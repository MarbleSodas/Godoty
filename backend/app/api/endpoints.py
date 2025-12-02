"""
FastAPI endpoints for Godoty backend.

Provides REST API endpoints that match the frontend expectations for
session management, streaming chat, and metrics retrieval.
"""

import logging
import uuid
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agents.godoty_agent import GodotyAgent
from app.sessions.session_manager import GodotySessionManager
from app.config import settings
from app.api.streaming import (
    create_sse_response,
    stream_context,
    agent_streamer
)

logger = logging.getLogger(__name__)

# Create FastAPI router
router = APIRouter()

# Global instances

# Request/response models
class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    project_path: str

class ChatMessageRequest(BaseModel):
    message: str
    session_id: str
    project_path: str
    model_id: Optional[str] = None

class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None

# Active agents storage
active_agents: Dict[str, GodotyAgent] = {}
active_session_managers: Dict[str, GodotySessionManager] = {}


def get_session_manager(project_path: str) -> GodotySessionManager:
    """Get or create session manager for a project."""
    if project_path not in active_session_managers:
        active_session_managers[project_path] = GodotySessionManager(project_path)
    return active_session_managers[project_path]


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.

    Returns:
        Health status information
    """
    try:
        return {
            "status": "healthy",
            "app_name": settings.app_name,
            "version": settings.app_version,
            "model": settings.default_godoty_model,
            "active_sessions": len(active_agents),
            "active_projects": len(active_session_managers)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")


@router.get("/connection/status")
async def connection_status() -> Dict[str, Any]:
    """
    Check OpenRouter connection status.

    Returns:
        Connection status and detailed model information including API key source
    """
    try:
        # Check if backend has API key configured
        has_api_key = bool(settings.openrouter_api_key)

        # Determine API key source and create prefix for display (security: only show first 8 chars)
        api_key_source = "environment" if settings.openrouter_api_key else "none"
        api_key_prefix = settings.openrouter_api_key[:8] + "..." if settings.openrouter_api_key else None

        return {
            "connected": has_api_key,
            "model_id": settings.default_godoty_model,
            "api_key_configured": has_api_key,
            "api_key_source": api_key_source,
            "api_key_prefix": api_key_prefix,
            "has_backend_key": has_api_key,
            "allow_user_override": True,  # Allow users to override if needed
            "provider": "openrouter",
            "base_url": settings.openrouter_base_url,
            # Add apiKeyStatus nested object for frontend compatibility
            "apiKeyStatus": {
                "hasKey": has_api_key,
                "hasBackendKey": has_api_key,
                "allowUserOverride": True,
                "apiKeyPrefix": api_key_prefix
            }
        }

    except Exception as e:
        logger.error(f"Connection status check failed: {e}")
        return {
            "connected": False,
            "error": str(e),
            "model_id": settings.default_godoty_model,
            "api_key_configured": False,
            "api_key_source": "none",
            "api_key_prefix": None,
            "has_backend_key": False,
            "allow_user_override": True,
            "provider": "openrouter",
            "base_url": settings.openrouter_base_url,
            # Add apiKeyStatus nested object for frontend compatibility
            "apiKeyStatus": {
                "hasKey": False,
                "hasBackendKey": False,
                "allowUserOverride": True,
                "apiKeyPrefix": None
            }
        }


@router.post("/sessions")
async def create_session(request: CreateSessionRequest) -> Dict[str, Any]:
    """
    Create a new session.

    Args:
        request: Session creation request

    Returns:
        Created session information
    """
    try:
        session_manager = get_session_manager(request.project_path)
        session_id = session_manager.create_session(request.title)

        return {
            "session_id": session_id,
            "title": request.title or f"Session {session_id[:8]}",
            "created_at": session_manager._load_session_metadata(session_id).get("created_at"),
            "status": "active"
        }

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(project_path: str) -> List[Dict[str, Any]]:
    """
    List all sessions for a project.

    Args:
        project_path: Path to the Godot project

    Returns:
        List of session information
    """
    try:
        session_manager = get_session_manager(project_path)
        sessions = session_manager.list_sessions()

        return sessions

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, project_path: str) -> Dict[str, Any]:
    """
    Get information about a specific session.

    Args:
        session_id: Session identifier
        project_path: Path to the Godot project

    Returns:
        Session information
    """
    try:
        session_manager = get_session_manager(project_path)

        if not session_manager.session_exists(session_id):
            raise HTTPException(status_code=404, detail="Session not found")

        session_stats = session_manager.get_session_stats(session_id)
        if not session_stats:
            raise HTTPException(status_code=404, detail="Session data not found")

        return session_stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/chat/stream")
async def chat_stream(
    session_id: str,
    request: ChatMessageRequest,
    background_tasks: BackgroundTasks
) -> JSONResponse:
    """
    Start a streaming chat session.

    Args:
        session_id: Session identifier
        request: Chat message request
        background_tasks: FastAPI background tasks

    Returns:
        SSE streaming response
    """
    try:
        # Create stream ID
        stream_id = str(uuid.uuid4())

        # Create SSE response
        return create_sse_response(stream_id)

    except Exception as e:
        logger.error(f"Failed to start chat stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/chat/send")
async def send_chat_message(request: ChatMessageRequest) -> Dict[str, Any]:
    """
    Send a chat message and get response.

    Args:
        request: Chat message request

    Returns:
        Message response
    """
    try:
        # Get or create agent
        if request.session_id not in active_agents:
            active_agents[request.session_id] = GodotyAgent(
                session_id=request.session_id,
                project_path=request.project_path,
                model_id=request.model_id
            )

        agent = active_agents[request.session_id]

        # Process message (this would be async in real implementation)
        # For now, return a mock response
        response = {
            "type": "text",
            "content": f"Received your message: {request.message[:100]}...",
            "session_id": request.session_id
        }

        return response

    except Exception as e:
        logger.error(f"Failed to send chat message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    project_path: str
) -> Dict[str, Any]:
    """
    Update session information.

    Args:
        session_id: Session identifier
        request: Update request
        project_path: Path to the Godot project

    Returns:
        Updated session information
    """
    try:
        session_manager = get_session_manager(project_path)

        if not session_manager.session_exists(session_id):
            raise HTTPException(status_code=404, detail="Session not found")

        updates = {}
        if request.title is not None:
            updates["title"] = request.title
        if request.status is not None:
            updates["status"] = request.status

        success = session_manager.update_session_metadata(session_id, updates)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update session")

        # Return updated session info
        session_stats = session_manager.get_session_stats(session_id)
        return session_stats or {"session_id": session_id, "updated": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/hide")
async def hide_session(session_id: str, project_path: str) -> Dict[str, Any]:
    """
    Hide a session (soft delete).

    Args:
        session_id: Session identifier
        project_path: Path to the Godot project

    Returns:
        Operation result
    """
    try:
        session_manager = get_session_manager(project_path)

        if not session_manager.session_exists(session_id):
            raise HTTPException(status_code=404, detail="Session not found")

        success = session_manager.update_session_metadata(session_id, {"status": "hidden"})

        if not success:
            raise HTTPException(status_code=500, detail="Failed to hide session")

        # Clean up active agent if exists
        if session_id in active_agents:
            del active_agents[session_id]

        return {"session_id": session_id, "status": "hidden"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to hide session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str, project_path: str) -> Dict[str, Any]:
    """
    Stop a session and clean up resources.

    Args:
        session_id: Session identifier
        project_path: Path to the Godot project

    Returns:
        Operation result
    """
    try:
        session_manager = get_session_manager(project_path)

        if not session_manager.session_exists(session_id):
            raise HTTPException(status_code=404, detail="Session not found")

        # Update session status
        success = session_manager.update_session_metadata(session_id, {"status": "stopped"})

        # Clean up active agent
        if session_id in active_agents:
            del active_agents[session_id]

        return {"session_id": session_id, "status": "stopped"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, project_path: str) -> Dict[str, Any]:
    """
    Delete a session permanently.

    Args:
        session_id: Session identifier
        project_path: Path to the Godot project

    Returns:
        Operation result
    """
    try:
        session_manager = get_session_manager(project_path)

        # Clean up active agent
        if session_id in active_agents:
            del active_agents[session_id]

        # Delete session
        success = session_manager.delete_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"session_id": session_id, "deleted": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_metrics(project_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Get basic session metrics.

    Args:
        project_path: Optional project path to filter by

    Returns:
        Basic session information
    """
    try:
        # Add session-level information if project_path specified
        session_metrics = []
        if project_path:
            session_manager = get_session_manager(project_path)
            sessions = session_manager.list_sessions()

            for session in sessions:
                session_metrics.append({
                    "session_id": session.get("session_id"),
                    "title": session.get("title"),
                    "status": session.get("status"),
                    "created_at": session.get("created_at")
                })

        return {
            "session_metrics": session_metrics,
            "active_sessions": len(active_agents)
        }

    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    """
    Get configuration information.

    Returns:
        Configuration details
    """
    try:
        return {
            "default_model": settings.default_godoty_model,
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "openrouter_base_url": settings.openrouter_base_url
        }

    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        raise HTTPException(status_code=500, detail=str(e))