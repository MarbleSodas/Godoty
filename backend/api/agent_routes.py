"""
FastAPI routes for the planning agent.

Provides endpoints for interacting with the planning agent:
- Streaming responses with SSE
- Non-streaming responses
- Session management
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional, AsyncIterable
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents import get_planning_agent, AgentConfig
from agents.db import ProjectDB

logger = logging.getLogger(__name__)


class SessionTitleUpdate(BaseModel):
    title: str = Field(..., description="New session title")


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
                max_length = 50
                if len(content) > max_length:
                    # Try to break at last word boundary before limit
                    truncated = content[:max_length].rsplit(' ', 1)[0]
                    # Only use truncated if it's substantial (>20 chars)
                    if len(truncated) > 20:
                        content = truncated + "..."
                    else:
                        # Just hard truncate
                        content = content[:max_length] + "..."

                return content if content else "New Session"

    return "New Session"

# Create router
router = APIRouter(prefix="/api/agent", tags=["agent"])


# Request/Response Models


# Session Management Routes

class SessionRequest(BaseModel):
    """Request model for session creation."""
    session_id: str = Field(..., description="Unique session identifier", min_length=1)
    title: Optional[str] = Field(None, description="Optional session title")
    project_path: Optional[str] = Field(None, description="Project path for database storage")


class ChatRequest(BaseModel):
    """Request model for chat message."""
    message: str = Field(..., description="User message", min_length=1)
    mode: str = Field("planning", description="Execution mode: 'planning' or 'fast'")


@router.post("/sessions", response_model=dict)
async def create_session(request: SessionRequest):
    """
    Create a new multi-agent session.

    Args:
        request: SessionRequest with session_id, optional title, and optional project_path

    Returns:
        Session details
    """
    try:
        from agents.multi_agent_manager import get_multi_agent_manager
        manager = get_multi_agent_manager()

        session_id = manager.create_session(
            request.session_id,
            title=request.title,
            project_path=request.project_path
        )

        return {
            "status": "success",
            "session_id": session_id,
            "message": "Session created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))




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

        # Get sessions from FileSessionManager (primary source)
        from agents.multi_agent_manager import get_multi_agent_manager
        multi_agent_manager = get_multi_agent_manager()
        fs_sessions = multi_agent_manager.list_sessions()
        logger.info(f"Found {len(fs_sessions)} sessions from FileSessionManager")

        if not path:
            # Require explicit project path to avoid loading wrong project's sessions
            logger.error("No project path provided - project path is required to list sessions")
            raise HTTPException(
                status_code=400,
                detail="Project path is required to list sessions. Please provide a valid project path."
            )

        sessions_dict = {}

        logger.info(f"Processing {len(fs_sessions)} sessions from FileSessionManager")

        # Process FileSessionManager sessions
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

                # Get session date from FileSessionManager
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

        # SECONDARY SOURCE: Enrich with ProjectDB metadata where available
        try:
            logger.debug(f"Enriching sessions with ProjectDB data using path: {path}")
            db = ProjectDB(path)
            db_sessions = db.get_all_sessions()
            logger.debug(f"Found {len(db_sessions)} sessions in ProjectDB")

            # Create mapping of session_id -> db_session for quick lookup
            db_session_map = {session["id"]: session for session in db_sessions}

            # Enrich FileSessionManager sessions with ProjectDB data
            enriched_count = 0
            for session_id, session_data in sessions_dict.items():
                if session_id in db_session_map:
                    db_session = db_session_map[session_id]
                    # Merge ProjectDB metadata with FileSessionManager data
                    session_data["metadata"].update({
                        "last_updated": db_session.get("last_updated"),
                        "project_path": path
                    })
                    enriched_count += 1
            logger.debug(f"Enriched {enriched_count} sessions with ProjectDB data")

        except Exception as e:
            logger.warning(f"Failed to enrich sessions with ProjectDB data: {e}")

        # Add metrics from ProjectDB (with defaults if unavailable)
        session_ids = list(sessions_dict.keys())
        try:
            logger.debug(f"Fetching metrics for {len(session_ids)} sessions")
            db = ProjectDB(path)
            metrics_map = db.get_metrics_for_sessions(session_ids)

            metrics_count = 0
            for sid, sdata in sessions_dict.items():
                sdata["metrics"] = metrics_map.get(sid, {
                    "session_cost": 0.0,
                    "session_tokens": 0
                })
                if metrics_map.get(sid):
                    metrics_count += 1
            logger.debug(f"Added metrics for {metrics_count} sessions")
        except Exception as e:
            logger.error(f"Metrics fetch failed: {e}")
            for sid, sdata in sessions_dict.items():
                sdata["metrics"] = {
                    "session_cost": 0.0,
                    "session_tokens": 0
                }

        logger.info(f"Successfully returning {len(sessions_dict)} sessions for project: {path}")
        return {"status": "success", "sessions": sessions_dict}

    except Exception as e:
        logger.error(f"Unexpected error in list_sessions: {e}", exc_info=True)
        return {"status": "error", "sessions": {}, "message": str(e)}


@router.get("/sessions/{session_id}", response_model=dict)
async def get_session(session_id: str, path: Optional[str] = Query(None)):
    """
    Get session details with enhanced loading strategy and user notifications.

    Args:
        session_id: Session ID
        path: Optional project path to look up in ProjectDB

    Returns:
        Session details with status and error information
    """
    try:
        from agents.multi_agent_manager import get_multi_agent_manager
        manager = get_multi_agent_manager()

        # Get chat history from FileSessionManager (single source of truth)
        chat_history = manager.get_session_chat_history(session_id)

        try:
            if chat_history:
                # Get metrics from database (always provide defaults if unavailable)
                metrics = None
                if path:
                    try:
                        db = ProjectDB(path)
                        metrics = db.get_session_metrics(session_id)
                    except Exception as metrics_error:
                        logger.warning(f"Failed to get session metrics: {metrics_error}")

                # Ensure metrics exist with defaults
                if not metrics:
                    metrics = {
                        "session_cost": 0.0,
                        "session_tokens": 0,
                        "individual_cost": 0.0,
                        "individual_tokens": 0,
                        "workflow_cost": 0.0,
                        "workflow_tokens": 0
                    }

                return {
                    "status": "success",
                    "chat_history": chat_history,
                    "metrics": metrics
                }
            else:
                return {
                    "status": "error",
                    "message": f"Session {session_id} not found or contains no data"
                }

        except FileNotFoundError:
            logger.error(f"Session file not found: {session_id}")
            return {"status": "error", "message": "Session not found. It may have been deleted."}
        except PermissionError:
            logger.error(f"Permission denied accessing session: {session_id}")
            return {"status": "error", "message": "Unable to access session due to file permissions."}
        except Exception as e:
            logger.error(f"Unexpected error loading session {session_id}: {e}", exc_info=True)
            return {"status": "error", "message": "An unexpected error occurred while loading the session."}

    except Exception as e:
        logger.error(f"Failed to load session {session_id}: {e}")
        return {"status": "error", "message": f"Unable to load session: {str(e)}"}




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
        from agents.multi_agent_manager import get_multi_agent_manager
        manager = get_multi_agent_manager()
        
        hidden = manager.hide_session(session_id)
        
        if not hidden:
             raise HTTPException(status_code=404, detail="Session not found")
             
        return {
            "status": "success",
            "message": "Session hidden successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error hiding session: {e}")
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
        from agents.multi_agent_manager import get_multi_agent_manager
        manager = get_multi_agent_manager()
        
        stopped = manager.stop_session(session_id)
        
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


@router.post("/sessions/{session_id}/chat/stream")
async def chat_session_stream(
    session_id: str,
    chat_request: ChatRequest,
    request: Request,
    path: Optional[str] = Query(None)
):
    """
    Send a message to a session and stream the response.

    Args:
        session_id: Session ID
        chat_request: ChatRequest with message
        request: FastAPI Request object for disconnection detection
        path: Optional project path

    Returns:
        StreamingResponse with Server-Sent Events
    """
    
    def sanitize_for_json(obj):
        """
        Recursively sanitize an object to ensure it's JSON serializable.
        Filters out non-serializable objects like EventLoopMetrics.
        """
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        elif isinstance(obj, dict):
            # Filter out known non-serializable types and recursively sanitize values
            sanitized = {}
            for key, value in obj.items():
                # Skip known non-serializable object types
                if hasattr(value, '__class__') and 'EventLoopMetrics' in value.__class__.__name__:
                    continue
                # Skip private/internal keys that might contain complex objects
                if isinstance(key, str) and key.startswith('_'):
                    continue
                try:
                    sanitized[key] = sanitize_for_json(value)
                except (TypeError, ValueError):
                    # If we can't serialize it, convert to string representation
                    sanitized[key] = str(value)
            return sanitized
        elif isinstance(obj, (list, tuple)):
            return [sanitize_for_json(item) for item in obj]
        else:
            # For any other type, try to convert to string
            try:
                # Check if it's actually JSON serializable first
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)
    
    try:
        from agents.multi_agent_manager import get_multi_agent_manager
        manager = get_multi_agent_manager()
        
        # Auto-create session if it doesn't exist (lazy creation)
        if not manager.get_session(session_id):
            logger.info(f"Auto-creating session {session_id} with title: {chat_request.message[:50]}...")
            manager.create_session(session_id, title=chat_request.message, project_path=path)
        
        # Create streaming generator
        async def event_generator():
            """Generate Server-Sent Events from agent stream."""
            try:
                async for event in manager.process_message_stream(session_id, chat_request.message, mode=chat_request.mode, project_path=path):
                    # Check if client has disconnected
                    if await request.is_disconnected():
                        logger.info(f"Client disconnected for session {session_id}, stopping stream")
                        manager.stop_session(session_id)
                        break

                    # Format as SSE
                    event_type = event.get("type", "data")
                    event_data = event.get("data", {})
                    
                    # Sanitize event data to ensure JSON serializability
                    sanitized_data = sanitize_for_json(event_data)
                    
                    # Ensure type is in the data
                    # The frontend expects the type to be part of the data object
                    # and the actual payload to be in a 'data' field
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
                        data_json = json.dumps({"error": "Serialization failed", "type": str(type(event_data))})
                    
                    # Yield SSE format
                    yield f"event: {event_type}\n"
                    yield f"data: {data_json}\n\n"
                
                # Send done event
                yield "event: done\n"
                yield "data: {}\n\n"

            except asyncio.CancelledError:
                logger.info(f"Stream cancelled for session {session_id}")
                manager.stop_session(session_id)
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


@router.put("/sessions/{session_id}/title", response_model=dict)
async def update_session_title(session_id: str, title_update: SessionTitleUpdate):
    """
    Update session title.

    Args:
        session_id: Unique identifier for the session
        title_update: New title for the session

    Returns:
        Success confirmation
    """
    try:
        from agents.multi_agent_manager import MultiAgentManager

        manager = MultiAgentManager()

        if not manager.get_session(session_id):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # Update session title
        manager.update_session_title(session_id, title_update.title)

        logger.info(f"Updated session {session_id} title to: {title_update.title}")

        return {
            "status": "success",
            "message": "Session title updated successfully",
            "session_id": session_id,
            "title": title_update.title
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating session title: {e}")
        raise HTTPException(status_code=500, detail=str(e))
