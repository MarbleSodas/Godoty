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
from typing import Optional, AsyncIterable
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents import get_planning_agent, close_planning_agent, AgentConfig
from agents.executor_agent import close_executor_agent
from agents.db import ProjectDB

logger = logging.getLogger(__name__)


def _extract_title_from_chat_history(chat_history: list) -> str:
    """
    Extract a meaningful title from the chat history.

    Priority order:
    1. First user message (trimmed to reasonable length)
    2. If no user messages, fall back to "Session {id}"

    Args:
        chat_history: List of chat messages from the database

    Returns:
        A meaningful title string
    """
    if not chat_history:
        return "New Session"

    # Find the first user message
    for message in chat_history:
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content", "")
            if content:
                # Clean up the content for display
                # Remove excessive whitespace and truncate
                content = content.strip()
                # Replace newlines with spaces
                content = ' '.join(content.split())
                # Truncate to reasonable length for title
                if len(content) > 50:
                    content = content[:50] + "..."
                return content if content else "New Session"

    # Fallback if no user message found
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
        agent = get_planning_agent()
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
        agent = get_planning_agent()

        # Reset conversation if requested
        if request.reset_conversation:
            agent.reset_conversation()

        # Generate plan - returns dict with plan, message_id, and metrics
        result = await agent.plan_async(request.prompt)

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
        agent = get_planning_agent()

        # Reset conversation if requested
        if request.reset_conversation:
            agent.reset_conversation()

        # Create streaming generator
        async def event_generator():
            """Generate Server-Sent Events from agent stream."""
            try:
                async for event in agent.plan_stream(request.prompt):
                    # Format as SSE
                    event_type = event.get("type", "data")
                    event_data = event.get("data", {})

                    # Serialize data
                    data_json = json.dumps(event_data)

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
        agent = get_planning_agent()
        agent.reset_conversation()

        return {
            "status": "success",
            "message": "Conversation history reset"
        }

    except Exception as e:
        logger.error(f"Error resetting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class UpdateConfigRequest(BaseModel):
    """Request model for updating agent configuration."""
    planning_model: Optional[str] = Field(None, description="Model ID for planning agent")
    executor_model: Optional[str] = Field(None, description="Model ID for executor agent")
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
        # 1. Update persistent configuration
        AgentConfig.update_config(
            planning_model=request.planning_model,
            executor_model=request.executor_model,
            api_key=request.openrouter_api_key
        )

        # 2. Reset the agent to pick up new configuration
        # This ensures the model is re-initialized with new ID and API key
        await close_planning_agent()
        await close_executor_agent()
        agent = get_planning_agent()
        
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
        agent = get_planning_agent()

        # Ensure MCP tools are initialized before getting configuration
        await agent._ensure_mcp_initialized()

        model_config = agent.model.get_config()
        return {
            "status": "success",
            "config": {
                "model_id": model_config.get("planning_model", "unknown"),
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
    List all available sessions.

    Prioritizes database sessions, falls back to file-based sessions if database is empty.

    Args:
        path: Optional project path for database filtering

    Returns:
        List of sessions
    """
    try:
        # Try database first (preferred source)
        if path:
            try:
                db = ProjectDB(path)
                db_sessions = db.get_all_sessions()

                if db_sessions:
                    # Convert database sessions to expected format
                    sessions_dict = {}
                    for session in db_sessions:
                        session_id = session["id"]

                        # Extract meaningful title from chat history
                        title = _extract_title_from_chat_history(session.get("chat_history", []))

                        sessions_dict[session_id] = {
                            "session_id": session_id,
                            "title": title,
                            "date": session["created_at"],
                            "active": False,  # Could check if session is in MultiAgentManager memory
                            "is_running": False,
                            "metadata": {
                                "created_at": session["created_at"],
                                "last_updated": session["last_updated"],
                                "title": title
                            },
                            "path": f"database://{session_id}"
                        }

                    # Add metrics for database sessions
                    try:
                        session_ids = list(sessions_dict.keys())
                        metrics_map = db.get_metrics_for_sessions(session_ids)

                        for session_id, session_data in sessions_dict.items():
                            if session_id in metrics_map:
                                session_data["metrics"] = metrics_map[session_id]

                    except Exception as metrics_error:
                        logger.warning(f"Failed to get metrics for database sessions: {metrics_error}")

                    logger.info(f"Retrieved {len(sessions_dict)} sessions from database for project: {path}")
                    return {
                        "status": "success",
                        "sessions": sessions_dict
                    }

            except Exception as db_error:
                logger.warning(f"Failed to get sessions from database: {db_error}")

        # Fallback to file-based sessions
        from agents.multi_agent_manager import get_multi_agent_manager
        manager = get_multi_agent_manager()

        sessions_dict = manager.list_sessions()

        # Enhance with metrics if possible
        try:
            # Use a dummy path if none provided, just to access the global DB file
            db_path = path if path else "."
            db = ProjectDB(db_path)

            session_ids = list(sessions_dict.keys())
            metrics_map = db.get_metrics_for_sessions(session_ids)

            for session_id, session_data in sessions_dict.items():
                if session_id in metrics_map:
                    session_data["metrics"] = metrics_map[session_id]

        except Exception as e:
            logger.warning(f"Error fetching metrics for file sessions: {e}")
            # Continue without metrics if DB fails

        logger.info(f"Retrieved {len(sessions_dict)} sessions from file system (fallback)")
        return {
            "status": "success",
            "sessions": sessions_dict
        }

    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

        # Primary source: FileSessionManager (always has latest conversation)
        try:
            session_data = await manager.get_session_chat_history(session_id)

            # If we have data and a path, sync to ProjectDB for future listing
            if session_data and path:
                try:
                    db = ProjectDB(path)
                    db.save_session(session_id, session_data)
                    logger.info(f"Synced session {session_id} to ProjectDB")
                except Exception as sync_error:
                    logger.warning(f"Failed to sync session to ProjectDB: {sync_error}")

            if session_data:
                # Get metrics from database if available
                metrics = None
                if path:
                    try:
                        db = ProjectDB(path)
                        metrics = db.get_session_metrics(session_id)
                    except Exception as metrics_error:
                        logger.warning(f"Failed to get session metrics: {metrics_error}")

                return {
                    "status": "success",
                    "chat_history": session_data,
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
        from agents.executor_agent import get_executor_agent
        agent = get_executor_agent()
        
        agent.set_project_path(path)
        agent.restore_session(session_id)
        
        return {
            "status": "success",
            "message": f"Session {session_id} restored"
        }
    except Exception as e:
        logger.error(f"Error restoring session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/project", response_model=dict)
async def get_project_metrics(path: str = Query(...)):
    """
    Get aggregated metrics for the project.

    Args:
        path: Project path

    Returns:
        Project metrics
    """
    try:
        db = ProjectDB(path)
        metrics = db.get_project_metrics()

        logger.info(f"Project metrics for {path}: cost=${metrics['total_cost']:.4f}, "
                   f"tokens={metrics['total_tokens']}, sessions={metrics['total_sessions']}")

        return {
            "status": "success",
            "metrics": metrics
        }
    except Exception as e:
        logger.error(f"Error getting project metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/session/{session_id}", response_model=dict)
async def get_session_metrics_endpoint(session_id: str, path: str = Query(...)):
    """
    Get metrics for a specific session.
    
    Args:
        session_id: Session ID
        path: Project path
        
    Returns:
        Session metrics
    """
    try:
        db = ProjectDB(path)
        metrics = db.get_session_metrics(session_id)
        return {
            "status": "success",
            "metrics": metrics
        }
    except Exception as e:
        logger.error(f"Error getting session metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}", response_model=dict)
async def delete_session(session_id: str, path: Optional[str] = Query(None)):
    """
    Delete a session.
    
    Args:
        session_id: Session ID
        path: Optional project path
        
    Returns:
        Status message
    """
    try:
        project_db_deleted = False
        if path:
            try:
                db = ProjectDB(path)
                db.delete_session(session_id)
                project_db_deleted = True
            except Exception as e:
                logger.error(f"Error deleting from ProjectDB: {e}")

        from agents.multi_agent_manager import get_multi_agent_manager
        manager = get_multi_agent_manager()
        
        manager_deleted = manager.delete_session(session_id)
        
        if not manager_deleted and not project_db_deleted:
            raise HTTPException(status_code=404, detail="Session not found or could not be deleted")
            
        return {
            "status": "success",
            "message": "Session deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
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


@router.post("/sessions/{session_id}/chat", response_model=dict)
async def chat_session(session_id: str, request: ChatRequest, path: Optional[str] = Query(None)):
    """
    Send a message to a session.
    
    Args:
        session_id: Session ID
        request: ChatRequest with message
        path: Optional project path
        
    Returns:
        Agent response
    """
    try:
        from agents.multi_agent_manager import get_multi_agent_manager
        manager = get_multi_agent_manager()
        
        # Auto-create session if it doesn't exist (lazy creation)
        if not manager.get_session(session_id):
            logger.info(f"Auto-creating session {session_id} with title: {request.message[:50]}...")
            manager.create_session(session_id, title=request.message, project_path=path)
        
        # Process message
        # Note: This might take time, so in a real app we might want streaming or background tasks
        result = await manager.process_message(session_id, request.message, mode=request.mode, project_path=path)
        
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
