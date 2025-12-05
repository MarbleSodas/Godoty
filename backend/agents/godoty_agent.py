import logging
import os
import threading
import warnings
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
    refactor_gdscript_method, extract_gdscript_method
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
            refactor_gdscript_method, extract_gdscript_method
        ]

        # Initialize Conversation Manager
        self.conversation_manager = SlidingWindowConversationManager(
            window_size=50, # Increased context window
            should_truncate_results=True
        )

        # Initialize project path
        self.project_path = None
        
        # Create Agent (will be recreated with scoped prompt on initialize_session)
        self._create_agent()

        # Rehydrate metrics if session exists
        if self.session_manager:
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

    async def run(self, prompt: str) -> Dict[str, Any]:
        """
        Run the agent synchronously (non-streaming).
        """
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
        """
        Run the agent with streaming.
        """
        try:
            # Import shared event utility
            from agents.event_utils import transform_strands_event

            async for event in self.agent.stream_async(prompt):
                # Transform event
                logger.debug(f"[SSE] Raw Strands event: {event}")
                transformed = transform_strands_event(event)
                logger.debug(f"[SSE] Transformed event: {transformed}")

                # Add content length check for debugging
                if transformed and transformed.get("type") == "text":
                    content_length = len(transformed.get("content", ""))
                    logger.debug(f"[SSE] Text event content length: {content_length}")
                    if content_length == 0:
                        logger.warning(f"[SSE] Empty content event detected: {transformed}")

                if transformed:
                    yield transformed
                    
                # Check for metrics update and persist
                if "metrics" in event:
                    await self._update_metrics(event["metrics"])

        except Exception as e:
            logger.error(f"Error in agent stream: {e}", exc_info=True)
            yield {"type": "error", "data": {"error": str(e)}}

    async def _update_metrics(self, metrics: Dict[str, Any]):
        """Update and persist metrics ledger."""
        if not hasattr(self.agent, 'state'):
            self.agent.state = {}
            
        if 'godoty_metrics' not in self.agent.state:
            self.agent.state['godoty_metrics'] = {
                'total_cost': 0.0,
                'total_tokens': 0,
                'run_history': []
            }
            
        ledger = self.agent.state['godoty_metrics']
        
        # Extract metrics data
        usage = metrics.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        
        # Cost extraction
        cost = metrics.get("openrouter_cost") or metrics.get("cost", 0.0)
        actual_cost = metrics.get("actual_cost") # Might be populated if available
        
        # Prefer actual cost if available, otherwise estimated
        final_cost = float(actual_cost if actual_cost is not None else cost)

        # Metadata
        generation_id = metrics.get("id") or metrics.get("generation_id")
        model_id = self.model.model_id
        
        if final_cost > 0 or total_tokens > 0:
            ledger['total_cost'] += final_cost
            ledger['total_tokens'] += total_tokens
            ledger['run_history'].append({
                'timestamp': datetime.utcnow().isoformat(),
                'cost': final_cost,
                'tokens': total_tokens,
                'model': model_id
            })
            
            # Persist to FileSessionManager (Agent State)
            if self.session_manager and self.session_id:
                try:
                    self.session_manager.update_agent(self.session_id, self.agent.to_session_agent())
                except Exception as e:
                    logger.error(f"Failed to persist metrics to session manager: {e}")
            
            # Persist to Raw SQLite MetricsDB
            if self.session_id:
                try:
                    from agents.db import get_metrics_db
                    db = get_metrics_db()
                    
                    db.log_api_call(
                        session_id=self.session_id,
                        model=model_id,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost=final_cost,
                        generation_id=generation_id
                    )
                    
                    logger.debug(f"Persisted metrics to MetricsDB: cost=${final_cost:.6f}, tokens={total_tokens}")
                except Exception as e:
                    logger.error(f"Failed to persist metrics to MetricsDB: {e}")

    def _create_agent(self, project_path: str = None):
        """
        Create or recreate agent with optional project path scoping.
        
        Args:
            project_path: Optional project path to scope agent operations to.
        """
        system_prompt = Prompts.get_system_prompt(project_path)
        
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
        
        # Recreate agent with project-scoped prompt
        self._create_agent(project_path)
        logger.info(f"Initialized session {self.session_id} with project path: {project_path}")
        
        # Ensure session exists in MetricsDB
        try:
            from agents.db import get_metrics_db
            db = get_metrics_db()
            db.register_session(self.session_id)
        except Exception as e:
            logger.error(f"Failed to register session in MetricsDB: {e}")

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
