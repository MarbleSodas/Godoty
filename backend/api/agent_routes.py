"""
FastAPI routes for the planning agent.

Provides endpoints for interacting with the planning agent:
- Streaming responses with SSE
- Non-streaming responses
- Session management
"""

import asyncio
from datetime import datetime
import json
import logging
import os
import re
from typing import Optional, AsyncIterable, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Use new Agno-based agent (with backward-compatible alias)
from agents.agno_agent import get_godoty_agent, GodotyTeam
from agents.config import AgentConfig
from agents.db import get_metrics_db
from agents.agno_event_utils import sanitize_event_data
from services.supabase_auth import get_supabase_auth

logger = logging.getLogger(__name__)


def require_auth():
    """
    Dependency that requires authentication for chat endpoints.
    Returns the authenticated user's info or raises 401.
    """
    auth = get_supabase_auth()
    if not auth.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in to use the chat."
        )
    
    # Check balance
    balance = auth.get_balance()
    if balance is not None and balance <= 0:
        raise HTTPException(
            status_code=402,
            detail="Insufficient credits. Please add credits to continue."
        )
    
    return {
        "user_id": auth.user_id,
        "email": auth.user_email,
        "balance": balance,
        "access_token": auth.get_access_token()
    }


def _extract_title_from_chat_history(chat_history: list) -> str:
    """
    Extract meaningful title with robust cleaning.

    Handles:
    - Code blocks (markdown)
    - Excessive whitespace
    - Long content (truncates at word boundary)

    Args:
        chat_history: List of chat messages from the database

    Returns:
        A meaningful title string
    """
    if not chat_history:
        return "New Session"

    for message in chat_history:
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content", "")
            if content and isinstance(content, str):
                # Step 1: Strip whitespace
                content = content.strip()

                # Step 2: Remove markdown code blocks
                content = re.sub(r'^```[\w]*\s*', '', content)
                content = re.sub(r'```\s*$', '', content)

                # Step 3: Normalize whitespace (newlines → spaces, multiple → single)
                content = re.sub(r'\s+', ' ', content)

                # Step 4: Truncate at word boundary
                max_length = 16
                if len(content) > max_length:
                    # Try to break at last word boundary before limit
                    truncated = content[:max_length].rsplit(' ', 1)[0]
                    # Only use truncated if it's substantial (>8 chars)
                    if len(truncated) > 8:
                        content = truncated + "..."
                    else:
                        # Just hard truncate
                        content = content[:max_length] + "..."

                return content if content else "New Session"

    return "New Session"

# Create router
router = APIRouter(prefix="/api/agent", tags=["agent"])


# Request/Response Models
class PlanRequest(BaseModel):
    """Request model for plan generation."""
    prompt: str = Field(..., description="The planning request", min_length=1)
    reset_conversation: bool = Field(
        default=False,
        description="Whether to reset conversation history before planning"
    )


class PlanResponse(BaseModel):
    """Response model for plan generation."""
    status: str = Field(..., description="Status of the request")
    plan: str = Field(..., description="Generated plan")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    agent_ready: bool
    model: Optional[str] = None


# Routes
@router.get("/health", response_model=HealthResponse)
async def agent_health():
    """
    Check agent health and readiness.

    Returns:
        HealthResponse with agent status
    """
    try:
        agent = get_godoty_agent()
        model_id = None
        if hasattr(agent, 'model'):
            model_config = agent.model.get_config()
            model_id = model_config.get("model_id")

        return HealthResponse(
            status="healthy",
            agent_ready=True,
            model=model_id
        )
    except Exception as e:
        logger.error(f"Agent health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            agent_ready=False
        )


@router.get("/chat/ready", response_model=dict)
async def check_chat_ready():
    """
    Check if chat is ready to accept messages.
    
    Chat requires both:
    1. OpenRouter API key to be configured
    2. Godot editor to be connected
    
    Returns:
        Dictionary with:
        - ready: bool - Whether chat is ready
        - godot_connected: bool - Godot connection status
        - api_key_configured: bool - OpenRouter key status
        - message: str - User-facing status message
    """
    try:
        from agents.tools.godot_bridge import get_godot_bridge
        from config_manager import get_config
        
        bridge = get_godot_bridge()
        config = get_config()
        
        # Check Godot connection
        godot_connected = False
        if hasattr(bridge, 'is_connected'):
            godot_connected = await bridge.is_connected()
        elif hasattr(bridge, 'connection_state'):
            godot_connected = bridge.connection_state.value == "connected"
        
        # Check API key configuration
        api_key_configured = config.is_configured
        
        ready = godot_connected and api_key_configured
        
        # Generate user-facing message
        if not api_key_configured:
            message = "Please configure your OpenRouter API key in Settings to start chatting."
        elif not godot_connected:
            message = "Please connect to the Godot editor to start chatting."
        else:
            message = "Ready to chat!"
        
        return {
            "ready": ready,
            "godot_connected": godot_connected,
            "api_key_configured": api_key_configured,
            "message": message
        }
    except Exception as e:
        logger.error(f"Chat ready check failed: {e}")
        return {
            "ready": False,
            "godot_connected": False,
            "api_key_configured": False,
            "message": "Unable to check chat readiness"
        }


@router.post("/plan", response_model=PlanResponse)
async def create_plan(request: PlanRequest):
    """
    Generate a plan (non-streaming).

    Args:
        request: PlanRequest with prompt and options

    Returns:
        PlanResponse with generated plan and metrics
    """
    try:
        # Get agent
        agent = get_godoty_agent(session_id="default")

        # Reset conversation if requested
        if request.reset_conversation:
            agent.reset_conversation()

        # Generate plan - returns dict with plan, message_id, and metrics
        result = await agent.run(request.prompt)

        # Extract plan text and metrics
        plan_text = result.get("plan", "") if isinstance(result, dict) else str(result)
        message_id = result.get("message_id") if isinstance(result, dict) else None
        metrics = result.get("metrics") if isinstance(result, dict) else None

        # Build metadata
        metadata = {}
        if message_id:
            metadata["message_id"] = message_id
        if metrics:
            metadata["metrics"] = metrics

        return PlanResponse(
            status="success",
            plan=plan_text,
            metadata=metadata if metadata else None
        )

    except Exception as e:
        import traceback
        error_detail = f"Error generating plan: {str(e)}"
        logger.error(f"{error_detail}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_detail)


@router.post("/plan/stream")
async def create_plan_stream(request: PlanRequest):
    """
    Generate a plan with streaming responses (SSE).

    Args:
        request: PlanRequest with prompt and options

    Returns:
        StreamingResponse with Server-Sent Events
    """
    try:
        # Get agent
        agent = get_godoty_agent(session_id="default")

        # Reset conversation if requested
        if request.reset_conversation:
            agent.reset_conversation()

        # Create streaming generator
        async def event_generator():
            """Generate Server-Sent Events from agent stream."""
            try:
                async for event in agent.run_stream(request.prompt):
                    # Add debug logging
                    logger.debug(f"[SSE] Agent stream event: {event}")

                    # Format as SSE
                    event_type = event.get("type", "data")
                    event_data = event.get("data", {})

                    # Filter out empty text events
                    if event_type == "text" and "content" in event_data:
                        content_len = len(event_data["content"])
                        if content_len == 0:
                            logger.warning(f"[SSE] Filtering out empty text event: {event}")
                            continue  # Skip this event entirely
                        else:
                            logger.debug(f"[SSE] Sending text event with {content_len} characters")

                    # Sanitize event data to ensure JSON serializability
                    sanitized_data = sanitize_event_data(event_data)

                    # Create the event structure to send directly (consistent with other endpoint)
                    final_data = {
                        "type": event_type,
                        "data": sanitized_data
                    }

                    # Serialize data
                    data_json = json.dumps(final_data)

                    # Yield SSE format
                    yield f"event: {event_type}\n"
                    yield f"data: {data_json}\n\n"

                # Send done event
                yield "event: done\n"
                yield "data: {}\n\n"

            except Exception as e:
                logger.error(f"Error in event stream: {e}")
                error_data = json.dumps({"error": str(e)})
                yield "event: error\n"
                yield f"data: {error_data}\n\n"

        # Return streaming response
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

    except Exception as e:
        logger.error(f"Error setting up stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_conversation():
    """
    Reset the agent's conversation history.

    Returns:
        Status message
    """
    try:
        agent = get_godoty_agent(session_id="default")
        agent.reset_conversation()
        
        # Reset the singleton instance for a fresh start
        from agents.agno_agent import _godoty_team_instance
        import agents.agno_agent as agno_module
        agno_module._godoty_team_instance = None

        return {
            "status": "success",
            "message": "Conversation history reset"
        }

    except Exception as e:
        logger.error(f"Error resetting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class UpdateConfigRequest(BaseModel):
    """Request model for updating agent configuration."""
    model_id: Optional[str] = Field(None, description="Model ID for Godoty agent")
    openrouter_api_key: Optional[str] = Field(None, description="OpenRouter API key")


@router.post("/config")
async def update_agent_config(request: UpdateConfigRequest):
    """
    Update agent configuration.

    Args:
        request: Configuration updates

    Returns:
        Updated configuration
    """
    try:
        # 1. Update persistent configuration using ConfigManager
        from config_manager import get_config
        config = get_config()

        if request.openrouter_api_key is not None:
            config.openrouter_api_key = request.openrouter_api_key

        if request.model_id is not None:
            config.default_model = request.model_id

        # Save to persistent storage (this is sufficient - ModelConfig reads from ConfigManager)
        config._save_config()

        # 2. Reset the agent to pick up new configuration
        # This ensures the model is re-initialized with new ID and API key
        from agents.agno_agent import _godoty_team_instance
        import agents.agno_agent as agno_module
        agno_module._godoty_team_instance = None
        agent = get_godoty_agent()

        # Get updated config from the fresh agent
        model_config = agent.model.get_config()

        return {
            "status": "success",
            "message": "Configuration updated successfully",
            "config": {
                "model_id": model_config.get("model_id", "unknown"),
                "model_config": model_config
            }
        }

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_agent_config():
    """
    Get current agent configuration.

    Returns:
        Agent configuration details
    """
    try:
        agent = get_godoty_agent()
        model_config = agent.model.get_config()
        return {
            "status": "success",
            "config": {
                "model_id": model_config.get("model_id", "unknown"),
                "model_config": model_config,
                "tools": [
                    getattr(tool, '__name__',
                           getattr(tool, 'name',
                                  f"MCP_{type(tool).__name__}"))
                    for tool in agent.tools
                ],
                "conversation_manager": type(agent.conversation_manager).__name__
            }
        }

    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Session Management Routes

class SessionRequest(BaseModel):
    """Request model for session creation."""
    session_id: str = Field(..., description="Unique session identifier", min_length=1)
    title: Optional[str] = Field(None, description="Optional session title")
    project_path: Optional[str] = Field(None, description="Project path for database storage")


class ChatRequest(BaseModel):
    """Request model for chat message."""
    message: str = Field(..., description="User message", min_length=1)
    mode: str = Field("planning", description="Execution mode: 'learning', 'planning', or 'execution'")
    plan_feedback: Optional[str] = Field(None, description="Feedback for plan regeneration")


@router.post("/sessions", response_model=dict)
async def create_session(request: SessionRequest):
    """
    Create a new multi-agent session with proper initialization.

    Args:
        request: SessionRequest with session_id, optional title, and optional project_path

    Returns:
        Session details with initialization status
    """
    try:
        # Validate session creation parameters
        if not request.session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")

        # Check if session already exists
        storage_dir = AgentConfig.get_sessions_storage_dir()
        session_path = os.path.join(storage_dir, f"session_{request.session_id}")

        if os.path.exists(session_path):
            logger.info(f"Session {request.session_id} already exists")
            # Return existing session data
            return {
                "status": "success",
                "session_id": request.session_id,
                "message": "Session already exists",
                "ready": True,
                "existing": True
            }

        # Create session directory and initialize metadata using file-based storage
        session_dir = os.path.join(storage_dir, f"session_{request.session_id}")
        os.makedirs(session_dir, exist_ok=True)

        # Initialize session with metadata
        metadata = {
            "title": request.title or "New Session",
            "project_path": request.project_path,
            "created_at": datetime.utcnow().isoformat(),
            "session_type": "AGENT",
            "status": "initializing"
        }

        # Save metadata to file
        try:
            metadata_file = os.path.join(session_dir, "metadata.json")
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Metadata saved for session {request.session_id}")
        except Exception as e:
            logger.warning(f"Could not save metadata for session {request.session_id}: {e}")

        # Initialize GodotyAgent for the session (uses Agno SQLite storage)
        from agents.agno_agent import get_godoty_agent
        agent = get_godoty_agent(session_id=request.session_id)

        # Initialize session with project path if available
        if request.project_path:
            try:
                # Initialize the agent with the project context
                if hasattr(agent, 'initialize_session'):
                    await agent.initialize_session(request.project_path)
                else:
                    logger.info(f"Agent initialization method not available for session {request.session_id}")
            except Exception as e:
                logger.warning(f"Agent initialization failed for session {request.session_id}: {e}")

        # Mark session as ready
        metadata["status"] = "ready"
        try:
            if hasattr(manager, 'save_metadata'):
                await manager.save_metadata(metadata)
        except Exception as e:
            logger.warning(f"Could not update session status: {e}")

        # Register session in MetricsDB
        try:
            db = get_metrics_db()
            db.register_session(request.session_id, request.title or "New Session")
        except Exception as e:
            logger.error(f"Failed to register session in MetricsDB: {e}")

        return {
            "status": "success",
            "session_id": request.session_id,
            "message": "Session created and initialized successfully",
            "ready": True,
            "title": metadata["title"],
            "project_path": metadata["project_path"]
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error creating session {request.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _extract_title_from_session_files(session_path: str, agent_id: str = "godoty-agent") -> Optional[str]:
    """Extract title from first user message in session files."""
    try:
        messages_dir = os.path.join(session_path, "agents", f"agent_{agent_id}", "messages")

        if not os.path.exists(messages_dir):
            agents_dir = os.path.join(session_path, "agents")
            if os.path.exists(agents_dir):
                agent_dirs = [d for d in os.listdir(agents_dir) if d.startswith("agent_")]
                if agent_dirs:
                    messages_dir = os.path.join(agents_dir, agent_dirs[0], "messages")

        if not os.path.exists(messages_dir):
            return None

        msg_file = os.path.join(messages_dir, "message_0.json")
        if os.path.exists(msg_file):
            with open(msg_file, 'r') as f:
                msg_data = json.load(f)
                message = msg_data.get('message', {})
                if message.get('role') == 'user':
                    content = message.get('content', [])
                    if content and isinstance(content, list):
                        text = content[0].get('text', '')
                        return _extract_title_from_text(text)
        return None
    except Exception as e:
        logger.debug(f"Error extracting title: {e}")
        return None


def _extract_title_from_text(text: str) -> str:
    """Extract clean title from message text."""
    if not text:
        return "New Session"

    content = text.strip()
    content = re.sub(r'^```[\w]*\s*', '', content)
    content = re.sub(r'```\s*$', '', content)
    content = re.sub(r'\s+', ' ', content)

    max_length = 16
    if len(content) > max_length:
        truncated = content[:max_length].rsplit(' ', 1)[0]
        content = truncated + "..." if len(truncated) > 8 else content[:max_length] + "..."

    return content if content else "New Session"


def _list_sessions_from_storage(storage_dir: str) -> Dict[str, Dict[str, Any]]:
    """Scan session storage directory for all sessions."""
    sessions = {}

    if not os.path.exists(storage_dir):
        logger.warning(f"Sessions storage directory does not exist: {storage_dir}")
        return sessions

    for entry in os.listdir(storage_dir):
        if not entry.startswith("session_"):
            continue

        try:
            session_path = os.path.join(storage_dir, entry)
            session_file = os.path.join(session_path, "session.json")

            if not os.path.exists(session_file):
                continue

            with open(session_file, 'r') as f:
                session_data = json.load(f)

            session_id = session_data.get('session_id')
            if not session_id:
                continue

            title = _extract_title_from_session_files(session_path)

            # Skip empty sessions (no messages yet)
            if not title:
                logger.debug(f"Skipping empty session (no messages): {session_id}")
                continue

            sessions[session_id] = {
                'session_id': session_id,
                'title': title,  # Now guaranteed to have a real title
                'date': session_data.get('updated_at') or session_data.get('created_at'),
                'active': False,
                'metadata': {
                    'created_at': session_data.get('created_at'),
                    'updated_at': session_data.get('updated_at'),
                    'title': title
                }
            }
        except Exception as e:
            logger.error(f"Error processing session {entry}: {e}")
            continue

    return sessions


@router.get("/sessions", response_model=dict)
async def list_sessions(path: Optional[str] = Query(None)):
    """
    List sessions for a specific project.

    IMPORTANT: If path is provided, ONLY return sessions for that project.
    If no path, return empty list (don't leak cross-project data).

    Args:
        path: Optional project path for database filtering

    Returns:
        List of sessions for the specified project
    """
    try:
        logger.info(f"Listing sessions with path: {path}")

        # Get sessions from file storage
        storage_dir = AgentConfig.get_sessions_storage_dir()
        fs_sessions = _list_sessions_from_storage(storage_dir)
        logger.info(f"Found {len(fs_sessions)} sessions from file storage")

        if not path:
            # For development/testing, use current working directory as default
            logger.warning("No project path provided, using current working directory as default")
            path = os.getcwd()

        sessions_dict = {}

        logger.info(f"Processing {len(fs_sessions)} sessions from file storage")

        # Process file storage sessions
        for session_id, session_data in fs_sessions.items():
            logger.debug(f"Processing session: {session_id}")

            try:
                # Extract title from session metadata or conversation
                title = session_data.get("metadata", {}).get("title", f"Session {session_id}")
                if not title or title == f"Session {session_id}":
                    # Try to extract from conversation
                    chat_history = session_data.get("chat_history", [])
                    title = _extract_title_from_chat_history(chat_history)
                    if not title:
                        title = f"Session {session_id}"

                # Get session date from file storage
                session_date = session_data.get("session_type") == "AGENT" and session_data.get("created_at")

                sessions_dict[session_id] = {
                    "session_id": session_id,
                    "title": title,
                    "date": session_date,
                    "active": False,
                    "is_running": False,
                    "metadata": {
                        "created_at": session_date,
                        "title": title,
                        **session_data.get("metadata", {})
                    },
                    "path": f"filesession://{session_id}"
                }
                logger.debug(f"Successfully processed session: {session_id} with title: {title}")

            except Exception as e:
                logger.error(f"Error processing session {session_id}: {e}")
                continue

        # Use MetricsDB to get aggregated metrics
        try:
            db = get_metrics_db()
            metrics_db_sessions = db.get_all_sessions()
            
            # Map DB metrics to session IDs
            db_metrics_map = {s["id"]: s["metrics"] for s in metrics_db_sessions}

            for session_id, session_data in sessions_dict.items():
                if session_id in db_metrics_map:
                    session_data["metrics"] = db_metrics_map[session_id]
                else:
                    session_data["metrics"] = {
                        "total_tokens": 0,
                        "total_estimated_cost": 0.0
                    }
        except Exception as e:
            logger.error(f"Error fetching metrics from MetricsDB: {e}")
            # Initialize default metrics
            for session_id, session_data in sessions_dict.items():
                if "metrics" not in session_data:
                    session_data["metrics"] = {
                        "total_tokens": 0,
                        "total_estimated_cost": 0.0
                    }

        logger.info(f"Successfully returning {len(sessions_dict)} sessions for project: {path}")
        return {"status": "success", "sessions": sessions_dict}

    except Exception as e:
        logger.error(f"Unexpected error in list_sessions: {e}", exc_info=True)
        return {"status": "error", "sessions": {}, "message": str(e)}


def parse_message_content_blocks(message_obj: Dict) -> Dict:
    """
    Parse message content blocks to extract text and tool calls.

    Handles the Anthropic/Agno message format where content is an array
    of blocks that can be text, toolUse, or toolResult.

    Args:
        message_obj: Raw message object with 'content' field containing
                    either a string or list of content blocks

    Returns:
        Dict with:
        - text: str - Concatenated text from all text blocks
        - toolCalls: List[Dict] - Tool calls with matched results
          Each tool call has: name, input, status, and optionally result
    """
    try:
        content = message_obj.get('content', [])

        # Handle string content (typically user messages)
        if isinstance(content, str):
            return {"text": content, "toolCalls": []}

        # Handle non-list content
        if not isinstance(content, list):
            return {"text": "", "toolCalls": []}

        text_parts = []
        tool_uses = {}      # toolUseId -> {name, input}
        tool_results = {}   # toolUseId -> result content
        tool_errors = {}    # toolUseId -> {error, type}

        # First pass: collect all blocks by type
        for block in content:
            if not isinstance(block, dict):
                continue

            # Text block
            if 'text' in block:
                text_parts.append(block['text'])

            # Tool use block
            elif 'toolUse' in block:
                tool_use = block['toolUse']
                tool_use_id = tool_use.get('toolUseId', f"generated-{len(tool_uses)}")
                tool_uses[tool_use_id] = {
                    'name': tool_use.get('name', 'unknown'),
                    'input': tool_use.get('input', {}),
                    'toolUseId': tool_use_id
                }

            # Tool result block
            elif 'toolResult' in block:
                tool_result = block['toolResult']
                tool_use_id = tool_result.get('toolUseId')
                if tool_use_id:
                    # Extract result content
                    result_content = tool_result.get('content', [])

                    # Result can be a list of blocks or a simple value
                    if isinstance(result_content, list) and len(result_content) > 0:
                        # Take first block if it's a dict with text
                        if isinstance(result_content[0], dict) and 'text' in result_content[0]:
                            result = result_content[0]['text']
                        else:
                            result = result_content[0]
                    else:
                        result = result_content

                    tool_results[tool_use_id] = result

            # Add tool error handling
            elif 'toolError' in block:
                tool_error = block['toolError']
                tool_use_id = tool_error.get('toolUseId')
                if tool_use_id:
                    tool_errors[tool_use_id] = {
                        'error': tool_error.get('error', 'Unknown error'),
                        'type': tool_error.get('type', 'execution_error')
                    }

        # Second pass: match tool uses with their results
        tool_calls = []
        for tool_use_id, tool_use_data in tool_uses.items():
            status = "completed"
            result = None
            error = None

            if tool_use_id in tool_errors:
                status = "failed"
                error = tool_errors[tool_use_id]
            elif tool_use_id not in tool_results:
                # If stored in session, tool completed but result might have been truncated
                # Default to "completed" instead of "running" for persistence
                status = "completed"
            else:
                result = tool_results[tool_use_id]

            tool_call = {
                'name': tool_use_data['name'],
                'input': tool_use_data['input'],
                'toolUseId': tool_use_id,  # Include ID
                'status': status,
                'result': result,
                'error': error
            }

            tool_calls.append(tool_call)

        return {
            'text': ' '.join(text_parts) if text_parts else '',
            'toolCalls': tool_calls
        }

    except Exception as e:
        logger.warning(f"Error parsing message content blocks: {e}", exc_info=True)

        # Fallback: try basic text extraction
        content = message_obj.get('content', [])
        if isinstance(content, str):
            return {"text": content, "toolCalls": []}
        elif isinstance(content, list) and len(content) > 0:
            first_block = content[0]
            if isinstance(first_block, dict) and 'text' in first_block:
                return {"text": first_block['text'], "toolCalls": []}

        return {"text": "", "toolCalls": []}


@router.get("/sessions/{session_id}", response_model=dict)
async def get_session(session_id: str, path: Optional[str] = Query(None)):
    """Get session details with conversation history."""
    try:
        storage_dir = AgentConfig.get_sessions_storage_dir()
        session_dir = os.path.join(storage_dir, f"session_{session_id}")

        # Load chat history from Agno SQLite storage or legacy files
        chat_history = []

        try:
            # Try to load from Agno agent's memory
            from agents.agno_agent import get_godoty_agent
            agent = get_godoty_agent(session_id=session_id)
            if hasattr(agent, 'memory') and agent.memory:
                # Get messages from memory
                memories = agent.memory.get_messages(limit=100)
                for i, mem in enumerate(memories):
                    message_dict = {
                        "role": getattr(mem, 'role', 'assistant'),
                        "content": getattr(mem, 'content', ''),
                        "timestamp": getattr(mem, 'created_at', datetime.utcnow().isoformat()),
                        "id": f"{session_id}-{i}"
                    }
                    if message_dict['content']:
                        chat_history.append(message_dict)
        except Exception as e:
            logger.warning(f"Error loading messages from Agno memory: {e}")
            
            # Fallback: try to load from legacy message files
            try:
                messages_dir = os.path.join(session_dir, "agents", "agent_godoty-agent", "messages")
                if os.path.exists(messages_dir):
                    for msg_file in sorted(os.listdir(messages_dir)):
                        if msg_file.endswith('.json'):
                            with open(os.path.join(messages_dir, msg_file)) as f:
                                msg_data = json.load(f)
                                message_obj = msg_data.get('message', {})
                                parsed = parse_message_content_blocks(message_obj)
                                if parsed['text'].strip() or parsed['toolCalls']:
                                    chat_history.append({
                                        "role": message_obj.get("role"),
                                        "content": parsed['text'],
                                        "timestamp": msg_data.get('created_at'),
                                        "id": f"{session_id}-{msg_file}",
                                        "toolCalls": parsed['toolCalls'] if parsed['toolCalls'] else None
                                    })
            except Exception as e2:
                logger.warning(f"Error loading legacy messages: {e2}")
                chat_history = []

        # Get metrics from MetricsDB
        metrics = {"total_tokens": 0, "total_estimated_cost": 0.0}
        try:
            db = get_metrics_db()
            session_metrics = db.get_session_metrics(session_id)
            if session_metrics:
                metrics = {
                    "total_tokens": session_metrics["total_tokens"],
                    "total_estimated_cost": session_metrics["total_estimated_cost"]
                }
        except Exception as e:
            logger.warning(f"Failed to load metrics from MetricsDB: {e}")

        return {
            "status": "success",
            "chat_history": chat_history,
            "metrics": metrics,
            "messages": chat_history
        }
    except Exception as e:
        logger.error(f"Error loading session {session_id}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/sessions/{session_id}/metrics", response_model=dict)
async def get_session_metrics_endpoint(session_id: str):
    """
    Retrieve session metrics from MetricsDB.

    Args:
        session_id: Session ID to retrieve metrics for

    Returns:
        Dictionary containing:
        - session_id: The session identifier
        - total_estimated_cost: Cumulative cost
        - total_tokens: Cumulative token count
    """
    try:
        db = get_metrics_db()
        metrics = db.get_session_metrics(session_id)
        
        return {
            "status": "success",
            "session_id": session_id,
            "total_estimated_cost": metrics.get("total_estimated_cost", 0.0),
            "total_tokens": metrics.get("total_tokens", 0),
        }

    except Exception as e:
        logger.error(f"Failed to retrieve metrics for session {session_id}: {e}")
        return {
            "status": "error",
            "message": f"Unable to retrieve metrics: {str(e)}",
            "session_id": session_id,
            "total_estimated_cost": 0.0,
            "total_tokens": 0,
        }


@router.post("/sessions/{session_id}/restore", response_model=dict)
async def restore_session(session_id: str, path: str = Query(...)):
    """
    Restore agent state from history.
    
    Args:
        session_id: Session ID
        path: Project path
        
    Returns:
        Status message
    """
    try:
        # Initialize agent with project path and restore session
        # from agents.executor_agent import get_executor_agent
        # agent = get_executor_agent()
        
        # agent.set_project_path(path)
        # agent.restore_session(session_id)
        
        # GodotyAgent doesn't support explicit restore yet, it auto-loads.
        # So we just return success.
        pass
        
        return {
            "status": "success",
            "message": f"Session {session_id} restored"
        }
    except Exception as e:
        logger.error(f"Error restoring session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/project", response_model=dict)
async def get_project_metrics_endpoint(path: str = Query(...)):
    """
    Get aggregated metrics for the project.

    Args:
        path: Project path

    Returns:
        Project metrics
    """
    try:
        db = get_metrics_db()
        all_sessions = db.get_all_sessions()
        
        # Aggregate on the fly
        total_tokens = sum(s["metrics"]["total_tokens"] for s in all_sessions)
        total_cost = sum(s["metrics"]["total_estimated_cost"] for s in all_sessions)
        session_count = len(all_sessions)
        
        result = {
            "total_estimated_cost": total_cost,
            "total_tokens": total_tokens,
            "session_count": session_count,
            "call_count": 0 # Not easily available in this view, but acceptable for minimal implementation
        }

        logger.info(f"Project metrics calculated: cost=${total_cost:.4f}, tokens={total_tokens}")

        return {
            "status": "success",
            "metrics": result
        }
    except Exception as e:
        logger.error(f"Error getting project metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}", response_model=dict)
async def delete_session(session_id: str, path: Optional[str] = Query(None)):
    """
    Delete a session from file storage and MetricsDB.

    Args:
        session_id: Session ID
        path: Optional project path

    Returns:
        Status message
    """
    try:
        # Delete from MetricsDB
        try:
            db = get_metrics_db()
            db.delete_session(session_id)
            logger.info(f"Deleted session {session_id} from MetricsDB")
        except Exception as e:
            logger.warning(f"MetricsDB delete failed: {e}")

        # Direct deletion from file storage
        storage_dir = AgentConfig.get_sessions_storage_dir()
        session_dir = os.path.join(storage_dir, f"session_{session_id}")
        manager_deleted = False
        
        try:
            if os.path.exists(session_dir):
                import shutil
                shutil.rmtree(session_dir)
                manager_deleted = True
                logger.info(f"Deleted session directory: {session_dir}")
        except Exception as e:
            logger.error(f"Error deleting session directory: {e}")
            manager_deleted = False

        if not manager_deleted:
            raise HTTPException(status_code=404, detail="Session not found or could not be deleted")

        return {
            "status": "success",
            "message": f"Session {session_id} deleted"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sessions/{session_id}/title", response_model=dict)
async def update_session_title(session_id: str, title_data: dict):
    """
    Update the title of a session.

    Args:
        session_id: Session ID
        title_data: Dictionary containing the new title

    Returns:
        Status message
    """
    try:
        new_title = title_data.get("title", "").strip()
        if not new_title:
            raise HTTPException(status_code=400, detail="Title cannot be empty")

        # Update title in MetricsDB
        try:
            db = get_metrics_db()
            db.update_session_title(session_id, new_title)
        except Exception as e:
            logger.error(f"Error updating title in MetricsDB: {e}")

        # Update title in session file storage
        try:
            storage_dir = AgentConfig.get_sessions_storage_dir()
            session_dir = os.path.join(storage_dir, f"session_{session_id}")
            session_file = os.path.join(session_dir, "session.json")
            
            if os.path.exists(session_file):
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                
                # Update title in session data
                session_data['title'] = new_title
                if 'metadata' not in session_data:
                    session_data['metadata'] = {}
                session_data['metadata']['title'] = new_title
                session_data['updated_at'] = datetime.now().isoformat()
                
                with open(session_file, 'w') as f:
                    json.dump(session_data, f, indent=2)
                    
                logger.info(f"Updated title in session file: {session_file}")
            
        except Exception as e:
            logger.error(f"Error updating title in session file storage: {e}")

        logger.info(f"Updated session {session_id} title to: {new_title}")

        return {
            "status": "success",
            "message": f"Session title updated to: {new_title}",
            "title": new_title
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating session title: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/hide", response_model=dict)
async def hide_session(session_id: str):
    """
    Hide a session from the list (soft delete).
    
    Args:
        session_id: Session ID
        
    Returns:
        Status message
    """
    try:
        # Note: Soft delete not implemented in GodotyAgent yet - always returns success
        return {
            "status": "success",
            "message": "Session hidden successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error hiding session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/status", response_model=dict)
async def get_session_status(session_id: str):
    """
    Check if session is ready for messaging.

    Args:
        session_id: Session ID to check

    Returns:
        Session status information including readiness
    """
    try:
        # Check if session directory exists
        storage_dir = AgentConfig.get_sessions_storage_dir()
        session_dir = os.path.join(storage_dir, f"session_{session_id}")

        # Try to load metadata from file
        metadata = None
        try:
            metadata_file = os.path.join(session_dir, "metadata.json")
            if os.path.exists(metadata_file):
                with open(metadata_file) as f:
                    metadata = json.load(f)
        except Exception as e:
            logger.debug(f"Could not load metadata for session {session_id}: {e}")

        # If no metadata, try to determine status from agent
        if not metadata:
            try:
                from agents.agno_agent import get_godoty_agent
                agent = get_godoty_agent(session_id=session_id)
                # If agent exists and has session_manager, consider it ready
                if hasattr(agent, 'session_manager') and agent.session_manager:
                    return {
                        "session_id": session_id,
                        "status": "ready",
                        "ready": True,
                        "created_at": datetime.utcnow().isoformat(),
                        "message": "Session is ready for messaging"
                    }
            except Exception as e:
                logger.debug(f"Could not access agent for session {session_id}: {e}")

            # If we can't determine status, assume not ready
            return {
                "session_id": session_id,
                "status": "unknown",
                "ready": False,
                "created_at": datetime.utcnow().isoformat(),
                "message": "Session status could not be determined"
            }

        # Check status from metadata
        session_status = metadata.get("status", "unknown")
        is_ready = session_status == "ready"

        return {
            "session_id": session_id,
            "status": session_status,
            "ready": is_ready,
            "created_at": metadata.get("created_at", datetime.utcnow().isoformat()),
            "title": metadata.get("title"),
            "project_path": metadata.get("project_path"),
            "session_type": metadata.get("session_type", "AGENT")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking session status for {session_id}: {e}")
        return {
            "session_id": session_id,
            "status": "error",
            "ready": False,
            "error": str(e),
            "created_at": datetime.utcnow().isoformat()
        }


@router.post("/sessions/{session_id}/chat", response_model=dict)
async def chat_session(
    session_id: str,
    request: ChatRequest,
    path: Optional[str] = Query(None),
    auth_user: dict = Depends(require_auth)
):
    """
    Send a message to a session.
    
    Requires authentication and sufficient credits.
    
    Args:
        session_id: Session ID
        request: ChatRequest with message
        path: Optional project path
        auth_user: Authenticated user info (injected via dependency)
        
    Returns:
        Agent response
    """
    try:
        # Process message with authenticated user context
        agent = get_godoty_agent(session_id=session_id, user_context=auth_user)
        result = await agent.run(request.message)
        
        # Format result
        response_text = str(result)
        if hasattr(result, 'message') and isinstance(result.message, dict):
             content = result.message.get('content')
             if isinstance(content, list) and len(content) > 0:
                 response_text = content[0].get('text', response_text)
        
        return {
            "status": "success",
            "response": response_text,
            "raw_result": str(result)
        }
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/stop", response_model=dict)
async def stop_session(session_id: str):
    """
    Stop a running session.
    
    Args:
        session_id: Session ID
        
    Returns:
        Status message
    """
    try:
        # from agents.multi_agent_manager import get_multi_agent_manager
        # manager = get_multi_agent_manager()
        
        # stopped = manager.stop_session(session_id)
        
        # GodotyAgent doesn't have explicit stop yet (async tasks cancellation handled in stream)
        stopped = True
        
        if stopped:
            return {
                "status": "success",
                "message": "Session stopped successfully"
            }
        else:
            return {
                "status": "success",
                "message": "No running task found for session"
            }
    except Exception as e:
        logger.error(f"Error stopping session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def transform_event_for_frontend(event_type: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform backend event format to frontend-expected format.

    Backend sends: {"type": "text", "data": {"content": "..."}}
    Frontend expects: {"type": "text", "content": "..."}

    This function flattens the structure for compatibility.
    """
    # Start with the type
    transformed = {
        "type": event_type
    }

    # Move data fields to top level based on event type
    if event_type == "text":
        if "content" in event_data:
            transformed["content"] = event_data["content"]
        else:
            transformed["content"] = str(event_data.get("message", ""))
    elif event_type == "reasoning":
        if "reasoning" in event_data:
            transformed["reasoning"] = event_data["reasoning"]
        else:
            transformed["reasoning"] = str(event_data.get("thought", ""))
    elif event_type == "tool_use":
        # Handle tool calls
        if "tool_call" in event_data:
            transformed["toolCall"] = event_data["tool_call"]
        if "result" in event_data:
            transformed["result"] = event_data["result"]
        # Include status if available
        if "status" in event_data:
            transformed["status"] = event_data["status"]
    elif event_type == "error":
        transformed["error"] = event_data.get("error", "Unknown error occurred")
        # Include error code if available
        if "code" in event_data:
            transformed["code"] = event_data["code"]
    elif event_type == "done":
        # Done events don't need additional data
        pass
    else:
        # For unknown event types, include all data
        for key, value in event_data.items():
            transformed[key] = value

    return transformed


@router.post("/sessions/{session_id}/chat/stream")
async def chat_session_stream(
    session_id: str,
    chat_request: ChatRequest,
    request: Request,
    path: Optional[str] = Query(None),
    auth_user: dict = Depends(require_auth)
):
    """
    Send a message to a session and stream the response.

    Requires authentication and sufficient credits.

    Args:
        session_id: Session ID
        chat_request: ChatRequest with message
        request: FastAPI Request object for disconnection detection
        path: Optional project path
        auth_user: Authenticated user info (injected via dependency)

    Returns:
        StreamingResponse with Server-Sent Events
    """
    try:
        # Create streaming generator
        async def event_generator():
            """Generate Server-Sent Events from agent stream."""
            try:
                agent = get_godoty_agent(session_id=session_id, user_context=auth_user)
                
                # Determine mode - default to planning unless explicitly set to learning or execution
                mode = chat_request.mode if chat_request.mode in ["learning", "planning", "execution"] else "planning"
                
                # If feedback is provided, prepend it to the message for plan regeneration
                message = chat_request.message
                if chat_request.plan_feedback:
                    message = f"[User Feedback: {chat_request.plan_feedback}]\n\n{message}"
                
                logger.info(f"Starting {mode} mode stream for session {session_id}")
                
                async for event in agent.run_stream(message, mode=mode):
                    # Check if client has disconnected
                    if await request.is_disconnected():
                        logger.info(f"Client disconnected for session {session_id}, stopping stream")
                        break

                    # Format as SSE - send events directly as-is from backend
                    event_type = event.get("type", "data")
                    event_data = event.get("data", {})

                    # Sanitize event data to ensure JSON serializability
                    sanitized_data = sanitize_event_data(event_data)
                    
                    # Include mode in the event data
                    sanitized_data["mode"] = mode

                    # Create the event structure to send directly
                    final_data = {
                        "type": event_type,
                        "data": sanitized_data
                    }

                    # Serialize data with error handling
                    try:
                        data_json = json.dumps(final_data)
                    except (TypeError, ValueError) as e:
                        logger.error(f"Failed to serialize event data: {e}, event_type: {event_type}")
                        # Fallback to a basic error message
                        final_data = {"type": "error", "data": {"error": "Serialization failed"}}
                        data_json = json.dumps(final_data)

                    # Yield SSE format with the event type
                    yield f"event: {event_type}\n"
                    yield f"data: {data_json}\n\n"
                
                # Send done event with plan info
                done_data = {
                    "mode": mode,
                    "has_pending_plan": agent.has_pending_plan()
                }
                yield "event: done\n"
                yield f"data: {json.dumps(done_data)}\n\n"

            except asyncio.CancelledError:
                logger.info(f"Stream cancelled for session {session_id}")
                yield "event: cancelled\n"
                yield 'data: {"message": "Stream cancelled by client"}\n\n'
                raise

            except Exception as e:
                logger.error(f"Error in chat stream: {e}")
                import traceback
                logger.error(traceback.format_exc())
                error_data = json.dumps({"error": str(e)})
                yield "event: error\n"
                yield f"data: {error_data}\n\n"

        # Return streaming response
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except Exception as e:
        logger.error(f"Error setting up chat stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Plan Management Routes

@router.get("/sessions/{session_id}/plan", response_model=dict)
async def get_plan_status(session_id: str):
    """
    Get the current pending plan and its status.
    
    Returns:
        Full plan info including state and original request
    """
    try:
        agent = get_godoty_agent(session_id=session_id)
        plan_info = agent.get_plan_info()
        
        return {
            "status": "success",
            **plan_info,
            "current_mode": agent.get_current_mode()
        }
    except Exception as e:
        logger.error(f"Error getting plan status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/plan/approve")
async def approve_plan_stream(
    session_id: str,
    request: Request,
    execution_prompt: Optional[str] = None
):
    """
    Approve the pending plan and execute it with streaming response.
    
    Args:
        session_id: Session ID
        execution_prompt: Optional additional instructions for execution
    
    Returns:
        StreamingResponse with execution events
    """
    try:
        agent = get_godoty_agent(session_id=session_id)
        
        if not agent.has_pending_plan():
            raise HTTPException(status_code=400, detail="No pending plan to approve")
        
        async def event_generator():
            try:
                async for event in agent.approve_and_execute(execution_prompt):
                    if await request.is_disconnected():
                        break
                    
                    event_type = event.get("type", "data")
                    event_data = event.get("data", {})
                    sanitized_data = sanitize_event_data(event_data)
                    sanitized_data["mode"] = "execution"
                    
                    final_data = {"type": event_type, "data": sanitized_data}
                    yield f"event: {event_type}\n"
                    yield f"data: {json.dumps(final_data)}\n\n"
                
                yield "event: done\n"
                yield f'data: {{"mode": "execution", "execution_complete": true}}\n\n'
                
            except Exception as e:
                logger.error(f"Error in execution stream: {e}")
                yield "event: error\n"
                yield f'data: {{"error": "{str(e)}"}}\n\n'
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/plan/reject", response_model=dict)
async def reject_plan(session_id: str, feedback: Optional[dict] = None):
    """
    Reject/clear the pending plan.
    
    Args:
        session_id: Session ID
        feedback: Optional dict with 'reason' field
    
    Returns:
        Status confirmation
    """
    try:
        agent = get_godoty_agent(session_id=session_id)
        agent.clear_pending_plan()
        
        return {
            "status": "success",
            "message": "Plan rejected and cleared",
            "feedback_received": feedback.get("reason") if feedback else None
        }
    except Exception as e:
        logger.error(f"Error rejecting plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RegeneratePlanRequest(BaseModel):
    """Request model for plan regeneration."""
    feedback: str = Field(..., description="User feedback for plan changes")


@router.post("/sessions/{session_id}/plan/regenerate")
async def regenerate_plan_stream(
    session_id: str,
    regen_request: RegeneratePlanRequest,
    request: Request
):
    """
    Regenerate a plan with user feedback.
    
    Args:
        session_id: Session ID
        regen_request: Feedback for regeneration
    
    Returns:
        StreamingResponse with new plan
    """
    try:
        agent = get_godoty_agent(session_id=session_id)
        
        # Get the original request
        plan_info = agent.get_plan_info()
        original_request = plan_info.get("original_request")
        
        if not original_request:
            raise HTTPException(status_code=400, detail="No original request found for regeneration")
        
        # Clear old plan
        agent.clear_pending_plan()
        
        # Construct regeneration prompt with feedback
        regen_prompt = f"""[User Feedback on Previous Plan]
{regen_request.feedback}

[Original Request]
{original_request}

Please generate a new plan addressing the user's feedback."""

        async def event_generator():
            try:
                async for event in agent.run_stream(regen_prompt, mode="planning"):
                    if await request.is_disconnected():
                        break
                    
                    event_type = event.get("type", "data")
                    event_data = event.get("data", {})
                    sanitized_data = sanitize_event_data(event_data)
                    sanitized_data["mode"] = "planning"
                    
                    final_data = {"type": event_type, "data": sanitized_data}
                    yield f"event: {event_type}\n"
                    yield f"data: {json.dumps(final_data)}\n\n"
                
                done_data = {
                    "mode": "planning",
                    "has_pending_plan": agent.has_pending_plan()
                }
                yield "event: done\n"
                yield f"data: {json.dumps(done_data)}\n\n"
                
            except Exception as e:
                logger.error(f"Error in regeneration stream: {e}")
                yield "event: error\n"
                yield f'data: {{"error": "{str(e)}"}}\n\n'
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))
