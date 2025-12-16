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
from typing import TYPE_CHECKING

import yaml
from agno.agent import Agent, RunEvent
from agno.db.sqlite import SqliteDb
from agno.models.litellm import LiteLLM
from agno.team import Team

from app.agents.tools import (
    # Perception tools
    get_open_script,
    get_project_settings,
    get_scene_tree,
    request_screenshot,
    # Actuation tools
    create_node,
    delete_node,
    read_project_file,
    set_project_setting,
    write_project_file,
    # Knowledge & LSP tools
    query_godot_docs,
    get_symbol_info,
    get_code_completions,
)

if TYPE_CHECKING:
    from agno.run.response import RunResponse

# Load prompts from YAML files
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"

# SQLite database path for session storage
DB_DIR = Path.home() / ".godoty"
DB_PATH = DB_DIR / "data.db"


def _load_prompt(name: str) -> str:
    """Load a system prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.yaml"
    if prompt_path.exists():
        with open(prompt_path) as f:
            data = yaml.safe_load(f)
            return data.get("system", "")
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
    """Create the Observer agent specialized in perception tasks."""
    return Agent(
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
    )


def create_coder_agent() -> Agent:
    """Create the GDScript Coder agent specialized in Godot 4.x syntax."""
    return Agent(
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
            # Knowledge tools for API reference
            query_godot_docs,
            get_symbol_info,
            get_code_completions,
        ],
        description="Writes and modifies GDScript code with Godot 4.x best practices",
        expected_output="Well-formatted GDScript code with static typing, docstrings, and Godot 4.x conventions",
        markdown=True,
        retries=2,
        tool_call_limit=10,  # Coding often requires multiple file operations
    )


def create_architect_agent() -> Agent:
    """Create the Systems Architect agent for planning complex features."""
    return Agent(
        name="Systems Architect",
        role="Planning and Design Specialist",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("architect") or (
            "You are the Systems Architect agent for Godoty. Your role is to break down "
            "complex feature requests into structured, actionable steps. When asked to implement "
            "a feature like 'inventory system', decompose it into: resource definitions, "
            "script implementations, UI components, and scene setup. Output a clear task list "
            "that the Lead can delegate to specialized agents."
        ),
        tools=[read_project_file, get_scene_tree, query_godot_docs],  # Read-only tools + docs
        description="Plans and decomposes complex multi-step features",
        expected_output="Structured implementation plan with: Overview, Prerequisites, Task List, Files to Create/Modify, and Potential Challenges",
        markdown=True,
        retries=2,
        tool_call_limit=5,  # Planning is mostly reasoning, limited tool use
    )


def create_lead_agent(session_id: str | None = None) -> Agent:
    """Create the Lead Developer agent that orchestrates the team."""
    return Agent(
        name="Lead Developer",
        role="Team Coordinator",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("lead") or (
            "You are the Lead Developer agent for Godoty. "
            "Prefer state-based perception (scene tree, open script) over screenshots. "
            "Never perform project modifications without HITL approval."
        ),
        tools=[get_scene_tree, get_open_script, read_project_file],  # Read-only context gathering
        description="Orchestrates requests and coordinates the agent team",
        expected_output="Clear action plan with delegated tasks or direct helpful response",
        markdown=True,
        retries=2,
        tool_call_limit=5,
        session_id=session_id,
    )


def create_godoty_team(
    session_id: str | None = None,
    db: SqliteDb | None = None,
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

    Returns:
        An Agno Team configured for Godot development assistance
    """
    return Team(
        name="Godoty Team",
        members=[
            create_lead_agent(session_id),
            create_observer_agent(),
            create_coder_agent(),
            create_architect_agent(),
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
        add_history_to_context=True,  # Include previous conversation in context
        num_history_runs=10,  # Last 10 conversation turns
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
        
        # Set the JWT token and model globally for model creation
        set_jwt_token(jwt_token)
        set_model_id(model_id)
        
        # Create team with database for persistent session storage
        self.team = create_godoty_team(session_id, db)
        self.total_tokens = 0
        self.pending_confirmations: dict[str, dict] = {}

    async def process_message_stream(self, user_text: str):
        """Process a user message with streaming, yielding chunks as they arrive.

        This is an async generator that yields dictionaries with either:
        - {"type": "chunk", "content": "..."} for content chunks
        - {"type": "done", "content": "...", "metrics": {...}} for final result

        Args:
            user_text: The user's input text

        Yields:
            Dictionaries with chunk or final content and metrics
        """
        try:
            # Get spend before the request (for cost tracking)
            spend_before = 0.0
            try:
                spend_info = await get_key_spend_info(self.jwt_token)
                if "spend" in spend_info:
                    spend_before = spend_info["spend"]
            except Exception:
                pass  # Spend tracking is best-effort

            # Use async streaming mode with team.arun() for proper async operation
            response_stream = self.team.arun(user_text, stream=True)
            
            full_content = ""
            final_metrics = None
            
            # Iterate through the async stream
            async for chunk in response_stream:
                # Handle content chunks using RunEvent enum
                if hasattr(chunk, "event") and chunk.event == RunEvent.run_content:
                    # This is a content chunk
                    if chunk.content:
                        full_content += chunk.content
                        yield {"type": "chunk", "content": chunk.content}
                elif hasattr(chunk, "content") and chunk.content:
                    # Fallback: check for content attribute directly
                    # Calculate delta to avoid duplicates
                    new_content = chunk.content
                    if new_content.startswith(full_content):
                        delta = new_content[len(full_content):]
                    else:
                        delta = new_content
                    
                    if delta:
                        full_content = new_content
                        yield {"type": "chunk", "content": delta}
                
                # Capture metrics from the final response
                if hasattr(chunk, "metrics") and chunk.metrics:
                    final_metrics = chunk.metrics

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

            # Yield final result with full content and metrics
            yield {"type": "done", "content": full_content, "metrics": metrics_dict}

        except Exception as e:
            yield {"type": "error", "error": str(e)}

    async def process_message(self, user_text: str) -> tuple[str, dict]:
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
