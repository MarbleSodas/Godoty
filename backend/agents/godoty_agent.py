import logging
import os
import threading
import warnings
import asyncio
from enum import Enum
from typing import Optional, Dict, Any, AsyncIterable, Literal
from datetime import datetime

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from strands import Agent
from strands.session.file_session_manager import FileSessionManager
from strands.agent.conversation_manager import SlidingWindowConversationManager

from core.model import GodotyOpenRouterModel
from agents.config import AgentConfig
from agents.config.prompts import Prompts
from agents.config.planning_prompts import PlanningPrompts
from agents.config.learning_prompts import LearningPrompts
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

# Agent Safety Constants for Monetization
MAX_AGENT_STEPS = 15  # Maximum tool calls per user request
MIN_BALANCE_FOR_STEP = 0.01  # Minimum balance ($0.01) to continue
BALANCE_CHECK_INTERVAL = 5  # Check balance every N steps


class AgentMode(Enum):
    """Agent modes for the three-phase workflow."""
    LEARNING = "learning"     # Deep research with web search
    PLANNING = "planning"     # Read-only information gathering
    EXECUTION = "execution"   # Full execution with write access


class PlanState(Enum):
    """State of a pending plan."""
    NONE = "none"             # No plan generated
    PENDING = "pending"       # Plan generated, awaiting approval
    APPROVED = "approved"     # Plan approved, ready/executing
    REJECTED = "rejected"     # Plan rejected


class GodotyAgent:
    """
    Godoty Agent with support for planning and execution modes.
    
    In PLANNING mode, the agent gathers information and proposes a plan.
    In EXECUTION mode, the agent executes an approved plan with full tool access.
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

        # Define Read-Only Tools for PLANNING mode
        self._planning_tools = [
            # File reading (no write)
            read_file, list_files, search_codebase,
            # Web/documentation tools
            search_documentation, fetch_webpage, get_godot_api_reference,
            search_godot_docs, get_class_reference, get_documentation_status,
            # Connection check
            ensure_godot_connection,
            # Scene analysis (read-only)
            get_project_overview, analyze_scene_tree, capture_visual_context,
            capture_editor_viewport, capture_game_viewport, get_visual_debug_info,
            inspect_scene_file, search_nodes,
            # Debug reading
            get_debug_output, get_debug_logs, search_debug_logs, monitor_debug_output,
            get_performance_metrics, analyze_node_performance, get_scene_debug_overlays,
            compare_scenes, get_debugger_state, access_debug_variables, get_call_stack_info,
            # GDScript analysis (read-only)
            analyze_gdscript_structure, validate_gdscript_syntax,
            # Context engine tools
            retrieve_context, get_signal_flow, get_class_hierarchy,
            find_usages, get_file_context, get_project_structure,
            get_context_stats
        ]
        
        # Define Learning Mode Tools (focused on research + documentation)
        # These are the same as planning tools - web search is enabled via model suffix
        self._learning_tools = [
            # File reading (no write)
            read_file, list_files, search_codebase,
            # Web/documentation tools (primary focus for learning)
            search_documentation, fetch_webpage, get_godot_api_reference,
            search_godot_docs, get_class_reference, get_documentation_status,
            # Connection check
            ensure_godot_connection,
            # Scene analysis (read-only)
            get_project_overview, analyze_scene_tree, capture_visual_context,
            capture_editor_viewport, capture_game_viewport, get_visual_debug_info,
            inspect_scene_file, search_nodes,
            # Debug reading
            get_debug_output, get_debug_logs, search_debug_logs, monitor_debug_output,
            get_performance_metrics, analyze_node_performance, get_scene_debug_overlays,
            compare_scenes, get_debugger_state, access_debug_variables, get_call_stack_info,
            # GDScript analysis (read-only)
            analyze_gdscript_structure, validate_gdscript_syntax,
            # Context engine tools
            retrieve_context, get_signal_flow, get_class_hierarchy,
            find_usages, get_file_context, get_project_structure,
            get_context_stats
        ]
        
        # Define Write/Modify Tools for EXECUTION mode (all planning tools + these)
        self._execution_only_tools = [
            # File modification
            write_file, delete_file,
            # GDScript modification
            modify_gdscript_method, add_gdscript_method, remove_gdscript_method,
            refactor_gdscript_method, extract_gdscript_method,
            # Node/scene modification
            create_node, modify_node_property, create_scene, open_scene, select_nodes,
            # Execution control
            play_scene, stop_playing,
            # Settings
            modify_project_setting,
        ]
        
        # Full tools = planning + execution
        self.tools = self._planning_tools + self._execution_only_tools
        
        # Current mode and pending plan
        self._current_mode: AgentMode = AgentMode.PLANNING
        self._pending_plan: Optional[str] = None
        self._plan_state: PlanState = PlanState.NONE
        self._plan_original_request: Optional[str] = None  # Original user request for plan regeneration
        
        # Try to restore plan from session
        self._restore_plan_from_session()

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
        
        # Agent safety tracking for monetization
        self._step_count = 0
        self._supabase_auth = None
        self._cached_balance = None
        self._last_balance_check = 0
    
    def _ensure_agent_initialized(self):
        """Ensure agent is initialized before use."""
        if not self._agent_initialized:
            logger.info("Agent not yet initialized - creating without project scope")
            self._create_agent()
            self._agent_initialized = True

    async def run(self, prompt: str, mode: Literal["learning", "planning", "execution"] = "planning") -> Dict[str, Any]:
        """
        Run the agent synchronously (non-streaming).
        
        Args:
            prompt: The user's request
            mode: 'learning' (research), 'planning' (read-only), or 'execution' (full access)
        
        Returns:
            Dict with response text and metrics
        """
        # Set mode and recreate agent with appropriate tools/prompt
        mode_map = {
            "learning": AgentMode.LEARNING,
            "planning": AgentMode.PLANNING,
            "execution": AgentMode.EXECUTION
        }
        self._set_mode(mode_map.get(mode, AgentMode.PLANNING))
        
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
            
            # Store plan if in planning mode
            if mode == "planning":
                self._pending_plan = response_text
            
            # Metrics are handled by callback
            metrics = {}
            if hasattr(self.agent, 'state'):
                 metrics = self.agent.state.get("godoty_metrics", {})

            return {
                "plan": response_text,
                "mode": mode,
                "has_pending_plan": self._pending_plan is not None,
                "metrics": metrics
            }
        except Exception as e:
            logger.error(f"Error in agent run: {e}")
            raise

    async def run_stream(self, prompt: str, mode: Literal["learning", "planning", "execution"] = "planning") -> AsyncIterable[Dict[str, Any]]:
        """
        Run the agent with streaming.
        
        Args:
            prompt: The user's request
            mode: 'learning' (research), 'planning' (read-only), or 'execution' (full access)
        
        Yields:
            Transformed event dicts
        """
        # Set mode and recreate agent with appropriate tools/prompt
        mode_map = {
            "learning": AgentMode.LEARNING,
            "planning": AgentMode.PLANNING,
            "execution": AgentMode.EXECUTION
        }
        self._set_mode(mode_map.get(mode, AgentMode.PLANNING))
        
        try:
            from agents.event_utils import transform_strands_event

            logger.info(f"[STREAM] Starting {mode} stream for session {self.session_id}")
            event_count = 0
            metrics_received = False
            collected_text = []  # Collect text for plan storage
            
            # Reset step count for this request
            self._step_count = 0
            tool_call_count = 0

            async for event in self.agent.stream_async(prompt):
                event_count += 1
                event_keys = list(event.keys()) if isinstance(event, dict) else str(type(event))
                logger.debug(f"[STREAM] Raw event #{event_count} keys: {event_keys}")
                
                transformed = transform_strands_event(event)

                if transformed:
                    event_type = transformed.get("type", "unknown")
                    logger.debug(f"[STREAM] Transformed event type: {event_type}")
                    
                    # Count tool calls for safety limits
                    if event_type == "tool_start" or event_type == "tool_result":
                        tool_call_count += 1
                        self._step_count = tool_call_count
                        
                        # Check step limit
                        if tool_call_count >= MAX_AGENT_STEPS:
                            logger.warning(f"Agent reached max step limit: {MAX_AGENT_STEPS}")
                            yield {"type": "warning", "data": {"message": f"Agent reached maximum step limit ({MAX_AGENT_STEPS})"}}
                            break
                        
                        # Periodic balance check (every N steps)
                        if tool_call_count % BALANCE_CHECK_INTERVAL == 0:
                            can_continue, balance_msg = await self._check_balance()
                            if not can_continue:
                                logger.warning(f"Agent stopped: {balance_msg}")
                                yield {"type": "error", "data": {"error": balance_msg, "code": 402}}
                                break
                    
                    # Collect text content for plan storage
                    if event_type == "text" or event_type == "data":
                        # transform_strands_event returns {"text": ...} for text events
                        text_content = transformed.get("data", {}).get("text", "")
                        if text_content:
                            collected_text.append(text_content)
                    
                    # Capture and persist metrics from transformed events
                    if event_type == "metrics":
                        metrics_received = True
                        metrics_data = transformed.get("data", {}).get("metrics", {})
                        logger.info(f"[STREAM] METRICS EVENT RECEIVED: {metrics_data}")
                        if metrics_data:
                            await self._update_metrics(metrics_data)
                    
                    # Add mode info to events
                    transformed["mode"] = mode
                    yield transformed

            # Store plan if in planning mode
            if mode == "planning" and collected_text:
                plan_text = "".join(collected_text)
                self.set_pending_plan(plan_text, original_request=prompt)

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
    
    async def _check_balance(self) -> tuple[bool, str]:
        """
        Check if user has sufficient balance to continue.
        
        Returns:
            Tuple of (can_continue: bool, message: str)
        """
        try:
            # Lazy-load supabase auth to avoid circular imports
            if self._supabase_auth is None:
                try:
                    from services.supabase_auth import get_supabase_auth
                    self._supabase_auth = get_supabase_auth()
                except ImportError:
                    # Supabase not available - allow continuation
                    return (True, "")
            
            # Only check if user is authenticated (monetization enabled)
            if not self._supabase_auth.is_authenticated:
                return (True, "")
            
            # Get current balance
            balance = self._supabase_auth.get_balance()
            if balance is None:
                # Unable to check - allow continuation but log warning
                logger.warning("Unable to check balance, allowing continuation")
                return (True, "")
            
            self._cached_balance = balance
            
            if balance < MIN_BALANCE_FOR_STEP:
                return (False, f"Insufficient credits (${balance:.4f}). Please top up to continue.")
            
            logger.debug(f"Balance check OK: ${balance:.4f}")
            return (True, "")
            
        except Exception as e:
            logger.error(f"Balance check error: {e}")
            # On error, allow continuation to avoid blocking users
            return (True, "")

    def _set_mode(self, mode: AgentMode):
        """
        Set the agent mode and recreate agent with appropriate tools/prompt.
        
        Args:
            mode: AgentMode.LEARNING, AgentMode.PLANNING, or AgentMode.EXECUTION
        """
        if self._current_mode != mode or not self._agent_initialized:
            self._current_mode = mode
            self._create_agent(
                project_path=self.project_path,
                mode=mode
            )
            self._agent_initialized = True
            logger.info(f"Agent mode set to: {mode.value}")

    def _create_agent(self, project_path: str = None, project_context: str = None, mode: AgentMode = None):
        """
        Create or recreate agent with optional project path scoping and mode.
        
        Args:
            project_path: Optional project path to scope agent operations to.
            project_context: Optional project context map for prompt injection.
            mode: AgentMode for selecting tools and prompt (defaults to current mode).
        """
        if mode is None:
            mode = self._current_mode
        
        # Get base system prompt
        base_prompt = Prompts.get_system_prompt(project_path, project_context)
        
        # Apply mode-specific prompt and select tools
        if mode == AgentMode.LEARNING:
            # Learning mode: research-focused with web search via model
            godot_version = None
            # Try to get Godot version from status for doc references
            try:
                from services.godot_manager import godot_manager
                status = godot_manager.get_status()
                godot_version = status.godot_version if status else None
            except Exception:
                pass
            system_prompt = LearningPrompts.get_learning_prompt(base_prompt, godot_version)
            tools = self._learning_tools
            logger.info("Using LEARNING mode: research tools with web search")
        elif mode == AgentMode.PLANNING:
            system_prompt = PlanningPrompts.get_planning_prompt(base_prompt)
            tools = self._planning_tools
            logger.info("Using PLANNING mode: read-only tools")
        else:
            # Execution mode - use full tools and optionally include pending plan
            system_prompt = PlanningPrompts.get_execution_prompt(
                base_prompt, 
                approved_plan=self._pending_plan
            )
            tools = self.tools  # All tools
            logger.info("Using EXECUTION mode: full tool access")
        
        self.agent = Agent(
            model=self.model,
            tools=tools,
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

    # Plan management methods for two-phase workflow
    
    def _restore_plan_from_session(self):
        """Restore pending plan from session storage if exists."""
        if not self.session_manager:
            return
        
        try:
            # Read session state file directly
            import json
            from pathlib import Path
            
            storage_dir = self.session_manager.storage_dir
            session_id = self.session_manager.session_id
            plan_file = Path(storage_dir) / f"session_{session_id}" / "plan_state.json"
            
            if plan_file.exists():
                with open(plan_file, 'r') as f:
                    plan_data = json.load(f)
                
                self._pending_plan = plan_data.get("plan")
                self._plan_state = PlanState(plan_data.get("state", "none"))
                self._plan_original_request = plan_data.get("original_request")
                
                if self._pending_plan and self._plan_state == PlanState.PENDING:
                    logger.info(f"Restored pending plan from session ({len(self._pending_plan)} chars)")
        except Exception as e:
            logger.warning(f"Failed to restore plan from session: {e}")
    
    def _save_plan_to_session(self):
        """Save current plan state to session storage."""
        if not self.session_manager:
            return
        
        try:
            import json
            from pathlib import Path
            
            storage_dir = self.session_manager.storage_dir
            session_id = self.session_manager.session_id
            session_dir = Path(storage_dir) / f"session_{session_id}"
            session_dir.mkdir(parents=True, exist_ok=True)
            
            plan_file = session_dir / "plan_state.json"
            plan_data = {
                "plan": self._pending_plan,
                "state": self._plan_state.value,
                "original_request": self._plan_original_request
            }
            
            with open(plan_file, 'w') as f:
                json.dump(plan_data, f, indent=2)
            
            logger.info(f"Saved plan state to session: {self._plan_state.value}")
        except Exception as e:
            logger.error(f"Failed to save plan to session: {e}")
    
    def get_pending_plan(self) -> Optional[str]:
        """Get the currently pending plan awaiting approval."""
        return self._pending_plan
    
    def get_plan_state(self) -> str:
        """Get the current plan state as a string."""
        return self._plan_state.value
    
    def get_plan_info(self) -> Dict[str, Any]:
        """Get full plan info including state and original request."""
        return {
            "plan": self._pending_plan,
            "state": self._plan_state.value,
            "original_request": self._plan_original_request,
            "has_pending_plan": self._plan_state == PlanState.PENDING
        }
    
    def has_pending_plan(self) -> bool:
        """Check if there's a pending plan awaiting approval."""
        return self._plan_state == PlanState.PENDING and self._pending_plan is not None
    
    def set_pending_plan(self, plan: str, original_request: str = None):
        """Set a new pending plan and save to session."""
        self._pending_plan = plan
        self._plan_state = PlanState.PENDING
        self._plan_original_request = original_request
        self._save_plan_to_session()
        logger.info(f"Set pending plan ({len(plan)} chars)")
    
    def clear_pending_plan(self):
        """Clear the pending plan (e.g., after rejection without regeneration)."""
        self._pending_plan = None
        self._plan_state = PlanState.NONE
        self._plan_original_request = None
        self._save_plan_to_session()
        logger.info("Pending plan cleared")
    
    async def approve_and_execute(self, execution_prompt: str = None) -> AsyncIterable[Dict[str, Any]]:
        """
        Approve the pending plan and execute it.
        
        Args:
            execution_prompt: Optional additional instructions for execution.
                              If not provided, uses the plan content.
        
        Yields:
            Execution stream events
        """
        if not self._pending_plan:
            yield {"type": "error", "data": {"error": "No pending plan to execute"}}
            return
        
        # Mark plan as approved
        self._plan_state = PlanState.APPROVED
        self._save_plan_to_session()
        
        # Build execution prompt including the plan
        plan_content = self._pending_plan
        if execution_prompt:
            prompt = f"{execution_prompt}\n\n## Approved Plan to Execute:\n{plan_content}"
        else:
            prompt = f"Execute the following approved plan step by step:\n\n{plan_content}"
        
        logger.info(f"Executing approved plan ({len(plan_content)} chars)")
        
        async for event in self.run_stream(prompt, mode="execution"):
            yield event
        
        # Clear plan after execution
        self.clear_pending_plan()
    
    def get_current_mode(self) -> str:
        """Get the current agent mode as a string."""
        return self._current_mode.value

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
