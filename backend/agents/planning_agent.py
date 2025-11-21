"""
Planning Agent Implementation

This module provides the main planning agent that uses OpenRouter and Strands
to generate execution plans for other agents.
"""

import logging
import uuid
import warnings
from datetime import datetime
from typing import Optional, AsyncIterable, Dict, Any

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager

from .models import OpenRouterModel
from .config import AgentConfig
from .metrics_tracker import TokenMetricsTracker
from .tools import (
    # File system tools
    read_file,
    list_files,
    search_codebase,
    # Web tools
    search_documentation,
    fetch_webpage,
    get_godot_api_reference,
    # Godot bridge
    GodotBridge,
    get_godot_bridge,
    ensure_godot_connection,
    # Godot debug tools
    GodotDebugTools,
    get_project_overview,
    analyze_scene_tree,
    capture_visual_context,
    capture_editor_viewport,
    capture_game_viewport,
    get_visual_debug_info,
    get_debug_output,
    get_debug_logs,
    search_debug_logs,
    monitor_debug_output,
    get_performance_metrics,
    inspect_scene_file,
    search_nodes,
    # Advanced scene analysis tools
    analyze_node_performance,
    get_scene_debug_overlays,
    compare_scenes,
    # Runtime debugging tools
    get_debugger_state,
    access_debug_variables,
    get_call_stack_info,
    # Godot executor tools (safe operations only)
    create_node,
    modify_node_property,
    create_scene,
    open_scene,
    select_nodes,
    play_scene,
    stop_playing,
    )
from .tools.plan_submission import submit_execution_plan
from .tools.mcp_tools import MCPToolManager

logger = logging.getLogger(__name__)


class PlanningAgent:
    """
    Planning agent that creates execution plans for other agents.

    This agent uses OpenRouter models via Strands Agents framework to:
    - Analyze user requests
    - Break down complex tasks into steps
    - Identify dependencies and resources
    - Provide actionable execution plans
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
        enable_mcp: Optional[bool] = None,
        **kwargs
    ):
        """
        Initialize the planning agent.

        Args:
            api_key: OpenRouter API key (defaults to config)
            model_id: Model ID to use (defaults to config)
            enable_mcp: Enable MCP tools (defaults to config)
            **kwargs: Additional configuration options
        """
        # Get configuration
        config = AgentConfig.get_openrouter_config()
        model_config = AgentConfig.get_model_config()

        # Override with provided values
        api_key_value = api_key if api_key else config["api_key"]
        if model_id:
            model_config["model_id"] = model_id
        else:
            model_config["model_id"] = config["model_id"]

        # Add app name and URL to model config
        model_config["app_name"] = config.get("app_name", "Godot-Assistant")
        model_config["app_url"] = config.get("app_url", "http://localhost:8000")

        # Merge additional config
        model_config.update(kwargs)

        # Initialize OpenRouter model with new signature
        try:
            self.model = OpenRouterModel(api_key_value, **model_config)
            logger.info(f"Initialized OpenRouter model: {model_config.get('model_id')}")
        except Exception as e:
            logger.error(f"Failed to initialize model: {e}")
            # Try fallback model
            if model_config.get('model_id') != AgentConfig.FALLBACK_MODEL:
                logger.info(f"Attempting fallback model: {AgentConfig.FALLBACK_MODEL}")
                model_config['model_id'] = AgentConfig.FALLBACK_MODEL
                self.model = OpenRouterModel(api_key_value, **model_config)
            else:
                raise

        # Define base tools for the agent - limited to safe operations
        self.tools = [
            # File system tools
            read_file,
            list_files,
            search_codebase,
            # Web tools
            search_documentation,
            fetch_webpage,
            get_godot_api_reference,
            # Godot connection tools
            ensure_godot_connection,
            # Safe Godot debug tools (read-only operations)
            get_project_overview,
            analyze_scene_tree,
            capture_visual_context,
            capture_editor_viewport,
            capture_game_viewport,
            get_visual_debug_info,
            get_debug_output,
            get_debug_logs,
            search_debug_logs,
            monitor_debug_output,
            get_performance_metrics,
            inspect_scene_file,
            search_nodes,
            # Advanced scene analysis tools
            analyze_node_performance,
            get_scene_debug_overlays,
            compare_scenes,
            # Runtime debugging tools
            get_debugger_state,
            access_debug_variables,
            get_call_stack_info,
            # Safe Godot executor tools (non-destructive operations)
            create_node,
            modify_node_property,
            create_scene,
            open_scene,
            select_nodes,
            play_scene,
            stop_playing,
            # Note: delete_node removed for safety - agents can create/modify but not delete
            
            # Plan submission
            submit_execution_plan,
        ]

        # Track MCP manager for cleanup
        self.mcp_manager: Optional[MCPToolManager] = None

        # Initialize metrics tracker if enabled
        metrics_config = AgentConfig.get_metrics_config()
        self.metrics_enabled = metrics_config.get("enabled", True)
        self.metrics_tracker: Optional[TokenMetricsTracker] = None
        if self.metrics_enabled:
            self.metrics_tracker = TokenMetricsTracker(api_key=api_key_value)
            logger.info("Metrics tracking enabled")

        # Initialize conversation manager for context handling BEFORE MCP initialization
        self.conversation_manager = SlidingWindowConversationManager(
            window_size=20,  # Keep last 20 messages for context
            should_truncate_results=True
        )

        # Initialize MCP tools if enabled
        mcp_enabled = enable_mcp if enable_mcp is not None else AgentConfig.is_mcp_enabled()
        if mcp_enabled:
            self._initialize_mcp_tools_sync()

            # Try to initialize MCP tools synchronously if possible
            try:
                import asyncio
                # Check if we're already in an event loop
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an async context, we'll initialize lazily later
                    logger.info("In async context, MCP tools will be initialized lazily")
                except RuntimeError:
                    # We're not in an async context, try to initialize
                    logger.info("Initializing MCP tools synchronously...")
                    asyncio.run(self._ensure_mcp_initialized())
            except Exception as e:
                logger.warning(f"Failed to initialize MCP tools synchronously: {e}")
                if not AgentConfig.MCP_FAIL_SILENTLY:
                    logger.warning("MCP tools will be initialized lazily when needed")

        # Create Strands agent
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT,
            conversation_manager=self.conversation_manager
        )

        logger.info("Planning agent initialized successfully")

    def _initialize_mcp_tools_sync(self):
        """
        Initialize MCP tools synchronously during agent construction.

        This is a workaround since __init__ can't be async. MCP tools are
        initialized lazily on first use.
        """
        try:
            logger.info("MCP tools will be initialized on first agent invocation")
            self.mcp_manager = MCPToolManager.get_instance()
            # Note: Actual initialization happens in _ensure_mcp_initialized
        except Exception as e:
            error_msg = f"Failed to prepare MCP tool manager: {e}"
            if AgentConfig.MCP_FAIL_SILENTLY:
                logger.warning(error_msg)
                logger.warning("Continuing without MCP tools")
            else:
                logger.error(error_msg)
                raise

    async def _ensure_mcp_initialized(self):
        """
        Ensure MCP tools are initialized before use.

        This is called before agent invocations to lazily initialize MCP.
        """
        if self.mcp_manager:
            try:
                # Initialize if not connected
                if not self.mcp_manager.is_connected():
                    logger.info("Initializing MCP tools...")
                    servers_config = AgentConfig.get_mcp_servers_config()
                    success = await self.mcp_manager.initialize(
                        servers=servers_config,
                        fail_silently=AgentConfig.MCP_FAIL_SILENTLY
                    )
                else:
                    logger.info("MCP already connected, checking for tools...")
                    success = True

                if success:
                    # Always get MCP tools and add them if not already present
                    mcp_tools = self.mcp_manager.get_all_tools()
                    existing_tool_names = {getattr(tool, '__name__', str(tool)) for tool in self.tools}

                    # Add only new MCP tools
                    new_tools = []
                    for tool in mcp_tools:
                        tool_name = getattr(tool, '__name__', str(tool))
                        if tool_name not in existing_tool_names:
                            new_tools.append(tool)
                            existing_tool_names.add(tool_name)

                    if new_tools:
                        logger.info(f"Adding {len(new_tools)} new MCP tools to agent")
                        self.tools.extend(new_tools)

                        # Recreate agent with updated tools
                        self.agent = Agent(
                            model=self.model,
                            tools=self.tools,
                            system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT,
                            conversation_manager=self.conversation_manager
                        )

                        connected_servers = self.mcp_manager.get_connected_servers()
                        logger.info(f"MCP tools updated successfully: {', '.join(connected_servers)}")
                    else:
                        logger.info("All MCP tools already present in agent tools")
                else:
                    logger.warning("No MCP servers connected")

            except Exception as e:
                error_msg = f"Failed to initialize MCP tools: {e}"
                if AgentConfig.MCP_FAIL_SILENTLY:
                    logger.warning(error_msg)
                    logger.warning("Continuing without MCP tools")
                else:
                    logger.error(error_msg)
                    raise

    def plan(self, prompt: str) -> str:
        """
        Generate a plan synchronously.

        Args:
            prompt: User's request for planning

        Returns:
            Generated plan as a string
        """
        try:
            result = self.agent(prompt)

            # Extract text from result
            if hasattr(result, 'message'):
                content = result.message.get('content', [])
                if content and isinstance(content, list):
                    text_parts = [
                        block.get('text', '')
                        for block in content
                        if 'text' in block
                    ]
                    return '\n'.join(text_parts)

            return str(result)

        except Exception as e:
            logger.error(f"Error generating plan: {e}")
            raise

    async def plan_async(self, prompt: str, session_id: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a plan asynchronously using the Strands Agent Loop.

        This method now properly uses the Strands Agent Loop, enabling:
        - Multi-step reasoning
        - Tool execution and recursion
        - Proper conversation management
        - Metrics tracking for tokens and costs

        Args:
            prompt: User's request for planning
            session_id: Optional session ID for metrics tracking
            project_id: Optional project ID for metrics tracking

        Returns:
            Dictionary with plan text, message_id, and optional metrics
        """
        start_time = datetime.utcnow()
        message_id = str(uuid.uuid4())
        
        try:
            # Ensure MCP tools are initialized
            await self._ensure_mcp_initialized()

            logger.info("Using Strands Agent Loop for async planning")

            # Use the Strands Agent's invoke_async method to get the result
            result = await self.agent.invoke_async(prompt)

            # Extract text from AgentResult
            response_text = ""
            if hasattr(result, 'message'):
                content = result.message.get('content', [])
                if content and isinstance(content, list):
                    text_parts = [
                        block.get('text', '')
                        for block in content
                        if 'text' in block
                    ]
                    if text_parts:
                        response_text = '\n'.join(text_parts)

            if not response_text:
                response_text = str(result)

            # Extract and persist metrics if enabled
            metrics = None
            if self.metrics_enabled and self.metrics_tracker:
                try:
                    # Get model ID from config
                    model_id = self.model.get_config().get("model_id", "unknown")
                    
                    # Extract metrics from result
                    metrics = self.metrics_tracker.extract_metrics_from_strands_result(result, model_id)
                    
                    if metrics:
                        # Calculate response time
                        response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                        
                        # Count tool calls
                        tool_calls_count = self.metrics_tracker.count_tool_calls(result)
                        
                        # Store metrics in database
                        from database import get_db_manager
                        db_manager = get_db_manager()
                        
                        await db_manager.create_message_metrics(
                            message_id=message_id,
                            model_id=metrics.get("model_id", model_id),
                            prompt_tokens=metrics.get("prompt_tokens", 0),
                            completion_tokens=metrics.get("completion_tokens", 0),
                            total_tokens=metrics.get("total_tokens", 0),
                            estimated_cost=metrics.get("estimated_cost", 0.0),
                            session_id=session_id,
                            project_id=project_id,
                            response_time_ms=response_time_ms,
                            stop_reason=metrics.get("stop_reason"),
                            tool_calls_count=tool_calls_count
                        )
                        
                        logger.info(f"Persisted metrics for message {message_id}")
                except Exception as e:
                    logger.error(f"Failed to persist metrics: {e}")
                    # Don't fail the request if metrics fail

            return {
                "plan": response_text,
                "message_id": message_id,
                "metrics": metrics
            }

        except Exception as e:
            logger.error(f"Error generating plan: {e}")
            raise

    async def plan_stream(self, prompt: str) -> AsyncIterable[Dict[str, Any]]:
        """
        Generate a plan with streaming responses using the Strands Agent Loop.

        This method now properly uses the Strands Agent Loop, enabling:
        - Real-time streaming of text, tool calls, and results
        - Multi-step reasoning with tool execution
        - Proper event handling and conversation management

        Args:
            prompt: User's request for planning

        Yields:
            Dictionary events containing:
            - type: Event type ('start', 'data', 'tool_use', 'tool_result', 'end', etc.)
            - data: Event data (text chunk, tool info, etc.)
        """
        def sanitize_event_data(data: Any) -> Any:
            """
            Sanitize event data to ensure JSON serializability.
            Filters out complex objects like EventLoopMetrics.
            """
            if data is None or isinstance(data, (str, int, float, bool)):
                return data
            elif isinstance(data, dict):
                sanitized = {}
                for key, value in data.items():
                    # Skip non-serializable objects
                    if hasattr(value, '__class__'):
                        class_name = value.__class__.__name__
                        if 'EventLoopMetrics' in class_name or 'Metrics' in class_name:
                            # Skip metrics objects that aren't primitives
                            continue
                    # Skip private keys
                    if isinstance(key, str) and key.startswith('_'):
                        continue
                    try:
                        sanitized[key] = sanitize_event_data(value)
                    except (TypeError, ValueError):
                        # Convert to string if can't serialize
                        sanitized[key] = str(value)
                return sanitized
            elif isinstance(data, (list, tuple)):
                return [sanitize_event_data(item) for item in data]
            else:
                # Try to serialize, otherwise convert to string
                try:
                    import json
                    json.dumps(data)
                    return data
                except (TypeError, ValueError):
                    return str(data)
        
        try:
            # Yield start event
            print("\n" + "="*80)
            print("[PLAN] PLAN_STREAM CALLED")
            print(f"   Prompt: {prompt[:100]}...")
            print("="*80)

            yield {
                "type": "start",
                "data": {"message": "Starting plan generation..."}
            }

            # Ensure MCP tools are initialized
            await self._ensure_mcp_initialized()

            print(f"[PLAN] Starting Strands Agent Loop...")
            logger.info(f"[PLAN] Starting Strands Agent Loop for prompt: {prompt[:100]}...")

            # Use the Strands Agent's stream_async method to get streaming events
            # This will trigger the full agent loop with tool execution
            event_count = 0
            print(f"[PLAN] About to enter stream_async loop...")
            async for event in self.agent.stream_async(prompt):
                event_count += 1
                # DEBUG: Log all events to see what we're actually getting
                print(f"[PLAN] Stream event #{event_count} - keys: {list(event.keys())}")
                # Note: Skipping full event data print to avoid emoji encoding errors
                # print(f"   Full event data: {event}")
                logger.info(f"[PLAN] Stream event #{event_count} - keys: {list(event.keys())}")
                logger.debug(f"   Full event: {event}")

                # Convert Strands events to our expected format
                event_type = None
                event_data = {}

                # Handle different event types from Strands
                # Strands uses Claude's event format, so check for 'event' key first
                if "event" in event:
                    # Claude-style streaming events
                    inner_event = event["event"]
                    print(f"   [PLAN] Inner event keys: {list(inner_event.keys())}")
                    # Note: Skipping full inner event print to avoid emoji encoding errors
                    # print(f"   [PLAN] Inner event: {inner_event}")

                    # Check for content block delta (actual text chunks)
                    if "contentBlockDelta" in inner_event:
                        delta = inner_event["contentBlockDelta"].get("delta", {})
                        if "text" in delta:
                            event_type = "data"
                            event_data = {"text": delta["text"]}
                            logger.debug(f"Text delta: {delta['text']}")
                    # Tool use events
                    elif "contentBlockStart" in inner_event:
                        block = inner_event["contentBlockStart"].get("contentBlock", {})
                        if "toolUse" in block:
                            tool_use = block["toolUse"]
                            event_type = "tool_use"
                            event_data = {
                                "tool_name": tool_use.get("name"),
                                "tool_input": tool_use.get("input", {})
                            }
                    # Message start/stop events - we can ignore these
                    elif "messageStart" in inner_event or "messageStop" in inner_event:
                        print(f"   [PLAN] Skipping messageStart/Stop event")
                        continue
                    else:
                        print(f"   [PLAN] UNHANDLED inner event keys: {list(inner_event.keys())}")
                        # Note: Skipping full unhandled event print to avoid emoji encoding errors
                        # print(f"   [PLAN] UNHANDLED inner event data: {inner_event}")
                        logger.debug(f"Unhandled inner event: {inner_event}")
                        continue

                elif "data" in event:
                    # Skip Strands metadata events (they have agent, event_loop_cycle_id, etc.)
                    # These are duplicates of the contentBlockDelta events
                    if "agent" in event or "event_loop_cycle_id" in event:
                        continue
                    # Legacy text data streaming (might not be used)
                    event_type = "data"
                    event_data = {"text": event["data"]}
                    logger.debug(f"Data event: {event['data']}")
                elif "current_tool_use" in event:
                    # Tool being executed
                    tool_info = event["current_tool_use"]
                    event_type = "tool_use"
                    event_data = {
                        "tool_name": tool_info.get("name"),
                        "tool_input": tool_info.get("input", {})
                    }
                elif "tool_result" in event:
                    # Tool execution result
                    tool_result = event["tool_result"]
                    event_type = "tool_result"
                    event_data = {
                        "tool_name": tool_result.get("name"),
                        "result": tool_result.get("content", [])
                    }
                elif "result" in event:
                    # Final result - extract and yield end event
                    result = event["result"]
                    event_type = "end"
                    event_data = {
                        "stop_reason": getattr(result, 'stop_reason', 'end_turn')
                    }

                    # Include metrics if available (sanitized)
                    if hasattr(result, 'metrics'):
                        # Only include basic metrics, not complex objects
                        try:
                            metrics = result.metrics
                            if isinstance(metrics, dict):
                                event_data["metrics"] = sanitize_event_data(metrics)
                        except Exception as e:
                            logger.debug(f"Could not include metrics: {e}")
                elif "complete" in event and event["complete"]:
                    # Stream completion marker
                    continue
                # Ignore these common events
                elif "message" in event:
                    # Check for tool calls in the message (often happens at the end of generation)
                    msg = event["message"]
                    tool_calls = []
                    
                    # Handle object vs dict
                    if hasattr(msg, 'tool_calls'):
                        tool_calls = msg.tool_calls
                    elif isinstance(msg, dict):
                        tool_calls = msg.get('tool_calls', [])
                        
                    # Yield tool use events if found
                    if tool_calls:
                        for tc in tool_calls:
                            # Handle ToolCall object vs dict
                            if hasattr(tc, 'name'):
                                tool_name = tc.name
                                tool_input = tc.parameters if hasattr(tc, 'parameters') else {}
                            else:
                                tool_name = tc.get('name')
                                tool_input = tc.get('parameters', {})
                                
                            event_type = "tool_use"
                            event_data = {
                                "tool_name": tool_name,
                                "tool_input": tool_input
                            }
                            print(f"[PLAN] Extracted tool_use from message: {tool_name}")
                            logger.info(f"[PLAN] Extracted tool_use from message: {tool_name}")
                            
                            yield {
                                "type": event_type,
                                "data": sanitize_event_data(event_data)
                            }
                    continue

                elif "init_event_loop" in event or "start" in event or "start_event_loop" in event:
                    continue
                else:
                    # Other events - LOG THEM so we can see what we're missing!
                    logger.warning(f"Unhandled event type with keys: {list(event.keys())}, event: {event}")
                    continue

                # Sanitize and yield the converted event (MOVED INSIDE LOOP!)
                if event_type:
                    sanitized_data = sanitize_event_data(event_data)
                    print(f"[PLAN] Yielding event: type={event_type}")
                    logger.info(f"[PLAN] Yielding event: type={event_type}")
                    yield {
                        "type": event_type,
                        "data": sanitized_data
                    }
                else:
                    print(f"[PLAN] Event processed but event_type is None - event skipped")

            print(f"[PLAN] Stream loop completed. Total events processed: {event_count}")
            print("="*80 + "\n")
            logger.info(f"[PLAN] Stream loop completed. Total events processed: {event_count}")

        except Exception as e:
            logger.error(f"Error in streaming plan: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield {
                "type": "error",
                "data": {"error": str(e)}
            }

    def reset_conversation(self):
        """Reset the conversation history by recreating the agent."""
        # Recreate the agent to reset conversation history
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT,
            conversation_manager=self.conversation_manager
        )
        logger.info("Conversation history reset")

    async def close(self):
        """Close the agent and cleanup resources."""
        # Cleanup MCP connections
        if self.mcp_manager:
            try:
                await self.mcp_manager.cleanup()
                logger.info("MCP tools cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up MCP tools: {e}")

        # Cleanup metrics tracker
        if self.metrics_tracker:
            try:
                await self.metrics_tracker.close()
                logger.info("Metrics tracker cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up metrics tracker: {e}")

        # Close model
        if hasattr(self.model, 'close'):
            await self.model.close()

        logger.info("Planning agent closed")


# Singleton instance
_planning_agent_instance: Optional[PlanningAgent] = None


def get_planning_agent() -> PlanningAgent:
    """
    Get or create the planning agent singleton instance.

    Returns:
        PlanningAgent instance
    """
    global _planning_agent_instance

    if _planning_agent_instance is None:
        _planning_agent_instance = PlanningAgent()

    return _planning_agent_instance


async def close_planning_agent():
    """Close the planning agent singleton instance."""
    global _planning_agent_instance

    if _planning_agent_instance is not None:
        await _planning_agent_instance.close()
        _planning_agent_instance = None
