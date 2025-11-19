"""
Planning Agent Implementation

This module provides the main planning agent that uses OpenRouter and Strands
to generate execution plans for other agents.
"""

import logging
from typing import Optional, AsyncIterable, Dict, Any
from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager

from .models import OpenRouterModel
from .config import AgentConfig
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
        ]

        # Track MCP manager for cleanup
        self.mcp_manager: Optional[MCPToolManager] = None

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

    async def plan_async(self, prompt: str) -> str:
        """
        Generate a plan asynchronously using the Strands Agent Loop.

        This method now properly uses the Strands Agent Loop, enabling:
        - Multi-step reasoning
        - Tool execution and recursion
        - Proper conversation management

        Args:
            prompt: User's request for planning

        Returns:
            Generated plan as a string
        """
        try:
            # Ensure MCP tools are initialized
            await self._ensure_mcp_initialized()

            logger.info("Using Strands Agent Loop for async planning")

            # Use the Strands Agent's invoke_async method to get the result
            # This will trigger the full agent loop with tool execution
            result = await self.agent.invoke_async(prompt)

            # Debug: Log the result structure
            logger.info(f"AgentResult type: {type(result)}")
            logger.info(f"AgentResult dir: {[attr for attr in dir(result) if not attr.startswith('_')]}")
            if hasattr(result, 'message'):
                logger.info(f"Message: {result.message}")
                logger.info(f"Message type: {type(result.message)}")
            if hasattr(result, '__dict__'):
                logger.info(f"AgentResult dict: {result.__dict__}")

            # Extract text from AgentResult
            if hasattr(result, 'message'):
                content = result.message.get('content', [])
                if content and isinstance(content, list):
                    text_parts = [
                        block.get('text', '')
                        for block in content
                        if 'text' in block
                    ]
                    if text_parts:
                        return '\n'.join(text_parts)

            # Fallback to string representation
            logger.warning(f"No text content found in result, returning string representation")
            return str(result)

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
        try:
            # Yield start event
            yield {
                "type": "start",
                "data": {"message": "Starting plan generation..."}
            }

            # Ensure MCP tools are initialized
            await self._ensure_mcp_initialized()

            logger.info("Using Strands Agent Loop for streaming planning")

            # Use the Strands Agent's stream_async method to get streaming events
            # This will trigger the full agent loop with tool execution
            async for event in self.agent.stream_async(prompt):
                # Convert Strands events to our expected format
                event_type = None
                event_data = {}

                # Handle different event types from Strands
                if "data" in event:
                    # Text data streaming
                    event_type = "data"
                    event_data = {"text": event["data"]}
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

                    # Include metrics if available
                    if hasattr(result, 'metrics'):
                        event_data["metrics"] = result.metrics
                elif "complete" in event and event["complete"]:
                    # Stream completion marker
                    continue
                else:
                    # Other events - pass through with minimal transformation
                    logger.debug(f"Unhandled event type: {event}")
                    continue

                # Yield the converted event
                if event_type:
                    yield {
                        "type": event_type,
                        "data": event_data
                    }

        except Exception as e:
            logger.error(f"Error in streaming plan: {e}")
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
