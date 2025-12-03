import logging
import os
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
from agents.tools import (
    # File system tools
    read_file, list_files, search_codebase,
    # Web tools
    search_documentation, fetch_webpage, get_godot_api_reference,
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
            self.session_manager = FileSessionManager(session_id=session_id)

        # Define Tools (All tools except MCP)
        self.tools = [
            read_file, list_files, search_codebase,
            search_documentation, fetch_webpage, get_godot_api_reference,
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

        # Create Agent
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT, # Reusing prompt for now
            conversation_manager=self.conversation_manager,
            session_manager=self.session_manager,
            agent_id="godoty-agent"
        )
        
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
                    self._update_metrics(event["metrics"])

        except Exception as e:
            logger.error(f"Error in agent stream: {e}", exc_info=True)
            yield {"type": "error", "data": {"error": str(e)}}

    def _update_metrics(self, metrics: Dict[str, Any]):
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
        
        # Extract cost from OpenRouter (check multiple field names for compatibility)
        cost = metrics.get("openrouter_cost") or metrics.get("cost", 0.0)
        usage = metrics.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        
        if cost > 0 or tokens > 0:
            ledger['total_cost'] += cost
            ledger['total_tokens'] += tokens
            ledger['run_history'].append({
                'timestamp': datetime.utcnow().isoformat(),
                'cost': cost,
                'tokens': tokens,
                'model': self.model.model_id
            })
            
            # Persist
            if self.session_manager and self.session_id:
                try:
                    self.session_manager.update_agent(self.session_id, self.agent.to_session_agent())
                except Exception as e:
                    logger.error(f"Failed to persist metrics: {e}")

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

def get_godoty_agent(session_id: Optional[str] = None) -> GodotyAgent:
    global _godoty_agent_instance
    # If session_id is provided, we might need a new instance or update the existing one
    # For simplicity in this refactor, we'll create a new one if session_id changes or is not set
    
    if _godoty_agent_instance is None or (_godoty_agent_instance.session_id != session_id and session_id is not None):
        _godoty_agent_instance = GodotyAgent(session_id)
        
    return _godoty_agent_instance
    return _godoty_agent_instance
