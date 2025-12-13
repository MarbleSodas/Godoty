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
from agno.agent import Agent
from agno.models.litellm import LiteLLM
from agno.team import Team

from app.agents.tools import (
    get_open_script,
    get_scene_tree,
    read_project_file,
    request_screenshot,
    write_project_file,
)

if TYPE_CHECKING:
    from agno.run.response import RunResponse

# Load prompts from YAML files
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a system prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.yaml"
    if prompt_path.exists():
        with open(prompt_path) as f:
            data = yaml.safe_load(f)
            return data.get("system", "")
    return ""


def _get_model(jwt_token: str | None = None, model_id: str | None = None) -> LiteLLM:
    """Create a LiteLLM model instance configured via environment variables.
    
    Args:
        jwt_token: Optional virtual key (or JWT) for authentication with remote proxy.
                   When using secure edge functions, this should be the LiteLLM virtual key.
        model_id: Optional model ID to use (e.g., 'gpt-4o', 'claude-3-5-sonnet-20241022').
                  If not provided, uses GODOTY_MODEL env var or defaults to 'gpt-4o'.
    """
    # Remote LiteLLM proxy URL (Railway deployment)
    base_url = os.getenv(
        "GODOTY_LITELLM_BASE_URL",
        "https://litellm-production-150c.up.railway.app"
    )
    # Use provided model_id or fall back to env var / default
    resolved_model = model_id or os.getenv("GODOTY_MODEL", "gpt-4o")
    
    # Use virtual key (from edge function) or JWT token as API key for remote proxy
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


def create_observer_agent() -> Agent:
    """Create the Observer agent specialized in perception tasks."""
    return Agent(
        name="Observer",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("observer") or (
            "You are the Observer agent for Godoty. Your role is to gather context "
            "about the Godot project by analyzing screenshots, scene trees, and open scripts. "
            "Translate raw data into clear natural language descriptions for other agents. "
            "Prefer state-based perception (scene tree, scripts) over screenshots when possible."
        ),
        tools=[request_screenshot, get_scene_tree, get_open_script],
        description="Gathers visual and state context from the Godot Editor",
    )


def create_coder_agent() -> Agent:
    """Create the GDScript Coder agent specialized in Godot 4.x syntax."""
    return Agent(
        name="GDScript Coder",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("coder") or (
            "You are the GDScript Coder agent for Godoty, specialized in Godot 4.x syntax. "
            "Always use static typing (: float, : Vector2, : String, etc.) to reduce runtime errors. "
            "Follow GDScript style guide conventions. Use snake_case for functions and variables, "
            "PascalCase for classes. Prefer signals over direct method calls for loose coupling. "
            "Never modify files without explicit user approval through the HITL system."
        ),
        tools=[read_project_file, write_project_file],
        description="Writes and modifies GDScript code with Godot 4.x best practices",
    )


def create_architect_agent() -> Agent:
    """Create the Systems Architect agent for planning complex features."""
    return Agent(
        name="Systems Architect",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("architect") or (
            "You are the Systems Architect agent for Godoty. Your role is to break down "
            "complex feature requests into structured, actionable steps. When asked to implement "
            "a feature like 'inventory system', decompose it into: resource definitions, "
            "script implementations, UI components, and scene setup. Output a clear task list "
            "that the Lead can delegate to specialized agents."
        ),
        description="Plans and decomposes complex multi-step features",
    )


def create_lead_agent(session_id: str | None = None) -> Agent:
    """Create the Lead Developer agent that orchestrates the team."""
    return Agent(
        name="Lead Developer",
        model=_get_model(_current_jwt_token, _current_model_id),
        instructions=_load_prompt("lead") or (
            "You are the Lead Developer agent for Godoty. "
            "Prefer state-based perception (scene tree, open script) over screenshots. "
            "Never perform project modifications without HITL approval."
        ),
        description="Orchestrates requests and coordinates the agent team",
        session_id=session_id,
    )


def create_godoty_team(session_id: str | None = None) -> Team:
    """Create the full Godoty agent team.

    The team consists of:
    - Lead Developer: Entry point, analyzes requests and delegates
    - Observer: Gathers context via screenshots and state introspection
    - GDScript Coder: Writes and modifies code
    - Systems Architect: Plans complex features

    Args:
        session_id: Optional session ID for conversation continuity

    Returns:
        An Agno Team configured for Godot development assistance
    """
    return Team(
        name="Godoty Team",
        mode="coordinate",
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
    )


class GodotySession:
    """Manages a single Godoty conversation session.

    This class wraps an Agno Team and tracks conversation history,
    token usage, and pending HITL confirmations.
    """

    def __init__(
        self,
        session_id: str | None = None,
        jwt_token: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.jwt_token = jwt_token
        self.model_id = model_id
        
        # Set the JWT token and model globally for model creation
        set_jwt_token(jwt_token)
        set_model_id(model_id)
        
        self.team = create_godoty_team(session_id)
        self.total_tokens = 0
        self.pending_confirmations: dict[str, dict] = {}

    async def process_message(self, user_text: str) -> tuple[str, dict]:
        """Process a user message and return the response with metrics.

        Args:
            user_text: The user's input text

        Returns:
            A tuple of (response_text, metrics_dict)
        """
        try:
            response: RunResponse = self.team.run(user_text)

            # Extract metrics from response
            metrics = {}
            if hasattr(response, "metrics") and response.metrics:
                metrics = response.metrics
                if "input_tokens" in metrics:
                    self.total_tokens += metrics.get("input_tokens", 0)
                    self.total_tokens += metrics.get("output_tokens", 0)

            metrics["session_total_tokens"] = self.total_tokens

            # Get the response content
            content = ""
            if response.content:
                content = response.content
            elif response.messages:
                # Get the last assistant message
                for msg in reversed(response.messages):
                    if msg.role == "assistant" and msg.content:
                        content = msg.content
                        break

            return content, metrics

        except Exception as e:
            return f"Error processing message: {e}", {"error": str(e)}
