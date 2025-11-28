"""
Planning Agent Implementation

This module provides the main planning agent that uses OpenRouter and Strands
to generate execution plans for other agents.
"""

import logging
import uuid
import warnings
import os
from datetime import datetime
from typing import Optional, AsyncIterable, Dict, Any

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager

from context.engine import ContextEngine
from core.model import GodotyOpenRouterModel
from strands.session.file_session_manager import FileSessionManager
from agents.config import AgentConfig
from agents.metrics_tracker import TokenMetricsTracker
from agents.db import ProjectDB
from agents.tools import (
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
from agents.tools.mcp_tools import MCPToolManager

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

        # Initialize state
        self.db: Optional[ProjectDB] = None
        self.current_session_id: Optional[str] = None

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

        # Prepare params to avoid duplicates
        model_params = model_config.copy()
        for key in ['api_key', 'app_name', 'app_url']:
             model_params.pop(key, None)

        # Initialize OpenRouter model with metrics callback
        try:
            self.model = GodotyOpenRouterModel(
                api_key=api_key_value,
                metrics_callback=self._metrics_callback,
                site_url=model_config.get("app_url"),
                app_name=model_config.get("app_name"),
                **model_params
            )
            logger.info(f"Initialized GodotyOpenRouterModel: {model_config.get('model_id')}")
        except Exception as e:
            logger.error(f"Failed to initialize model: {e}")
            # Try fallback model
            if model_config.get('model_id') != AgentConfig.FALLBACK_MODEL:
                logger.info(f"Attempting fallback model: {AgentConfig.FALLBACK_MODEL}")
                model_config['model_id'] = AgentConfig.FALLBACK_MODEL
                model_params['model_id'] = AgentConfig.FALLBACK_MODEL
                self.model = GodotyOpenRouterModel(
                    api_key=api_key_value,
                    site_url=model_config.get("app_url"),
                    app_name=model_config.get("app_name"),
                    **model_params
                )
            else:
                raise

        # Initialize Context Engine
        # Repo root is 3 levels up: backend/agents/planning_agent.py -> backend/agents -> backend -> Root
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.context_engine = ContextEngine(repo_root)

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
            conversation_manager=self.conversation_manager,
            agent_id="planning-agent"
        )

        logger.info("Planning agent initialized successfully")

    def set_project_path(self, project_path: str):
        """Set the project path and initialize the database."""
        try:
            self.db = ProjectDB(project_path)
            logger.info(f"ProjectDB initialized for path: {project_path}")
        except Exception as e:
            logger.error(f"Failed to initialize ProjectDB: {e}")

    def _metrics_callback(self, cost: float, tokens: int, model_name: str,
                         prompt_tokens: int = 0, completion_tokens: int = 0,
                         message_id: Optional[str] = None):
        """
        Callback for recording metrics from the model.

        Implements dual tracking:
        1. ProjectDB for analytics
        2. agent.state['godoty_metrics'] ledger for UI display
        """
        # Record to ProjectDB for analytics
        if self.db and self.current_session_id:
            try:
                # Record basic session-level metric
                self.db.record_metric(self.current_session_id, cost, tokens, model_name)

                # Also record message_level metric if message_id provided
                if message_id:
                    self.db.record_message_metric(
                        session_id=self.current_session_id,
                        message_id=message_id,
                        role="assistant",  # Metrics are for LLM responses
                        cost=cost,
                        tokens=tokens,
                        model_name=model_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens
                    )
            except Exception as e:
                logger.error(f"Failed to record metric to ProjectDB: {e}")

        # Maintain metrics ledger in agent state for UI display
        try:
            if not hasattr(self.agent, 'state'):
                self.agent.state = {}

            if 'godoty_metrics' not in self.agent.state:
                self.agent.state['godoty_metrics'] = {
                    'total_cost': 0.0,
                    'total_tokens': 0,
                    'run_history': []
                }
                logger.debug("Initialized godoty_metrics ledger in agent state")

            ledger = self.agent.state['godoty_metrics']
            ledger['total_cost'] += cost
            ledger['total_tokens'] += tokens
            ledger['run_history'].append({
                'timestamp': datetime.utcnow().isoformat(),
                'model': model_name,
                'cost': cost,
                'tokens': tokens,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens
            })

            logger.debug(
                f"Updated metrics ledger: total_cost=${ledger['total_cost']:.6f}, "
                f"total_tokens={ledger['total_tokens']}"
            )

            # Persist to session manager
            if hasattr(self.agent, 'session_manager') and self.current_session_id:
                try:
                    self.agent.session_manager.update_agent(
                        self.current_session_id,
                        self.agent.to_session_agent()
                    )
                    logger.debug(f"Persisted metrics ledger for session {self.current_session_id}")
                except Exception as e:
                    logger.error(f"Failed to persist ledger to session manager: {e}")
        except Exception as e:
            logger.error(f"Failed to update metrics ledger: {e}", exc_info=True)

    def get_session_metrics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve metrics ledger for displaying session totals.

        Args:
            session_id: Optional session ID to load metrics from.
                       If not provided, uses current session's agent state.

        Returns:
            Dictionary containing total_cost, total_tokens, and run_history
        """
        # If session_id provided and different from current, load from FileSessionManager
        if session_id and session_id != self.current_session_id:
            try:
                session_manager = FileSessionManager(session_id=session_id)
                session_data = session_manager.read_agent(session_id)
                return session_data.state.get('godoty_metrics', {
                    'total_cost': 0.0,
                    'total_tokens': 0,
                    'run_history': []
                })
            except Exception as e:
                logger.error(f"Failed to load metrics for session {session_id}: {e}")
                return {
                    'total_cost': 0.0,
                    'total_tokens': 0,
                    'run_history': []
                }

        # Use current agent state
        if hasattr(self.agent, 'state'):
            return self.agent.state.get('godoty_metrics', {
                'total_cost': 0.0,
                'total_tokens': 0,
                'run_history': []
            })

        return {
            'total_cost': 0.0,
            'total_tokens': 0,
            'run_history': []
        }

    def start_session(self, session_id: str):
        """Start tracking a session for metrics and persistence."""
        self.current_session_id = session_id
        logger.info(f"Planning agent started tracking session: {session_id}")
        
        # Re-initialize agent with FileSessionManager for this session
        try:
            session_manager = FileSessionManager(session_id=session_id)
            
            # Recreate the agent with the session manager
            self.agent = Agent(
                model=self.model,
                tools=self.tools,
                system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT,
                conversation_manager=self.conversation_manager,
                session_manager=session_manager,
                agent_id="planning-agent"
            )
            
            # Load previous metrics if available
            if hasattr(self.agent, 'state'):
                metrics_state = self.agent.state.get("godoty_metrics", {})
                if metrics_state:
                    logger.info(f"Resumed session {session_id}. Previous cost: ${metrics_state.get('total_cost', 0):.4f}")
                    
        except Exception as e:
            logger.error(f"Failed to initialize session manager for {session_id}: {e}")
            # Fallback to default agent if session manager fails


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
                            conversation_manager=self.conversation_manager,
                            agent_id="planning-agent"
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

    def _prepare_agent_with_context(self, prompt: str):
        """
        Inject dynamic context into the agent's system prompt.
        """
        try:
            # Get context from engine
            context = self.context_engine.get_context_for_prompt(prompt)
            
            # Combine with base prompt
            base_prompt = AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT
            enhanced_prompt = f"{base_prompt}\n\n{context}"
            
            # Recreate agent with new system prompt but same history
            self.agent = Agent(
                model=self.model,
                tools=self.tools,
                system_prompt=enhanced_prompt,
                conversation_manager=self.conversation_manager,
                agent_id="planning-agent"
            )
            # logger.info("Agent context updated with dynamic codebase map")
            
        except Exception as e:
            logger.error(f"Failed to inject context: {e}")
            # Continue with existing agent if context fails

    def plan(self, prompt: str) -> str:
        """
        Generate a plan synchronously.

        Args:
            prompt: User's request for planning

        Returns:
            Generated plan as a string
        """
        try:
            # Inject context
            self._prepare_agent_with_context(prompt)

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

            # Inject context
            self._prepare_agent_with_context(prompt)

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
                        
                        # Count tool calls and errors
                        tool_stats = self.metrics_tracker.extract_tool_stats(result)
                        tool_calls_count = tool_stats["call_count"]
                        tool_errors_count = tool_stats["error_count"]
                        
                        # Add to metrics dict for response
                        metrics["tool_calls"] = tool_calls_count
                        metrics["tool_errors"] = tool_errors_count

                        # Metrics are now recorded via _metrics_callback automatically
                        logger.info(f"Metrics tracked for message {message_id}")
                except Exception as e:
                    logger.error(f"Failed to track metrics: {e}")
                    # Don't fail the request if metrics tracking fails

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

            # Inject context
            self._prepare_agent_with_context(prompt)

            print(f"[PLAN] Starting Strands Agent Loop...")
            logger.info(f"[PLAN] Starting Strands Agent Loop for prompt: {prompt[:100]}...")

            # Import shared event utility
            from agents.event_utils import transform_strands_event

            # Use the Strands Agent's stream_async method to get streaming events
            # This will trigger the full agent loop with tool execution
            event_count = 0
            print(f"[PLAN] About to enter stream_async loop...")
            async for event in self.agent.stream_async(prompt):
                event_count += 1
                # DEBUG: Log all events to see what we're actually getting
                # print(f"[PLAN] Stream event #{event_count} - keys: {list(event.keys())}")
                
                # Transform event using shared utility
                transformed = transform_strands_event(event)
                
                if transformed:
                    print(f"[PLAN] Yielding event: type={transformed['type']}")
                    yield transformed
                else:
                    # print(f"[PLAN] Event processed but skipped (no transformation)")
                    pass

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
            conversation_manager=self.conversation_manager,
            agent_id="planning-agent"
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
