"""Godoty Agent Team - Agno-based multi-agent orchestration.

This module defines the agent team architecture for Godoty:
- Lead Developer: Orchestrates requests and maintains session state
- GDScript Coder: Specialized in Godot 4.x GDScript syntax
- Systems Architect: Plans complex multi-step features
- Observer: Handles perception (screenshots, scene tree analysis)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from dataclasses import dataclass, field
from agno.agent import Agent, RunEvent
from agno.db.sqlite import SqliteDb
from agno.models.litellm import LiteLLM
from agno.run.agent import (
    RunContentEvent,
    RunCompletedEvent,
    RunErrorEvent,
    ToolCallStartedEvent,
    ToolCallCompletedEvent,
    ReasoningStartedEvent,
    ReasoningStepEvent,
    ReasoningCompletedEvent,
    ReasoningContentDeltaEvent,
)
from agno.team import Team
from agno.run.team import TeamRunEvent
import logging

_logger = logging.getLogger("godoty.team")
from agno.tools.reasoning import ReasoningTools
from pydantic import BaseModel

from app.agents.schemas import ArchitecturePlan, CodeProposal, ObservationReport
from app.agents.tools import (
    # Perception tools
    get_open_script,
    get_project_settings,
    get_scene_tree,
    request_screenshot,
    # Actuation tools (Godot RPC)
    create_node,
    delete_node,
    read_project_file,
    set_project_setting,
    write_project_file,
    # Scoped file tools (direct filesystem)
    list_project_files,
    read_file,
    write_file,
    delete_file,
    file_exists,
    create_directory,
    rename_file,
    move_file,
    copy_file,
    # File discovery tools
    find_files,
    search_project_files,
    # Knowledge & LSP tools
    query_godot_docs,
    get_symbol_info,
    get_code_completions,
    # Project context
    get_project_context,
)

if TYPE_CHECKING:
    pass

PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"

DB_DIR = Path.home() / ".godoty"
DB_PATH = DB_DIR / "data.db"


@dataclass
class TeamConfig:
    """Configuration for Godoty team behavior.
    
    Controls optional features like structured output schemas.
    """
    use_structured_output: bool = False
    coder_schema: type[BaseModel] | None = None
    architect_schema: type[BaseModel] | None = None
    observer_schema: type[BaseModel] | None = None
    
    @classmethod
    def with_structured_output(cls) -> "TeamConfig":
        """Create config with structured output enabled for Coder and Architect."""
        return cls(
            use_structured_output=True,
            coder_schema=CodeProposal,
            architect_schema=ArchitecturePlan,
            observer_schema=ObservationReport,
        )


_team_config: TeamConfig = TeamConfig()


def set_team_config(config: TeamConfig) -> None:
    """Set the global team configuration."""
    global _team_config
    _team_config = config


def get_team_config() -> TeamConfig:
    """Get the current team configuration."""
    return _team_config


def _load_prompt(name: str, context: str = "") -> str:
    """Load a system prompt from the prompts directory.
    
    Supports BMAD-style context injection via {{PROJECT_CONTEXT}} placeholder.
    
    Args:
        name: The prompt name (without .yaml extension)
        context: Optional project context to inject
        
    Returns:
        The system prompt with context injected
    """
    prompt_path = PROMPTS_DIR / f"{name}.yaml"
    if prompt_path.exists():
        with open(prompt_path) as f:
            data = yaml.safe_load(f)
            prompt = data.get("system", "")
            # BMAD: Inject project context
            if context and "{{PROJECT_CONTEXT}}" in prompt:
                prompt = prompt.replace("{{PROJECT_CONTEXT}}", context)
            elif "{{PROJECT_CONTEXT}}" in prompt:
                prompt = prompt.replace("{{PROJECT_CONTEXT}}", "# No project connected yet")
            return prompt
    return ""


def get_db() -> SqliteDb:
    """Get the SQLite database instance for session storage.
    
    Creates the database directory if it doesn't exist.
    The database stores:
    - Session metadata and history
    - Agent run information
    - Conversation context for seamless resumption
    
    Returns:
        SqliteDb: Configured database instance pointing to ~/.godoty/data.db
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return SqliteDb(db_file=str(DB_PATH))


def _get_model(jwt_token: str | None = None, model_id: str | None = None) -> LiteLLM:
    """Create a LiteLLM model instance configured for the LiteLLM proxy server.
    
    This function configures Agno's LiteLLM model wrapper to connect to a remote
    LiteLLM proxy server (deployed on Railway). The proxy handles routing to
    various LLM providers (OpenRouter, OpenAI, Anthropic, etc.).
    
    Configuration Details:
    ----------------------
    - api_base: The URL of the LiteLLM proxy server. Set via GODOTY_LITELLM_BASE_URL
      environment variable or defaults to the Railway deployment.
      
    - Model ID Format: When calling a LiteLLM proxy server, the model ID must use
      the 'openai/' prefix (e.g., 'openai/GPT-OSS 120b'). This tells the underlying
      LiteLLM SDK to treat the proxy as an OpenAI-compatible endpoint and route
      requests to /chat/completions. Without this prefix, LiteLLM tries to match
      the model name to a known provider, which fails for custom proxy models.
      
    - api_key: The virtual key for authentication. The proxy validates this key
      against LiteLLM's internal key database for budget tracking and access control.
    
    Args:
        jwt_token: Optional virtual key (or JWT) for authentication with remote proxy.
                   When using secure edge functions, this should be the LiteLLM virtual key.
        model_id: Optional model ID to use. Should match model IDs from the proxy's 
                  /models endpoint (without the 'openai/' prefix - we add it automatically).
                  If not provided, uses GODOTY_MODEL env var or defaults to 'GPT-OSS 120b'.
    
    Returns:
        LiteLLM: An Agno LiteLLM model instance configured for the proxy.
        
    Environment Variables:
        GODOTY_LITELLM_BASE_URL: LiteLLM proxy server URL (default: Railway deployment)
        GODOTY_MODEL: Default model ID to use (default: 'GPT-OSS 120b')
        GODOTY_API_KEY: API key for proxy authentication (fallback if no jwt_token)
        
    Example:
        >>> model = _get_model(jwt_token="sk-user-key", model_id="gpt-4o")
        >>> # Creates LiteLLM with id="openai/gpt-4o" pointing to proxy
    """
    # Remote LiteLLM proxy URL (Railway deployment)
    # The proxy server handles routing to actual LLM providers
    base_url = os.getenv(
        "GODOTY_LITELLM_BASE_URL",
        "https://litellm-production-150c.up.railway.app"
    )
    
    # Get the model name from parameter, env var, or default
    # Model IDs should match what the proxy's /models endpoint returns
    raw_model = model_id or os.getenv("GODOTY_MODEL", "GPT-OSS 120b")
    
    # CRITICAL: When calling a LiteLLM proxy server through the LiteLLM SDK,
    # we must prefix the model with 'openai/' to indicate OpenAI-compatible routing.
    # This tells LiteLLM to send requests to {api_base}/chat/completions
    # rather than trying to determine the provider from the model name.
    # See: https://docs.litellm.ai/docs/providers/openai_compatible
    if not raw_model.startswith("openai/"):
        resolved_model = f"openai/{raw_model}"
    else:
        resolved_model = raw_model
    
    # Use virtual key (from edge function) or fallback to env var
    # The remote proxy validates this against LiteLLM's key database
    api_key = jwt_token if jwt_token else os.getenv("GODOTY_API_KEY", "sk-godoty")

    return LiteLLM(
        id=resolved_model,
        api_base=base_url,
        api_key=api_key,
    )


# Store JWT token and model for model creation in agents
_current_jwt_token: str | None = None
_current_model_id: str | None = None


def set_jwt_token(token: str | None) -> None:
    """Set the JWT/virtual key token for model authentication."""
    global _current_jwt_token
    _current_jwt_token = token


def get_jwt_token() -> str | None:
    """Get the current JWT/virtual key token."""
    return _current_jwt_token


def set_model_id(model_id: str | None) -> None:
    """Set the model ID for agent model creation."""
    global _current_model_id
    _current_model_id = model_id


def get_model_id() -> str | None:
    """Get the current model ID."""
    return _current_model_id


async def get_key_spend_info(api_key: str | None = None) -> dict:
    """Query LiteLLM /key/info endpoint to get spend data for a virtual key.
    
    This requires the virtual key to have `permissions: { get_spend_routes: true }`
    set during generation (done in the Supabase edge function).
    
    Args:
        api_key: The virtual key to query. Uses current JWT token if not provided.
        
    Returns:
        Dictionary with spend info:
        {
            "spend": float,       # Total spend in USD
            "max_budget": float,  # Budget limit (if set on key or user)
            "key_name": str,      # Key identifier
            "user_id": str,       # Associated user
            "models": list,       # Allowed models (empty = all)
        }
    """
    import httpx
    
    key = api_key or _current_jwt_token
    if not key:
        return {"error": "No API key provided"}
    
    base_url = os.getenv(
        "GODOTY_LITELLM_BASE_URL",
        "https://litellm-production-150c.up.railway.app"
    ).rstrip("/")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/key/info",
                headers={"Authorization": f"Bearer {key}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                info = data.get("info", data)
                return {
                    "spend": info.get("spend", 0.0) or 0.0,
                    "max_budget": info.get("max_budget"),
                    "key_name": info.get("key_name"),
                    "user_id": info.get("user_id"),
                    "models": info.get("models", []),
                }
            else:
                return {"error": f"HTTP {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": str(e)}


def create_observer_agent() -> Agent:
    """Create the Observer agent specialized in perception tasks.
    
    Features:
    - Gathers context from Godot Editor
    - Uses state-based perception (scene tree, scripts)
    - Provides structured observations
    """
    return Agent(
        id="observer",
        name="Observer",
        role="Perception Specialist",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("observer") or (
            "You are the Observer agent for Godoty. Your role is to gather context "
            "about the Godot project by analyzing screenshots, scene trees, and open scripts. "
            "Translate raw data into clear natural language descriptions for other agents. "
            "Prefer state-based perception (scene tree, scripts) over screenshots when possible."
        ),
        tools=[request_screenshot, get_scene_tree, get_open_script, get_project_settings],
        description="Gathers visual and state context from the Godot Editor",
        expected_output="Structured observations with: Summary, Details, Issues detected, and Suggestions",
        markdown=True,
        retries=2,
        tool_call_limit=5,
        reasoning=True,
        reasoning_min_steps=1,
        reasoning_max_steps=3,
    )


def create_coder_agent() -> Agent:
    """Create the GDScript Coder agent specialized in Godot 4.x syntax.
    
    Features:
    - Reasoning mode for better code quality
    - Tool result compression to save tokens
    - Self-review checklist in BMAD prompt
    - Optional structured output via TeamConfig
    """
    config = get_team_config()
    output_schema = config.coder_schema if config.use_structured_output else None
    
    return Agent(
        id="gdscript-coder",
        name="GDScript Coder",
        role="Code Implementation Specialist",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("coder") or (
            "You are the GDScript Coder agent for Godoty, specialized in Godot 4.x syntax. "
            "Always use static typing (: float, : Vector2, : String, etc.) to reduce runtime errors. "
            "Follow GDScript style guide conventions. Use snake_case for functions and variables, "
            "PascalCase for classes. Prefer signals over direct method calls for loose coupling. "
            "Never modify files without explicit user approval through the HITL system."
        ),
        tools=[
            read_project_file,
            write_project_file,
            create_node,
            delete_node,
            set_project_setting,
            list_project_files,
            read_file,
            write_file,
            delete_file,
            file_exists,
            create_directory,
            rename_file,
            move_file,
            copy_file,
            find_files,
            search_project_files,
            query_godot_docs,
            get_symbol_info,
            get_code_completions,
        ],
        description="Writes and modifies GDScript code with Godot 4.x best practices",
        expected_output="Well-formatted GDScript code with static typing, docstrings, and Godot 4.x conventions",
        output_schema=output_schema,
        markdown=True,
        retries=2,
        tool_call_limit=10,
        reasoning=True,
        reasoning_min_steps=2,
        reasoning_max_steps=5,
    )


def create_architect_agent(project_context: str = "") -> Agent:
    """Create the Systems Architect agent for planning complex features.
    
    Features:
    - Strong reasoning mode for planning
    - BMAD planning process and output format
    - Optional structured output via TeamConfig
    """
    config = get_team_config()
    output_schema = config.architect_schema if config.use_structured_output else None
    
    return Agent(
        id="systems-architect",
        name="Systems Architect",
        role="Planning and Design Specialist",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("architect", context=project_context) or (
            "You are the Systems Architect agent for Godoty. Your role is to break down "
            "complex feature requests into structured, actionable steps. When asked to implement "
            "a feature like 'inventory system', decompose it into: resource definitions, "
            "script implementations, UI components, and scene setup. Output a clear task list "
            "that the Lead can delegate to specialized agents."
        ),
        tools=[
            read_project_file,
            get_scene_tree,
            list_project_files,
            read_file,
            file_exists,
            find_files,
            search_project_files,
            query_godot_docs,
            get_project_context,
        ],
        description="Plans and decomposes complex multi-step features",
        expected_output="Structured implementation plan with: Overview, Prerequisites, Task List, Files to Create/Modify, and Potential Challenges",
        output_schema=output_schema,
        markdown=True,
        retries=2,
        tool_call_limit=5,
        reasoning=True,
        reasoning_min_steps=3,
        reasoning_max_steps=7,
    )


def create_lead_agent(session_id: str | None = None, project_context: str = "") -> Agent:
    """Create the Lead Developer agent that orchestrates the team.
    
    Features:
    - ReasoningTools for explicit think/analyze steps
    - Reasoning mode for decision making
    - BMAD decision tree and routing
    - User memory for personalization
    """
    reasoning_tools = ReasoningTools(
        enable_think=True,
        enable_analyze=True,
        add_instructions=True,
        add_few_shot=True,
    )
    
    return Agent(
        id="lead-developer",
        name="Lead Developer",
        role="Team Coordinator",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("lead", context=project_context) or (
            "You are the Lead Developer agent for Godoty. "
            "Prefer state-based perception (scene tree, open script) over screenshots. "
            "Never perform project modifications without HITL approval."
        ),
        tools=[
            reasoning_tools,
            get_scene_tree,
            get_open_script,
            read_project_file,
            get_project_context,
            find_files,
            search_project_files,
        ],
        description="Orchestrates requests and coordinates the agent team",
        expected_output="Clear action plan with delegated tasks or direct helpful response",
        markdown=True,
        retries=2,
        tool_call_limit=8,
        session_id=session_id,
        reasoning=True,
        reasoning_min_steps=2,
        reasoning_max_steps=5,
        enable_agentic_memory=True,
        enable_user_memories=True,
        add_memories_to_context=True,
    )


def create_godoty_team(
    session_id: str | None = None,
    db: SqliteDb | None = None,
    project_context: str = "",
) -> Team:
    """Create the full Godoty agent team.

    The team consists of:
    - Lead Developer: Entry point, analyzes requests and delegates
    - Observer: Gathers context via screenshots and state introspection
    - GDScript Coder: Writes and modifies code
    - Systems Architect: Plans complex features

    Args:
        session_id: Optional session ID for conversation continuity.
                    If provided with a db, restores previous conversation.
        db: Optional SqliteDb instance for persistent session storage.
            When provided, conversation history is saved and can be resumed.
        project_context: Optional formatted project context string for Lead/Architect.

    Returns:
        An Agno Team configured for Godot development assistance
    """
    return Team(
        name="Godoty Team",
        members=[
            create_lead_agent(session_id, project_context),
            create_observer_agent(),
            create_coder_agent(),
            create_architect_agent(project_context),
        ],
        instructions=(
            "You are Godoty, an AI assistant team for Godot game development. "
            "The Lead Developer receives user requests and coordinates the team. "
            "For perception tasks (screenshots, scene analysis), delegate to Observer. "
            "For code writing/modification, delegate to GDScript Coder. "
            "For complex feature planning, delegate to Systems Architect. "
            "Always prefer state-based context over visual context when possible. "
            "Never modify project files without user confirmation."
        ),
        model=_get_model(_current_jwt_token, _current_model_id),
        expected_output="Clear, helpful response combining team member contributions",
        markdown=True,
        retries=2,
        # Session storage configuration
        db=db,
        session_id=session_id,
        add_history_to_context=True,
        num_history_runs=10,
        read_chat_history=True,
        # Agno: Session summaries for long conversations
        enable_session_summaries=True,
        add_session_summary_to_context=True,
        # Agno: Enable memory management at team level
        enable_agentic_memory=True,
        enable_user_memories=True,
        add_memories_to_context=True,
        # Agno: Stream intermediate steps (tool calls, delegations)
        stream_intermediate_steps=True,
        stream_member_events=True,
        # Agno: Share member interactions for better coordination
        share_member_interactions=True,
        # Agno: Store member responses for debugging
        store_member_responses=True,
    )


class GodotySession:
    """Manages a single Godoty conversation session.

    This class wraps an Agno Team and tracks conversation history,
    token usage, and pending HITL confirmations. When a db is provided,
    session data is persisted to SQLite for seamless resumption.
    """

    def __init__(
        self,
        session_id: str | None = None,
        jwt_token: str | None = None,
        model_id: str | None = None,
        db: SqliteDb | None = None,
    ) -> None:
        self.session_id = session_id
        self.jwt_token = jwt_token
        self.model_id = model_id
        self.db = db
        self._project_context: str = ""
        self._team: Team | None = None
        
        # Set the JWT token and model globally for model creation
        set_jwt_token(jwt_token)
        set_model_id(model_id)
        
        self.total_tokens = 0
        self.pending_confirmations: dict[str, dict] = {}

    async def _ensure_project_context(self) -> str:
        """Get current project context, gathering fresh if not cached."""
        if not self._project_context:
            from app.agents.context import get_cached_context, format_context_for_agent
            ctx = await get_cached_context()
            if ctx:
                self._project_context = format_context_for_agent(ctx)
        return self._project_context

    async def _get_team(self) -> Team:
        """Get or create the team with project context injected."""
        if self._team is None:
            project_context = await self._ensure_project_context()
            self._team = create_godoty_team(self.session_id, self.db, project_context)
        return self._team

    @property
    def team(self) -> Team:
        """Synchronous access to team (creates without context if not yet initialized)."""
        if self._team is None:
            self._team = create_godoty_team(self.session_id, self.db, self._project_context)
        return self._team

    async def process_message_stream(self, user_text: str):
        """Process a user message with streaming, yielding chunks as they arrive.

        This is an async generator that yields dictionaries with either:
        - {"type": "chunk", "content": "..."} for content chunks
        - {"type": "reasoning_started", ...} for reasoning start
        - {"type": "reasoning", "content": "...", ...} for reasoning steps
        - {"type": "reasoning_completed", ...} for reasoning end
        - {"type": "tool_call_started", "tool": {...}} for tool call start
        - {"type": "tool_call_completed", "tool": {...}} for tool call end
        - {"type": "done", "content": "...", "metrics": {...}} for final result
        - {"type": "error", "error": "..."} for errors

        Args:
            user_text: The user's input text

        Yields:
            Dictionaries with chunk or final content and metrics
        """
        DEBUG_EVENTS = True  # Set to True for verbose event logging
        
        try:
            # Get spend before the request (for cost tracking)
            spend_before = 0.0
            try:
                spend_info = await get_key_spend_info(self.jwt_token)
                if "spend" in spend_info:
                    spend_before = spend_info["spend"]
            except Exception:
                pass  # Spend tracking is best-effort

            team = await self._get_team()
            response_stream = team.arun(user_text, stream=True, stream_events=True)
            
            full_content = ""
            final_metrics = None
            tool_calls: list[dict] = []
            reasoning_steps: list[dict] = []
            current_agent_id: str | None = None
            reasoning_started_sent = False  # Track if we've sent reasoning_started
            
            def _get_agent_display_name(agent_id: str | None) -> str:
                if not agent_id:
                    return "Team"
                name_map = {
                    "lead-developer": "Lead Developer",
                    "observer": "Observer",
                    "gdscript-coder": "GDScript Coder",
                    "systems-architect": "Systems Architect",
                }
                return name_map.get(agent_id, agent_id)
            
            async for chunk in response_stream:
                # === EXTRACT COMMON ATTRIBUTES ===
                event_agent_id = getattr(chunk, "agent_id", None)
                agent_name_attr = getattr(chunk, "agent_name", None)
                if event_agent_id:
                    current_agent_id = event_agent_id
                
                effective_agent_id = event_agent_id or current_agent_id
                effective_agent_name = agent_name_attr or _get_agent_display_name(effective_agent_id)
                
                event_type = getattr(chunk, "event", None)
                event_type_str = str(event_type) if event_type else "None"
                
                if DEBUG_EVENTS:
                    _logger.debug(f"[STREAM] event={event_type_str}, type={type(chunk).__name__}, agent={effective_agent_id}")
                
                # === CONTENT EVENTS ===
                if event_type == TeamRunEvent.run_content or event_type == RunEvent.run_content:
                    content = getattr(chunk, "content", None)
                    if DEBUG_EVENTS:
                        _logger.info(f"[STREAM] 📝 RunContent: len={len(str(content)) if content else 0}")
                    if content:
                        full_content += str(content)
                        yield {"type": "chunk", "content": str(content)}
                
                # === TOOL CALL STARTED ===
                elif event_type == TeamRunEvent.tool_call_started or event_type == RunEvent.tool_call_started:
                    tool = getattr(chunk, "tool", None)
                    if tool:
                        tool_info = {
                            "id": getattr(tool, "tool_call_id", None) or str(len(tool_calls)),
                            "name": getattr(tool, "tool_name", None) or "unknown",
                            "arguments": getattr(tool, "tool_args", None) or {},
                            "status": "running",
                            "agent_id": effective_agent_id,
                            "agent_name": effective_agent_name,
                        }
                        tool_calls.append(tool_info)
                        _logger.info(f"[STREAM] 🔧 ToolCallStarted: {tool_info['name']}")
                        yield {"type": "tool_call_started", "tool": tool_info}
                
                # === TOOL CALL COMPLETED ===
                elif event_type == TeamRunEvent.tool_call_completed or event_type == RunEvent.tool_call_completed:
                    tool = getattr(chunk, "tool", None)
                    if tool:
                        tool_id = getattr(tool, "tool_call_id", None)
                        for tc in tool_calls:
                            if tc["id"] == tool_id or (tool_id is None and tc["status"] == "running"):
                                tc["status"] = "completed"
                                tc["result"] = str(tool.result) if getattr(tool, "result", None) else None
                                _logger.info(f"[STREAM] ✅ ToolCallCompleted: {tc['name']}")
                                yield {"type": "tool_call_completed", "tool": tc}
                                break
                
                # === REASONING STARTED ===
                elif event_type == TeamRunEvent.reasoning_started or event_type == RunEvent.reasoning_started:
                    _logger.info(f"[STREAM] 🧠 ReasoningStarted: agent={effective_agent_name}")
                    reasoning_started_sent = True
                    yield {
                        "type": "reasoning_started",
                        "agent_id": effective_agent_id,
                        "agent_name": effective_agent_name,
                    }
                
                # === REASONING STEP (full step) ===
                elif event_type == TeamRunEvent.reasoning_step or event_type == RunEvent.reasoning_step:
                    reasoning_content = getattr(chunk, "reasoning_content", None) or getattr(chunk, "reasoning_step", None)
                    if reasoning_content:
                        _logger.info(f"[STREAM] 🧠 ReasoningStep: {str(reasoning_content)[:50]}...")
                        # Send reasoning_started if not yet sent
                        if not reasoning_started_sent:
                            reasoning_started_sent = True
                            yield {
                                "type": "reasoning_started",
                                "agent_id": effective_agent_id,
                                "agent_name": effective_agent_name,
                            }
                        step = {
                            "content": str(reasoning_content),
                            "agent_id": effective_agent_id,
                            "agent_name": effective_agent_name,
                        }
                        reasoning_steps.append(step)
                        yield {"type": "reasoning", **step}
                
                # === REASONING CONTENT DELTA (streaming reasoning) ===
                elif event_type == TeamRunEvent.reasoning_content_delta or event_type == RunEvent.reasoning_content_delta:
                    reasoning_content = getattr(chunk, "reasoning_content", None)
                    if reasoning_content:
                        _logger.info(f"[STREAM] 🧠 ReasoningDelta: {str(reasoning_content)[:30]}...")
                        # Send reasoning_started if not yet sent
                        if not reasoning_started_sent:
                            reasoning_started_sent = True
                            yield {
                                "type": "reasoning_started",
                                "agent_id": effective_agent_id,
                                "agent_name": effective_agent_name,
                            }
                        step = {
                            "content": str(reasoning_content),
                            "agent_id": effective_agent_id,
                            "agent_name": effective_agent_name,
                        }
                        # Only add if not duplicate of last step
                        if not reasoning_steps or reasoning_steps[-1]["content"] != step["content"]:
                            reasoning_steps.append(step)
                            yield {"type": "reasoning", **step}
                
                # === STRING-BASED FALLBACK for reasoning_content_delta ===
                elif event_type_str in ("ReasoningContentDelta", "TeamReasoningContentDelta"):
                    reasoning_content = getattr(chunk, "reasoning_content", None)
                    if reasoning_content:
                        _logger.info(f"[STREAM] 🧠 ReasoningDelta (str): {str(reasoning_content)[:30]}...")
                        if not reasoning_started_sent:
                            reasoning_started_sent = True
                            yield {
                                "type": "reasoning_started",
                                "agent_id": effective_agent_id,
                                "agent_name": effective_agent_name,
                            }
                        step = {
                            "content": str(reasoning_content),
                            "agent_id": effective_agent_id,
                            "agent_name": effective_agent_name,
                        }
                        if not reasoning_steps or reasoning_steps[-1]["content"] != step["content"]:
                            reasoning_steps.append(step)
                            yield {"type": "reasoning", **step}
                
                # === REASONING COMPLETED ===
                elif event_type == TeamRunEvent.reasoning_completed or event_type == RunEvent.reasoning_completed:
                    _logger.info(f"[STREAM] 🧠 ReasoningCompleted: agent={effective_agent_name}")
                    reasoning_started_sent = False  # Reset for next agent
                    yield {
                        "type": "reasoning_completed",
                        "agent_id": effective_agent_id,
                        "agent_name": effective_agent_name,
                    }
                
                # === RUN COMPLETED ===
                elif event_type == TeamRunEvent.run_completed or event_type == RunEvent.run_completed:
                    content = getattr(chunk, "content", None)
                    if content:
                        full_content = str(content)
                    chunk_metrics = getattr(chunk, "metrics", None)
                    if chunk_metrics:
                        final_metrics = chunk_metrics
                    _logger.info(f"[STREAM] ✅ RunCompleted: content_len={len(full_content)}")
                
                # === RUN ERROR ===
                elif event_type == RunEvent.run_error or event_type_str == "TeamRunError":
                    error_content = getattr(chunk, "content", None) or "Unknown error"
                    _logger.error(f"[STREAM] ❌ RunError: {error_content}")
                    yield {"type": "error", "error": str(error_content)}
                
                # === FALLBACK: isinstance checks for type safety ===
                elif isinstance(chunk, RunContentEvent):
                    if chunk.content:
                        full_content += str(chunk.content)
                        yield {"type": "chunk", "content": str(chunk.content)}
                
                elif isinstance(chunk, RunCompletedEvent):
                    if chunk.content:
                        full_content = str(chunk.content)
                    if chunk.metrics:
                        final_metrics = chunk.metrics
                
                elif isinstance(chunk, RunErrorEvent):
                    error_content = chunk.content or "Unknown error"
                    yield {"type": "error", "error": str(error_content)}
                
                elif isinstance(chunk, ReasoningContentDeltaEvent):
                    reasoning_content = getattr(chunk, "reasoning_content", None)
                    if reasoning_content:
                        if not reasoning_started_sent:
                            reasoning_started_sent = True
                            yield {
                                "type": "reasoning_started",
                                "agent_id": effective_agent_id,
                                "agent_name": effective_agent_name,
                            }
                        step = {
                            "content": str(reasoning_content),
                            "agent_id": effective_agent_id,
                            "agent_name": effective_agent_name,
                        }
                        if not reasoning_steps or reasoning_steps[-1]["content"] != step["content"]:
                            reasoning_steps.append(step)
                            yield {"type": "reasoning", **step}
                
                # === FALLBACK: Content with no event type ===
                elif hasattr(chunk, "content") and chunk.content and event_type is None:
                    new_content = str(chunk.content)
                    if new_content.startswith(full_content):
                        delta = new_content[len(full_content):]
                    else:
                        delta = new_content
                    
                    if delta:
                        full_content = new_content
                        yield {"type": "chunk", "content": delta}
                
                # === ALWAYS: Check for reasoning_content on any chunk ===
                chunk_reasoning = getattr(chunk, "reasoning_content", None)
                if chunk_reasoning and event_type not in [
                    RunEvent.reasoning_step, TeamRunEvent.reasoning_step,
                    RunEvent.reasoning_content_delta, TeamRunEvent.reasoning_content_delta,
                ]:
                    step = {
                        "content": str(chunk_reasoning),
                        "agent_id": effective_agent_id,
                        "agent_name": effective_agent_name,
                    }
                    if not reasoning_steps or reasoning_steps[-1]["content"] != step["content"]:
                        if not reasoning_started_sent:
                            reasoning_started_sent = True
                            yield {
                                "type": "reasoning_started",
                                "agent_id": effective_agent_id,
                                "agent_name": effective_agent_name,
                            }
                        reasoning_steps.append(step)
                        yield {"type": "reasoning", **step}
                
                # === ALWAYS: Extract metrics if present ===
                chunk_metrics = getattr(chunk, "metrics", None)
                if chunk_metrics:
                    final_metrics = chunk_metrics

            # Extract metrics from final response
            metrics_dict = {}
            if final_metrics:
                if hasattr(final_metrics, "to_dict"):
                    metrics_dict = final_metrics.to_dict()
                else:
                    metrics_dict = {
                        "input_tokens": getattr(final_metrics, "input_tokens", 0) or 0,
                        "output_tokens": getattr(final_metrics, "output_tokens", 0) or 0,
                        "total_tokens": getattr(final_metrics, "total_tokens", 0) or 0,
                    }
                
                # Accumulate total tokens for the session
                self.total_tokens += metrics_dict.get("input_tokens", 0) or 0
                self.total_tokens += metrics_dict.get("output_tokens", 0) or 0

            metrics_dict["session_total_tokens"] = self.total_tokens
            
            # Get spend after the request to calculate cost
            try:
                spend_info = await get_key_spend_info(self.jwt_token)
                if "spend" in spend_info:
                    spend_after = spend_info["spend"]
                    request_cost = spend_after - spend_before
                    metrics_dict["spend_before"] = spend_before
                    metrics_dict["spend_after"] = spend_after
                    metrics_dict["request_cost"] = request_cost
                    metrics_dict["total_spend"] = spend_after
            except Exception:
                pass  # Spend tracking is best-effort

            _logger.info(f"[STREAM] 🏁 Stream complete: content_len={len(full_content)}, reasoning_steps={len(reasoning_steps)}, tool_calls={len(tool_calls)}")

            # Yield final result with full content, metrics, and collected data
            yield {
                "type": "done",
                "content": full_content,
                "metrics": metrics_dict,
                "tool_calls": tool_calls,
                "reasoning": reasoning_steps,
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"[STREAM] ❌ Exception: {error_msg}")
            
            model_error_indicators = [
                "ServiceUnavailableError",
                "MidStreamFallbackError",
                "APIConnectionError",
                "Upstream error",
                "provider_name",
                "BadRequestError",
                "Unexpected token",
            ]
            
            if any(indicator in error_msg for indicator in model_error_indicators):
                yield {
                    "type": "error",
                    "error": "The selected model is temporarily unavailable. Please try a different model or try again later.",
                    "error_type": "model_unavailable",
                }
            else:
                yield {"type": "error", "error": error_msg}

    async def process_message(self, user_text: str) -> tuple[str, Any]:
        """Process a user message and return the response with metrics.

        This is a non-streaming version that collects the full response.
        For streaming, use process_message_stream() instead.

        Args:
            user_text: The user's input text

        Returns:
            A tuple of (response_text, metrics_dict) containing:
            - Token counts (input_tokens, output_tokens, total_tokens)
            - Session totals (session_total_tokens)
            - Cost data (spend_before, spend_after, request_cost) if available
        """
        content = ""
        metrics = {}
        
        async for chunk in self.process_message_stream(user_text):
            if chunk["type"] == "chunk":
                content += chunk["content"]
            elif chunk["type"] == "done":
                content = chunk["content"]
                metrics = chunk.get("metrics", {})
            elif chunk["type"] == "error":
                return f"Error processing message: {chunk['error']}", {"error": chunk["error"]}
        
        return content, metrics
