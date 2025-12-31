"""Godoty Agent - Unified single-agent architecture.

This module replaces the multi-agent team with a single, streamlined agent
that handles all Godot development tasks: code writing, planning, observation,
and debugging.

Key improvements over multi-agent approach:
- 80% reduction in system prompt tokens (1 agent vs 4)
- No team coordination overhead
- Simpler streaming event handling
- Direct tool access without delegation
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from agno.agent import Agent, RunEvent
from agno.db.sqlite import SqliteDb
from agno.models.litellm.litellm_openai import LiteLLMOpenAI
from agno.run.agent import (
    RunCompletedEvent,
    RunContentEvent,
    RunErrorEvent,
)

from app.agents.tools import (
    # Perception tools
    get_open_script,
    get_project_settings,
    get_scene_tree,
    request_screenshot,
    # File operations
    read_file,
    write_file,
    delete_file,
    file_exists,
    create_directory,
    rename_file,
    move_file,
    copy_file,
    # File discovery
    find_files,
    search_project_files,
    list_project_files,
    # Knowledge & LSP
    query_godot_docs,
    get_project_context,
    get_project_path,
    get_recent_errors,
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger("godoty.agent")

PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"
DB_DIR = Path.home() / ".godoty"
DB_PATH = DB_DIR / "data.db"

# Global state for authentication
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


def get_db() -> SqliteDb:
    """Get the SQLite database instance for session storage."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return SqliteDb(db_file=str(DB_PATH))


def _get_model(jwt_token: str | None = None, model_id: str | None = None) -> LiteLLMOpenAI:
    """Create a LiteLLMOpenAI model for the LiteLLM proxy."""
    base_url = os.getenv(
        "GODOTY_LITELLM_BASE_URL",
        "https://litellm-production-150c.up.railway.app"
    )
    raw_model = model_id or os.getenv("GODOTY_MODEL", "GPT-OSS 120b")
    api_key = jwt_token or os.getenv("GODOTY_API_KEY")
    if not api_key:
        raise ValueError(
            "API key is required. Set GODOTY_API_KEY environment variable "
            "or provide jwt_token parameter."
        )

    return LiteLLMOpenAI(
        id=raw_model,
        base_url=base_url,
        api_key=api_key,
    )


def _load_prompt(name: str) -> str:
    """Load a system prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.yaml"
    if prompt_path.exists():
        with open(prompt_path) as f:
            data = yaml.safe_load(f)
            return data.get("system", "")
    return ""


def _build_dynamic_prompt() -> str:
    """Build prompt with dynamic context injection.
    
    Injects:
    - Recent console errors (if any)
    - Active spec from .godoty/spec.md (if exists)
    """
    base_prompt = _load_prompt("godoty")
    
    # Inject recent errors if any
    errors = get_recent_errors(limit=5)
    if errors:
        error_lines = ["## Recent Console Errors"]
        for e in errors:
            script_info = f" in `{e.script_path}`" if e.script_path else ""
            line_info = f" (line {e.line})" if e.line else ""
            error_text = e.text[:150] + "..." if len(e.text) > 150 else e.text
            error_lines.append(f"- **{e.error_type.upper()}**{script_info}{line_info}: {error_text}")
        error_section = "\n".join(error_lines)
        base_prompt = base_prompt.replace("{{RECENT_ERRORS}}", error_section)
    else:
        base_prompt = base_prompt.replace("{{RECENT_ERRORS}}", "")
    
    # Inject active spec if exists
    project_path = get_project_path()
    if project_path:
        spec_path = Path(project_path) / ".godoty" / "spec.md"
        if spec_path.exists():
            try:
                spec_content = spec_path.read_text(encoding="utf-8")[:2000]  # Limit size
                spec_section = f"## Active Specification\n```markdown\n{spec_content}\n```"
                base_prompt = base_prompt.replace("{{ACTIVE_SPEC}}", spec_section)
            except Exception:
                base_prompt = base_prompt.replace("{{ACTIVE_SPEC}}", "")
        else:
            base_prompt = base_prompt.replace("{{ACTIVE_SPEC}}", "")
    else:
        base_prompt = base_prompt.replace("{{ACTIVE_SPEC}}", "")
    
    return base_prompt


def create_godoty_agent(
    session_id: str | None = None,
    jwt_token: str | None = None,
    model_id: str | None = None,
    db: SqliteDb | None = None,
) -> Agent:
    """Create the unified Godoty agent.
    
    A single agent that handles all Godot development tasks:
    - Code writing and modification
    - Project planning and architecture
    - Scene and script observation
    - Bug fixing and debugging
    
    Args:
        session_id: Optional session ID for conversation continuity
        jwt_token: LiteLLM virtual key for authentication
        model_id: Model to use (e.g., 'gpt-4o', 'claude-3-5-sonnet')
        db: SQLite database for session storage
        
    Returns:
        Configured Agno Agent
    """
    # Set global tokens for model creation
    set_jwt_token(jwt_token)
    set_model_id(model_id)
    
    return Agent(
        id="godoty",
        name="Godoty",
        model=_get_model(jwt_token, model_id),
        instructions=_build_dynamic_prompt(),
        tools=[
            # Perception
            get_scene_tree,
            get_open_script,
            get_project_settings,
            request_screenshot,
            # File operations
            read_file,
            write_file,
            delete_file,
            file_exists,
            create_directory,
            rename_file,
            move_file,
            copy_file,
            # File discovery
            find_files,
            search_project_files,
            list_project_files,
            # Knowledge
            query_godot_docs,
            get_project_context,
        ],
        description="AI assistant for Godot 4.x game development",
        expected_output="Clear, actionable response with code examples when appropriate",
        markdown=True,
        retries=2,
        tool_call_limit=15,
        # Session management
        session_id=session_id,
        db=db,
        # Chat history - inject previous conversation turns into context
        add_history_to_context=True,
        num_history_runs=5,
        # Reasoning for transparent thinking
        reasoning=True,
        reasoning_min_steps=2,
        reasoning_max_steps=5,
    )


async def get_key_spend_info(api_key: str | None = None) -> dict:
    """Query LiteLLM /key/info endpoint to get spend data for a virtual key."""
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


class GodotySession:
    """Manages a single Godoty conversation session.
    
    Simplified session wrapper for the unified agent architecture.
    Handles streaming, token tracking, and session persistence.
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
        self._agent: Agent | None = None
        
        self.total_tokens = 0
        self.pending_confirmations: dict[str, dict] = {}

    def _get_agent(self) -> Agent:
        """Get or create the agent."""
        if self._agent is None:
            self._agent = create_godoty_agent(
                session_id=self.session_id,
                jwt_token=self.jwt_token,
                model_id=self.model_id,
                db=self.db,
            )
        return self._agent

    @property
    def agent(self) -> Agent:
        """Synchronous access to agent."""
        return self._get_agent()

    async def process_message_stream(self, user_text: str):
        """Process a user message with streaming.
        
        Yields dictionaries with:
        - {"type": "chunk", "content": "..."} for content chunks
        - {"type": "reasoning", "content": "..."} for reasoning steps
        - {"type": "tool_call_started", "tool": {...}} for tool call start
        - {"type": "tool_call_completed", "tool": {...}} for tool call end
        - {"type": "done", "content": "...", "metrics": {...}} for final result
        - {"type": "error", "error": "..."} for errors
        """
        try:
            # Get spend before the request
            spend_before = 0.0
            try:
                spend_info = await get_key_spend_info(self.jwt_token)
                if "spend" in spend_info:
                    spend_before = spend_info["spend"]
            except Exception:
                pass

            agent = self._get_agent()
            response_stream = agent.arun(user_text, stream=True, stream_events=True)
            
            full_content = ""
            final_metrics = None
            tool_calls: list[dict] = []
            reasoning_steps: list[dict] = []
            
            async for chunk in response_stream:
                event_type = getattr(chunk, "event", None)
                
                # Content events
                if event_type == RunEvent.run_content:
                    content = getattr(chunk, "content", None)
                    if content:
                        full_content += str(content)
                        yield {"type": "chunk", "content": str(content)}
                
                # Tool call started
                elif event_type == RunEvent.tool_call_started:
                    tool = getattr(chunk, "tool", None)
                    if tool:
                        tool_info = {
                            "id": getattr(tool, "tool_call_id", None) or str(len(tool_calls)),
                            "name": getattr(tool, "tool_name", None) or "unknown",
                            "arguments": getattr(tool, "tool_args", None) or {},
                            "status": "running",
                        }
                        tool_calls.append(tool_info)
                        _logger.info(f"Tool started: {tool_info['name']}")
                        yield {"type": "tool_call_started", "tool": tool_info}
                
                # Tool call completed
                elif event_type == RunEvent.tool_call_completed:
                    tool = getattr(chunk, "tool", None)
                    if tool:
                        tool_id = getattr(tool, "tool_call_id", None)
                        for tc in tool_calls:
                            if tc["id"] == tool_id or (tool_id is None and tc["status"] == "running"):
                                tc["status"] = "completed"
                                tc["result"] = str(tool.result) if getattr(tool, "result", None) else None
                                _logger.info(f"Tool completed: {tc['name']}")
                                yield {"type": "tool_call_completed", "tool": tc}
                                break
                
                # Reasoning started
                elif event_type == RunEvent.reasoning_started:
                    yield {"type": "reasoning_started"}
                
                # Reasoning step
                elif event_type == RunEvent.reasoning_step:
                    reasoning_content = getattr(chunk, "reasoning_content", None) or getattr(chunk, "reasoning_step", None)
                    if reasoning_content:
                        step = {"content": str(reasoning_content)}
                        reasoning_steps.append(step)
                        yield {"type": "reasoning", **step}
                
                # Reasoning delta (streaming)
                elif hasattr(RunEvent, "reasoning_content_delta") and event_type == RunEvent.reasoning_content_delta:
                    reasoning_content = getattr(chunk, "reasoning_content", None)
                    if reasoning_content:
                        step = {"content": str(reasoning_content)}
                        if reasoning_steps and "content" in reasoning_steps[-1]:
                            reasoning_steps[-1]["content"] += str(reasoning_content)
                        else:
                            reasoning_steps.append(step)
                        yield {"type": "reasoning_delta", **step}
                
                # Reasoning completed
                elif event_type == RunEvent.reasoning_completed:
                    yield {"type": "reasoning_completed"}
                
                # Run completed
                elif event_type == RunEvent.run_completed:
                    content = getattr(chunk, "content", None)
                    if content:
                        full_content = str(content)
                    chunk_metrics = getattr(chunk, "metrics", None)
                    if chunk_metrics:
                        final_metrics = chunk_metrics
                
                # Run error
                elif event_type == RunEvent.run_error:
                    error_content = getattr(chunk, "content", None) or "Unknown error"
                    _logger.error(f"Run error: {error_content}")
                    yield {"type": "error", "error": str(error_content)}
                
                # Fallback: isinstance checks
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
                
                # Check for metrics on any chunk
                chunk_metrics = getattr(chunk, "metrics", None)
                if chunk_metrics:
                    final_metrics = chunk_metrics

            # Extract metrics
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
                
                self.total_tokens += metrics_dict.get("input_tokens", 0) or 0
                self.total_tokens += metrics_dict.get("output_tokens", 0) or 0

            metrics_dict["session_total_tokens"] = self.total_tokens
            
            # Get spend after request
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
                pass

            _logger.info(f"Stream complete: content_len={len(full_content)}, reasoning_steps={len(reasoning_steps)}, tool_calls={len(tool_calls)}")

            yield {
                "type": "done",
                "content": full_content,
                "metrics": metrics_dict,
                "tool_calls": tool_calls,
                "reasoning": reasoning_steps,
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Exception: {error_msg}")
            
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
        
        Non-streaming version that collects the full response.
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


# Export DB_PATH for backwards compatibility
__all__ = [
    "DB_DIR",
    "DB_PATH",
    "GodotySession",
    "create_godoty_agent",
    "get_db",
    "get_key_spend_info",
    "set_jwt_token",
    "get_jwt_token",
    "set_model_id",
    "get_model_id",
]
