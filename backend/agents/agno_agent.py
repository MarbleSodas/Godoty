"""
Godoty Agent with Agno Team Architecture.

This module provides the main Agno-based agent implementation with:
- Coordinator Team pattern with specialized member agents
- HITL (Human-in-the-Loop) for plan approval workflow
- SQLite session state management
- Knowledge integration with LanceDB
- Metrics tracking from OpenRouter responses

Team Structure:
- GodotyTeam (Coordinator): Routes tasks to appropriate specialists
  - ResearchAgent: Documentation and codebase research
  - PlannerAgent: Plan generation with read-only tools
  - ExecutorAgent: File modification and scene manipulation
"""

import logging
import os
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterable, Dict, List, Optional, Literal

from agno.agent import Agent
from agno.team import Team
from agno.run.response import RunResponse
from agno.models.openrouter import OpenRouter
from agno.storage.sqlite import SqliteStorage
from agno.memory.v2.db.sqlite import SqliteMemoryDb
from agno.memory.v2.memory import Memory

from core.model import create_godoty_model, GodotyOpenRouterConfig
from agents.config import AgentConfig
from agents.config.prompts import Prompts
from agents.config.planning_prompts import PlanningPrompts
from agents.config.learning_prompts import LearningPrompts
from agents.toolkits import (
    GodotReadToolkit,
    GodotWriteToolkit,
    GodotDebugToolkit,
    GodotDocToolkit,
    GodotExecutorToolkit,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Agent Safety Constants for Monetization
MAX_AGENT_STEPS = 15  # Maximum tool calls per user request
MIN_BALANCE_FOR_STEP = 0.01  # Minimum balance ($0.01) to continue
BALANCE_CHECK_INTERVAL = 5  # Check balance every N steps

# Storage paths
GODOTY_DATA_DIR = ".godoty"
SQLITE_DB_FILE = "godoty.db"


# =============================================================================
# Enums
# =============================================================================

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


# =============================================================================
# Specialized Agents
# =============================================================================

def create_research_agent(
    model: OpenRouter,
    storage: SqliteStorage,
    memory: Memory,
    project_path: Optional[str] = None,
) -> Agent:
    """
    Create the Research Agent specialized for documentation and learning.
    
    This agent focuses on:
    - Searching Godot documentation
    - Fetching web resources
    - Understanding APIs and concepts
    """
    # Research-focused toolkits
    read_toolkit = GodotReadToolkit()
    doc_toolkit = GodotDocToolkit()
    
    # Get version-aware prompt
    godot_version = None
    try:
        from services.godot_manager import godot_manager
        status = godot_manager.get_status()
        godot_version = status.godot_version if status else None
    except Exception:
        pass
    
    base_prompt = Prompts.get_system_prompt(project_path or "", "")
    system_prompt = LearningPrompts.get_learning_prompt(base_prompt, godot_version or "4.0")
    
    return Agent(
        name="ResearchAgent",
        role="Godot Documentation and Learning Specialist",
        model=model,
        tools=[read_toolkit, doc_toolkit],
        instructions=[
            "You are a Godot documentation and research specialist.",
            "Your job is to find relevant documentation, API references, and examples.",
            "Focus on understanding concepts and gathering information.",
            "Never modify files - only read and research.",
        ],
        storage=storage,
        memory=memory,
        add_history_to_messages=True,
        num_history_responses=5,
    )


def create_planner_agent(
    model: OpenRouter,
    storage: SqliteStorage,
    memory: Memory,
    project_path: Optional[str] = None,
    project_context: Optional[str] = None,
) -> Agent:
    """
    Create the Planner Agent specialized for analysis and plan generation.
    
    This agent focuses on:
    - Analyzing project structure
    - Reading and understanding code
    - Generating detailed implementation plans
    """
    # Read-only toolkits for planning
    read_toolkit = GodotReadToolkit()
    debug_toolkit = GodotDebugToolkit()
    doc_toolkit = GodotDocToolkit()
    
    base_prompt = Prompts.get_system_prompt(project_path or "", project_context or "")
    system_prompt = PlanningPrompts.get_planning_prompt(base_prompt)
    
    return Agent(
        name="PlannerAgent",
        role="Godot Project Analyzer and Plan Generator",
        model=model,
        tools=[read_toolkit, debug_toolkit, doc_toolkit],
        instructions=[
            "You are a Godot project analyzer and planning specialist.",
            "Analyze the project structure and code to understand the context.",
            "Generate detailed, step-by-step implementation plans.",
            "Never modify files - only analyze and plan.",
            "Your plans should be clear enough for the Executor to implement.",
            "Always consider potential issues and edge cases in your plans.",
        ],
        storage=storage,
        memory=memory,
        add_history_to_messages=True,
        num_history_responses=5,
    )


def create_executor_agent(
    model: OpenRouter,
    storage: SqliteStorage,
    memory: Memory,
    project_path: Optional[str] = None,
    approved_plan: Optional[str] = None,
) -> Agent:
    """
    Create the Executor Agent specialized for implementing changes.
    
    This agent focuses on:
    - Writing and modifying code files
    - Creating and modifying scene nodes
    - Implementing approved plans
    
    Uses HITL (Human-in-the-Loop) confirmation for destructive operations.
    """
    # All toolkits including write operations
    read_toolkit = GodotReadToolkit()
    write_toolkit = GodotWriteToolkit()  # Has requires_confirmation_tools
    debug_toolkit = GodotDebugToolkit()
    executor_toolkit = GodotExecutorToolkit()  # Has requires_confirmation_tools
    
    base_prompt = Prompts.get_system_prompt(project_path or "", "")
    system_prompt = PlanningPrompts.get_execution_prompt(base_prompt, approved_plan or "")
    
    return Agent(
        name="ExecutorAgent",
        role="Godot Project Implementer",
        model=model,
        tools=[read_toolkit, write_toolkit, debug_toolkit, executor_toolkit],
        instructions=[
            "You are a Godot project implementer.",
            "Execute the approved plan step by step.",
            "Verify each change before moving to the next step.",
            "Handle errors gracefully and report issues clearly.",
            "Confirm destructive operations with the user.",
        ],
        storage=storage,
        memory=memory,
        add_history_to_messages=True,
        num_history_responses=5,
    )


# =============================================================================
# Godoty Team (Coordinator Pattern)
# =============================================================================

class GodotyTeam:
    """
    Godoty Team with Coordinator pattern for multi-agent orchestration.
    
    The team uses a coordinator model where the leader agent routes
    tasks to specialized member agents based on the task requirements:
    
    - ResearchAgent: For documentation and learning tasks
    - PlannerAgent: For analysis and plan generation
    - ExecutorAgent: For implementing approved plans
    
    Features:
    - HITL for plan approval workflow
    - SQLite session state for persistence
    - Knowledge integration with context engine
    - Metrics tracking from OpenRouter
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the Godoty Team.
        
        Args:
            session_id: Session ID for state persistence
            user_context: Authenticated user context for proxy mode
        """
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.user_context = user_context
        
        # Storage paths
        self.data_dir = Path(GODOTY_DATA_DIR)
        self.data_dir.mkdir(exist_ok=True)
        self.db_path = str(self.data_dir / SQLITE_DB_FILE)
        
        # Initialize storage and memory
        self._init_storage()
        
        # Initialize model
        self._init_model()
        
        # Project and context state
        self.project_path: Optional[str] = None
        self.context_engine = None
        self.knowledge = None
        
        # Plan state
        self._current_mode: AgentMode = AgentMode.PLANNING
        self._pending_plan: Optional[str] = None
        self._plan_state: PlanState = PlanState.NONE
        self._plan_original_request: Optional[str] = None
        
        # Create specialized agents
        self._create_agents()
        
        # Create team
        self._create_team()
        
        # Agent safety tracking
        self._step_count = 0
        self._supabase_auth = None
        self._cached_balance = None
        
        # Restore state from storage
        self._restore_state()
        
        logger.info(f"GodotyTeam initialized with session: {self.session_id}")
    
    def _init_storage(self):
        """Initialize SQLite storage and memory."""
        # SQLite storage for agent state
        self.storage = SqliteStorage(
            table_name="godoty_agent_sessions",
            db_file=self.db_path,
        )
        
        # Memory for conversation history
        self.memory_db = SqliteMemoryDb(
            table_name="godoty_memory",
            db_file=self.db_path,
        )
        self.memory = Memory(db=self.memory_db)
        
        logger.info(f"Initialized SQLite storage at: {self.db_path}")
    
    def _init_model(self):
        """Initialize the OpenRouter model."""
        config = AgentConfig.get_openrouter_config()
        
        api_key = config["api_key"]
        model_id = config["model_id"]
        
        # Determine proxy settings
        use_proxy = False
        proxy_url = None
        proxy_token = None
        
        if self.user_context and self.user_context.get("access_token"):
            use_proxy = True
            from config_manager import get_config
            app_config = get_config()
            supabase_url = app_config.get("supabase_url", "")
            if supabase_url:
                proxy_url = f"{supabase_url}/functions/v1/chat-proxy"
                proxy_token = self.user_context["access_token"]
                logger.info(f"Proxy mode enabled for user {self.user_context.get('user_id')}")
        
        # Create model config
        model_config = GodotyOpenRouterConfig(
            api_key=api_key,
            model_id=model_id,
            use_proxy=use_proxy,
            proxy_url=proxy_url,
            proxy_token=proxy_token,
        )
        
        self.model = create_godoty_model(model_config)
        
        # Store for token refresh
        self._use_proxy = use_proxy
        self._proxy_url = proxy_url
    
    def _create_agents(self):
        """Create specialized agents for the team."""
        self.research_agent = create_research_agent(
            model=self.model,
            storage=self.storage,
            memory=self.memory,
            project_path=self.project_path,
        )
        
        self.planner_agent = create_planner_agent(
            model=self.model,
            storage=self.storage,
            memory=self.memory,
            project_path=self.project_path,
        )
        
        self.executor_agent = create_executor_agent(
            model=self.model,
            storage=self.storage,
            memory=self.memory,
            project_path=self.project_path,
        )
        
        logger.info("Created specialized agents: Research, Planner, Executor")
    
    def _create_team(self):
        """Create the coordinator team."""
        # Team instructions for routing
        team_instructions = [
            "You are the Godoty AI assistant coordinator.",
            "Route tasks to the appropriate specialist:",
            "- ResearchAgent: Documentation lookup, API reference, learning concepts",
            "- PlannerAgent: Code analysis, project structure, generating plans",
            "- ExecutorAgent: Implementing changes, modifying files (after plan approval)",
            "",
            "For new requests, always start with planning before execution.",
            "Complex tasks should go through: Research → Planning → Execution",
        ]
        
        self.team = Team(
            name="GodotyTeam",
            mode="coordinator",  # Coordinator pattern
            model=self.model,
            members=[
                self.research_agent,
                self.planner_agent,
                self.executor_agent,
            ],
            instructions=team_instructions,
            storage=self.storage,
            memory=self.memory,
            show_members_responses=True,
            enable_agentic_context=True,
        )
        
        logger.info("Created GodotyTeam with coordinator pattern")
    
    def _restore_state(self):
        """Restore plan state from storage."""
        try:
            # Use storage to get session state
            state = self.storage.read(self.session_id)
            if state:
                self._pending_plan = state.get("pending_plan")
                self._plan_state = PlanState(state.get("plan_state", "none"))
                self._plan_original_request = state.get("plan_original_request")
                self._current_mode = AgentMode(state.get("current_mode", "planning"))
                
                if self._pending_plan and self._plan_state == PlanState.PENDING:
                    logger.info(f"Restored pending plan ({len(self._pending_plan)} chars)")
        except Exception as e:
            logger.warning(f"Failed to restore state: {e}")
    
    def _save_state(self):
        """Save current state to storage."""
        try:
            state = {
                "session_id": self.session_id,
                "pending_plan": self._pending_plan,
                "plan_state": self._plan_state.value,
                "plan_original_request": self._plan_original_request,
                "current_mode": self._current_mode.value,
                "project_path": self.project_path,
                "updated_at": datetime.utcnow().isoformat(),
            }
            self.storage.upsert(state, overwrite=True)
            logger.debug("Saved state to storage")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def _refresh_proxy_token(self):
        """Refresh proxy token if using proxy mode."""
        if not self._use_proxy:
            return
        
        try:
            if self._supabase_auth is None:
                from services.supabase_auth import get_supabase_auth
                self._supabase_auth = get_supabase_auth()
            
            if not self._supabase_auth.is_authenticated:
                return
            
            token = self._supabase_auth.get_access_token()
            if token:
                # Update model with new token
                new_config = GodotyOpenRouterConfig(
                    api_key=self.model.api_key,
                    model_id=self.model.id,
                    use_proxy=True,
                    proxy_url=self._proxy_url,
                    proxy_token=token,
                )
                self.model = create_godoty_model(new_config)
                logger.debug("Refreshed proxy token")
        except Exception as e:
            logger.error(f"Error refreshing proxy token: {e}")
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    async def initialize_session(self, project_path: str):
        """Initialize session with project context."""
        self.project_path = project_path
        
        # Initialize context engine
        try:
            from agents.tools import get_context_engine
            self.context_engine = get_context_engine()
            if self.context_engine:
                logger.info(f"Using context engine for: {self.context_engine.project_path}")
        except Exception as e:
            logger.warning(f"Could not get context engine: {e}")
        
        # Initialize knowledge base
        try:
            from context.agno_knowledge import GodotProjectKnowledge
            self.knowledge = GodotProjectKnowledge(project_path)
            
            # Build index if needed
            if not self.knowledge.indexed:
                await self.knowledge.build_index()
            
            # Update team with knowledge
            self.team.knowledge = self.knowledge
            logger.info("Knowledge base initialized")
        except Exception as e:
            logger.warning(f"Could not initialize knowledge: {e}")
        
        # Recreate agents with project context
        self._create_agents()
        self._create_team()
        
        # Save state
        self._save_state()
        
        logger.info(f"Initialized session {self.session_id} with project: {project_path}")
    
    async def run(
        self,
        prompt: str,
        mode: Literal["learning", "planning", "execution"] = "planning"
    ) -> Dict[str, Any]:
        """
        Run the team synchronously.
        
        Args:
            prompt: The user's request
            mode: 'learning', 'planning', or 'execution'
            
        Returns:
            Dict with response and metrics
        """
        self._refresh_proxy_token()
        
        # Set mode
        mode_enum = AgentMode(mode)
        self._current_mode = mode_enum
        
        # Select agent based on mode
        if mode_enum == AgentMode.LEARNING:
            response = await self.research_agent.arun(prompt)
        elif mode_enum == AgentMode.PLANNING:
            response = await self.planner_agent.arun(prompt)
        else:
            response = await self.executor_agent.arun(prompt)
        
        # Extract response text
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Store plan if in planning mode
        if mode == "planning":
            self.set_pending_plan(response_text, original_request=prompt)
        
        # Extract metrics
        metrics = self._extract_metrics(response)
        
        return {
            "response": response_text,
            "mode": mode,
            "has_pending_plan": self.has_pending_plan(),
            "metrics": metrics,
        }
    
    async def run_stream(
        self,
        prompt: str,
        mode: Literal["learning", "planning", "execution"] = "planning"
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Run the team with streaming.
        
        Args:
            prompt: The user's request
            mode: 'learning', 'planning', or 'execution'
            
        Yields:
            Transformed event dicts for SSE
        """
        self._refresh_proxy_token()
        
        # Set mode
        mode_enum = AgentMode(mode)
        self._current_mode = mode_enum
        
        # Reset step count
        self._step_count = 0
        collected_text = []
        
        try:
            from agents.agno_event_utils import transform_agno_event
            
            logger.info(f"[STREAM] Starting {mode} stream for session {self.session_id}")
            
            # Select agent based on mode
            if mode_enum == AgentMode.LEARNING:
                agent = self.research_agent
            elif mode_enum == AgentMode.PLANNING:
                agent = self.planner_agent
            else:
                agent = self.executor_agent
            
            # Stream the response
            async for chunk in agent.arun_stream(prompt):
                # Transform to frontend format
                transformed = transform_agno_event(chunk, mode)
                
                if transformed:
                    event_type = transformed.get("type", "unknown")
                    
                    # Track tool calls for safety
                    if event_type in ("tool_start", "tool_result"):
                        self._step_count += 1
                        
                        if self._step_count >= MAX_AGENT_STEPS:
                            yield {"type": "warning", "data": {"message": f"Reached max steps ({MAX_AGENT_STEPS})"}}
                            break
                        
                        if self._step_count % BALANCE_CHECK_INTERVAL == 0:
                            can_continue, msg = await self._check_balance()
                            if not can_continue:
                                yield {"type": "error", "data": {"error": msg, "code": 402}}
                                break
                    
                    # Collect text for plan storage
                    if event_type == "text":
                        text = transformed.get("data", {}).get("text", "")
                        if text:
                            collected_text.append(text)
                    
                    # Extract and persist metrics
                    if event_type == "metrics":
                        metrics = transformed.get("data", {}).get("metrics", {})
                        if metrics:
                            await self._persist_metrics(metrics)
                    
                    yield transformed
            
            # Store plan if in planning mode
            if mode == "planning" and collected_text:
                self.set_pending_plan("".join(collected_text), original_request=prompt)
            
        except Exception as e:
            logger.error(f"Error in stream: {e}", exc_info=True)
            yield {"type": "error", "data": {"error": str(e)}}
    
    async def approve_and_execute(
        self,
        execution_prompt: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Approve pending plan and execute it.
        
        This implements the HITL workflow where the user approves
        a generated plan before execution.
        
        Args:
            execution_prompt: Optional additional instructions
            
        Yields:
            Execution stream events
        """
        if not self._pending_plan:
            yield {"type": "error", "data": {"error": "No pending plan to execute"}}
            return
        
        # Mark approved
        self._plan_state = PlanState.APPROVED
        self._save_state()
        
        # Build execution prompt
        plan_content = self._pending_plan
        if execution_prompt:
            prompt = f"{execution_prompt}\n\n## Approved Plan:\n{plan_content}"
        else:
            prompt = f"Execute the following approved plan:\n\n{plan_content}"
        
        logger.info(f"Executing approved plan ({len(plan_content)} chars)")
        
        # Update executor with approved plan
        self.executor_agent = create_executor_agent(
            model=self.model,
            storage=self.storage,
            memory=self.memory,
            project_path=self.project_path,
            approved_plan=self._pending_plan,
        )
        
        async for event in self.run_stream(prompt, mode="execution"):
            yield event
        
        # Clear plan after execution
        self.clear_pending_plan()
    
    # =========================================================================
    # Plan Management
    # =========================================================================
    
    def get_pending_plan(self) -> Optional[str]:
        """Get the currently pending plan."""
        return self._pending_plan
    
    def get_plan_state(self) -> str:
        """Get the current plan state."""
        return self._plan_state.value
    
    def get_plan_info(self) -> Dict[str, Any]:
        """Get full plan information."""
        return {
            "plan": self._pending_plan,
            "state": self._plan_state.value,
            "original_request": self._plan_original_request,
            "has_pending_plan": self.has_pending_plan(),
        }
    
    def has_pending_plan(self) -> bool:
        """Check if there's a pending plan."""
        return self._plan_state == PlanState.PENDING and self._pending_plan is not None
    
    def set_pending_plan(self, plan: str, original_request: Optional[str] = None):
        """Set a new pending plan."""
        self._pending_plan = plan
        self._plan_state = PlanState.PENDING
        self._plan_original_request = original_request
        self._save_state()
        logger.info(f"Set pending plan ({len(plan)} chars)")
    
    def clear_pending_plan(self):
        """Clear the pending plan."""
        self._pending_plan = None
        self._plan_state = PlanState.NONE
        self._plan_original_request = None
        self._save_state()
        logger.info("Pending plan cleared")
    
    def get_current_mode(self) -> str:
        """Get the current agent mode."""
        return self._current_mode.value
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    def reset_conversation(self):
        """Reset conversation history."""
        try:
            self.memory.clear()
            logger.info(f"Conversation reset for session {self.session_id}")
        except Exception as e:
            logger.error(f"Error resetting conversation: {e}")
    
    async def on_project_connected(self, project_path: str):
        """Handle project connection."""
        await self.initialize_session(project_path)
    
    # =========================================================================
    # Metrics and Balance
    # =========================================================================
    
    def _extract_metrics(self, response: RunResponse) -> Dict[str, Any]:
        """Extract metrics from RunResponse."""
        metrics = {}
        
        if hasattr(response, 'metrics') and response.metrics:
            m = response.metrics
            metrics = {
                "input_tokens": getattr(m, 'input_tokens', 0),
                "output_tokens": getattr(m, 'output_tokens', 0),
                "total_tokens": getattr(m, 'total_tokens', 0),
                "time_to_first_token": getattr(m, 'time_to_first_token', None),
                "response_time": getattr(m, 'response_timer', None),
            }
        
        return metrics
    
    async def _persist_metrics(self, metrics: Dict[str, Any]):
        """Persist metrics to database."""
        prompt_tokens = metrics.get("input_tokens", 0)
        completion_tokens = metrics.get("output_tokens", 0)
        cost = metrics.get("cost", 0.0)
        model_id = metrics.get("model_id") or self.model.id
        
        if self.session_id and (cost > 0 or prompt_tokens + completion_tokens > 0):
            try:
                from agents.db import get_metrics_db
                db = get_metrics_db()
                db.log_api_call(
                    session_id=self.session_id,
                    model=model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost,
                )
                logger.debug(f"Metrics saved: {prompt_tokens + completion_tokens} tokens, ${cost:.6f}")
            except Exception as e:
                logger.error(f"Failed to persist metrics: {e}")
    
    async def _check_balance(self) -> tuple[bool, str]:
        """Check if user has sufficient balance."""
        try:
            if self._supabase_auth is None:
                from services.supabase_auth import get_supabase_auth
                self._supabase_auth = get_supabase_auth()
            
            if not self._supabase_auth.is_authenticated:
                return (True, "")
            
            balance = self._supabase_auth.get_balance()
            if balance is None:
                return (True, "")
            
            self._cached_balance = balance
            
            if balance < MIN_BALANCE_FOR_STEP:
                return (False, f"Insufficient credits (${balance:.4f}). Please top up.")
            
            return (True, "")
        except Exception as e:
            logger.error(f"Balance check error: {e}")
            return (True, "")


# =============================================================================
# Singleton Management
# =============================================================================

_godoty_team_instance: Optional[GodotyTeam] = None
_team_lock = threading.Lock()


def get_godoty_agent(
    session_id: Optional[str] = None,
    user_context: Optional[Dict[str, Any]] = None,
) -> "GodotyTeam":
    """
    Get or create a GodotyTeam instance.
    
    Args:
        session_id: Session ID for state persistence
        user_context: Authenticated user context for proxy mode
        
    Returns:
        GodotyTeam instance
    """
    global _godoty_team_instance
    
    with _team_lock:
        should_recreate = (
            _godoty_team_instance is None or
            (_godoty_team_instance.session_id != session_id and session_id is not None) or
            (_godoty_team_instance.user_context != user_context and user_context is not None)
        )
        
        if should_recreate:
            _godoty_team_instance = GodotyTeam(session_id, user_context)
        
        # This assertion helps type checkers understand the flow
        assert _godoty_team_instance is not None
        return _godoty_team_instance


# Backward compatibility alias
GodotyAgent = GodotyTeam
