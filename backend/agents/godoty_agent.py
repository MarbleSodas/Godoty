import logging
import os
import threading
import warnings
import asyncio
from typing import Optional, Dict, Any, AsyncIterable
from datetime import datetime

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from strands import Agent
from strands.session.file_session_manager import FileSessionManager
from strands.agent.conversation_manager import SlidingWindowConversationManager

from core.model import GodotyOpenRouterModel
from agents.config import AgentConfig
from agents.config.prompts import Prompts
from agents.tools import (
    # File system tools
    read_file, list_files, search_codebase,
    # Web tools
    search_documentation, fetch_webpage, get_godot_api_reference,
    # Godot docs tools (simplified)
    search_godot_docs, get_class_reference, get_documentation_status,
    # Godot bridge
    ensure_godot_connection,
    # Godot debug tools
    get_project_overview, analyze_scene_tree, capture_visual_context,
    capture_editor_viewport, capture_game_viewport, get_visual_debug_info,
    get_debug_output, get_debug_logs, search_debug_logs, monitor_debug_output,
    get_performance_metrics, inspect_scene_file, search_nodes,
    analyze_node_performance, get_scene_debug_overlays, compare_scenes,
    get_debugger_state, access_debug_variables, get_call_stack_info,
    # Godot executor tools
    create_node, modify_node_property, create_scene, open_scene,
    select_nodes, play_scene, stop_playing,
    # File tools
    write_file, delete_file, modify_gdscript_method, add_gdscript_method,
    remove_gdscript_method, modify_project_setting,
    # GDScript editor
    analyze_gdscript_structure, validate_gdscript_syntax,
    refactor_gdscript_method, extract_gdscript_method,
    # Context engine tools
    retrieve_context, get_signal_flow, get_class_hierarchy,
    find_usages, get_file_context, get_project_structure,
    get_context_stats, set_context_engine
)

logger = logging.getLogger(__name__)

class GodotyAgent:
    """
    Single Godoty Agent with access to all tools.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
        
        # Get configuration
        config = AgentConfig.get_openrouter_config()
        model_config = AgentConfig.get_model_config()
        
        api_key = config["api_key"]
        model_id = config["model_id"]
        
        # Initialize Model
        self.model = GodotyOpenRouterModel(
            api_key=api_key,
            model_id=model_id,
            site_url=config.get("app_url", "http://localhost:8000"),
            app_name=config.get("app_name", "Godoty")
        )

        # Initialize Session Manager
        self.session_manager = None
        if session_id:
            # AgentConfig is already imported at module level (line 14)
            storage_dir = AgentConfig.get_sessions_storage_dir()
            self.session_manager = FileSessionManager(
                session_id=session_id,
                storage_dir=storage_dir
            )
            logger.info(f"Initialized session {session_id} with storage: {storage_dir}")

        # Define Tools (All tools except MCP)
        self.tools = [
            read_file, list_files, search_codebase,
            search_documentation, fetch_webpage, get_godot_api_reference,
            # Godot documentation tools (simplified)
            search_godot_docs, get_class_reference, get_documentation_status,
            ensure_godot_connection,
            get_project_overview, analyze_scene_tree, capture_visual_context,
            capture_editor_viewport, capture_game_viewport, get_visual_debug_info,
            get_debug_output, get_debug_logs, search_debug_logs, monitor_debug_output,
            get_performance_metrics, inspect_scene_file, search_nodes,
            analyze_node_performance, get_scene_debug_overlays, compare_scenes,
            get_debugger_state, access_debug_variables, get_call_stack_info,
            create_node, modify_node_property, create_scene, open_scene,
            select_nodes, play_scene, stop_playing,
            write_file, delete_file, modify_gdscript_method, add_gdscript_method,
            remove_gdscript_method, modify_project_setting,
            analyze_gdscript_structure, validate_gdscript_syntax,
            refactor_gdscript_method, extract_gdscript_method,
            # Context engine tools
            retrieve_context, get_signal_flow, get_class_hierarchy,
            find_usages, get_file_context, get_project_structure,
            get_context_stats
        ]

        # Initialize Conversation Manager
        self.conversation_manager = SlidingWindowConversationManager(
            window_size=50, # Increased context window
            should_truncate_results=True
        )

        # Initialize project path
        self.project_path = None
        
        # Initialize context engine (will be built on Godot connection)
        self.context_engine: Optional[GodotContextEngine] = None
        
        # Defer agent creation - will be created when Godot connects with project info
        # or lazily on first use
        self.agent = None
        self._agent_initialized = False
        logger.info("GodotyAgent created - waiting for Godot connection to initialize")

        # Rehydrate metrics if session exists
        if self.session_manager and self.agent:
            try:
                # This loads the agent state from disk
                # Note: Agent constructor calls session_manager.read_agent() internally if session_manager is passed
                # But we can double check or access state here
                if hasattr(self.agent, 'state'):
                     # AgentState might not support default value in get()
                     try:
                         metrics = self.agent.state.get("godoty_metrics")
                         if metrics is None:
                             metrics = {}
                     except Exception:
                         metrics = {}
                     
                     if metrics:
                         logger.info(f"Resumed session {session_id}. Previous cost: ${metrics.get('total_cost', 0):.4f}")
            except Exception as e:
                logger.warning(f"Failed to load session state: {e}")
    
    def _ensure_agent_initialized(self):
        """Ensure agent is initialized before use."""
        if not self._agent_initialized:
            logger.info("Agent not yet initialized - creating without project scope")
            self._create_agent()
            self._agent_initialized = True

    async def run(self, prompt: str) -> Dict[str, Any]:
        """
        Run the agent synchronously (non-streaming).
        """
        self._ensure_agent_initialized()
        try:
            result = await self.agent.invoke_async(prompt)
            
            # Extract text
            response_text = str(result)
            if hasattr(result, 'message'):
                content = result.message.get('content', [])
                if isinstance(content, list):
                     text_parts = [b.get('text', '') for b in content if 'text' in b]
                     if text_parts:
                         response_text = '\n'.join(text_parts)
            
            # Metrics are handled by callback
            metrics = {}
            if hasattr(self.agent, 'state'):
                 metrics = self.agent.state.get("godoty_metrics", {})

            return {
                "plan": response_text, # Keeping "plan" key for compatibility
                "metrics": metrics
            }
        except Exception as e:
            logger.error(f"Error in agent run: {e}")
            raise

    async def run_stream(self, prompt: str) -> AsyncIterable[Dict[str, Any]]:
        """Run the agent with streaming."""
        self._ensure_agent_initialized()
        try:
            from agents.event_utils import transform_strands_event

            logger.info(f"[STREAM] Starting stream for session {self.session_id}")
            event_count = 0
            metrics_received = False

            async for event in self.agent.stream_async(prompt):
                event_count += 1
                event_keys = list(event.keys()) if isinstance(event, dict) else str(type(event))
                logger.debug(f"[STREAM] Raw event #{event_count} keys: {event_keys}")
                
                transformed = transform_strands_event(event)

                if transformed:
                    event_type = transformed.get("type", "unknown")
                    logger.debug(f"[STREAM] Transformed event type: {event_type}")
                    
                    # Capture and persist metrics from transformed events
                    if event_type == "metrics":
                        metrics_received = True
                        metrics_data = transformed.get("data", {}).get("metrics", {})
                        logger.info(f"[STREAM] METRICS EVENT RECEIVED: {metrics_data}")
                        if metrics_data:
                            await self._update_metrics(metrics_data)
                    
                    yield transformed

            logger.info(f"[STREAM] Stream complete. Events: {event_count}, Metrics received: {metrics_received}")

        except Exception as e:
            logger.error(f"Error in agent stream: {e}", exc_info=True)
            yield {"type": "error", "data": {"error": str(e)}}

    async def _update_metrics(self, metrics: Dict[str, Any]):
        """Persist metrics directly to MetricsDB."""
        # Extract metrics data
        prompt_tokens = metrics.get("input_tokens", 0)
        completion_tokens = metrics.get("output_tokens", 0)
        total_tokens = metrics.get("total_tokens", prompt_tokens + completion_tokens)
        cost = metrics.get("estimated_cost") or metrics.get("cost", 0.0)
        model_id = metrics.get("model_id") or self.model.model_id
        generation_id = metrics.get("generation_id")
        
        logger.info(f"Persisting metrics: tokens={total_tokens}, cost=${cost:.6f}, model={model_id}")
        
        # Persist to MetricsDB
        if self.session_id and (cost > 0 or total_tokens > 0):
            try:
                from agents.db import get_metrics_db
                db = get_metrics_db()
                db.log_api_call(
                    session_id=self.session_id,
                    model=model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost,
                    generation_id=generation_id
                )
                logger.info(f"Metrics saved: {total_tokens} tokens, ${cost:.6f}")
            except Exception as e:
                logger.error(f"Failed to persist metrics: {e}")

    def _create_agent(self, project_path: str = None, project_context: str = None):
        """
        Create or recreate agent with optional project path scoping.
        
        Args:
            project_path: Optional project path to scope agent operations to.
            project_context: Optional project context map for prompt injection.
        """
        system_prompt = Prompts.get_system_prompt(project_path, project_context)
        
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=system_prompt,
            conversation_manager=self.conversation_manager,
            session_manager=self.session_manager,
            agent_id="godoty-agent"
        )
        
        if project_path:
            logger.info(f"Agent created with project scope: {project_path}")
        else:
            logger.info("Agent created without project scope")

    async def initialize_session(self, project_path: str):
        """Initialize session with project context."""
        self.project_path = project_path
        
        # Get context engine that was set up by connection monitor
        # (Indexing is now triggered on Godot connection, not session creation)
        logger.info(f"Initializing session for project: {project_path}")
        
        try:
            self.context_engine = get_context_engine()
            if self.context_engine:
                logger.info(f"Using context engine for: {self.context_engine.project_path}")
            else:
                logger.info("Context engine not yet initialized (will be set up on Godot connection)")
        except Exception as e:
            logger.warning(f"Could not get context engine: {e}")
            self.context_engine = None
        
        # Get project context for prompt injection
        project_context = None
        if self.context_engine and self.context_engine.is_indexed():
            try:
                project_context = self.context_engine.get_project_map()
            except Exception as e:
                logger.warning(f"Failed to get project map: {e}")
        
        # Recreate agent with project-scoped prompt (including context)
        self._create_agent(project_path, project_context=project_context)
        logger.info(f"Initialized session {self.session_id} with project path: {project_path}")
        
        # Ensure session exists in MetricsDB
        try:
            from agents.db import get_metrics_db
            db = get_metrics_db()
            db.register_session(self.session_id)
        except Exception as e:
            logger.error(f"Failed to register session in MetricsDB: {e}")

    async def on_project_connected(self, project_path: str):
        """
        Called when Godot connects and project info is available.
        Reinitializes the agent with project scope.
        """
        logger.info(f"Project connected, reinitializing agent with scope: {project_path}")
        self.project_path = project_path
        
        # Get context engine (should be set by connection monitor)
        try:
            self.context_engine = get_context_engine()
            if self.context_engine:
                logger.info(f"Context engine available for: {self.context_engine.project_path}")
        except Exception as e:
            logger.warning(f"Could not get context engine: {e}")
            self.context_engine = None
        
        # Get project context if available
        project_context = None
        if self.context_engine and self.context_engine.is_indexed():
            try:
                project_context = self.context_engine.get_project_map()
            except Exception as e:
                logger.warning(f"Failed to get project map: {e}")
        
        # Create/recreate agent with project-scoped prompt
        self._create_agent(project_path, project_context=project_context)
        self._agent_initialized = True
        logger.info(f"Agent initialized with project scope: {project_path}")

    def reset_conversation(self):
        """Reset the agent's conversation history and context."""
        try:
            # Clear messages from the underlying Strands Agent
            if hasattr(self.agent, 'messages'):
                self.agent.messages = []

            # Reset conversation manager if it has reset capability
            if hasattr(self.conversation_manager, 'reset'):
                self.conversation_manager.reset()

            # Clear any conversation context in the agent state
            if hasattr(self.agent, 'state') and self.agent.state:
                # Remove conversation-related keys but preserve metrics
                keys_to_remove = ['conversation', 'messages', 'context']
                for key in keys_to_remove:
                    self.agent.state.pop(key, None)

            logger.info(f"Conversation reset for session {self.session_id}")

        except Exception as e:
            logger.error(f"Error resetting conversation: {e}")
            raise

# Singleton management
_godoty_agent_instance: Optional[GodotyAgent] = None
_agent_lock = threading.Lock()

def get_godoty_agent(session_id: Optional[str] = None) -> GodotyAgent:
    global _godoty_agent_instance

    with _agent_lock:
        if _godoty_agent_instance is None or (
            _godoty_agent_instance.session_id != session_id and session_id is not None
        ):
            _godoty_agent_instance = GodotyAgent(session_id)
        return _godoty_agent_instance
