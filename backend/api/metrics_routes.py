"""
FastAPI routes for metrics tracking.

Provides endpoints for querying token usage and cost metrics at
message, session, and project levels.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import get_db_manager

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/metrics", tags=["metrics"])


# Response Models
class MetricsResponse(BaseModel):
    """Response model for individual metrics."""
    message_id: str
    session_id: Optional[str]
    project_id: Optional[str]
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float
    actual_cost: Optional[float]
    created_at: str
    response_time_ms: Optional[int]
    stop_reason: Optional[str]
    tool_calls_count: int


class SessionMetricsResponse(BaseModel):
    """Response model for session metrics."""
    session_id: str
    project_id: Optional[str]
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_estimated_cost: float
    total_actual_cost: Optional[float]
    message_count: int
    created_at: str
    updated_at: str
    models_used: Optional[str]


class ProjectMetricsResponse(BaseModel):
    """Response model for project metrics."""
    project_id: str
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_estimated_cost: float
    total_actual_cost: Optional[float]
    session_count: int
    message_count: int
    created_at: str
    updated_at: str
    name: Optional[str]
    description: Optional[str]


# Routes

@router.get("/message/{message_id}")
async def get_message_metrics(message_id: str):
    """
    Get metrics for a specific message.
    
    Args:
        message_id: Message ID to query
        
    Returns:
        Message metrics
    """
    try:
        db_manager = get_db_manager()
        metrics = await db_manager.get_message_metrics(message_id)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Message metrics not found")
        
        return {
            "status": "success",
            "metrics": metrics.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving message metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}")
async def get_session_metrics(session_id: str, include_messages: bool = False):
    """
    Get metrics for a session.
    
    Args:
        session_id: Session ID to query
        include_messages: Whether to include individual message metrics
        
    Returns:
        Session metrics and optionally message list
    """
    try:
        db_manager = get_db_manager()
        metrics = await db_manager.get_session_metrics(session_id)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Session metrics not found")
        
        response = {
            "status": "success",
            "metrics": metrics.to_dict()
        }
        
        if include_messages:
            messages = await db_manager.get_session_messages(session_id)
            response["messages"] = [msg.to_dict() for msg in messages]
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/summary")
async def get_session_summary(session_id: str):
    """
    Get aggregated summary for a session.
    
    Args:
        session_id: Session ID to query
        
    Returns:
        Aggregated session summary
    """
    try:
        db_manager = get_db_manager()
        metrics = await db_manager.get_session_metrics(session_id)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Session metrics not found")
        
        return {
            "status": "success",
            "summary": {
                "session_id": metrics.session_id,
                "message_count": metrics.message_count,
                "total_tokens": metrics.total_tokens,
                "estimated_cost_usd": metrics.total_estimated_cost,
                "actual_cost_usd": metrics.total_actual_cost,
                "average_tokens_per_message": (
                    metrics.total_tokens / metrics.message_count
                    if metrics.message_count > 0 else 0
                ),
                "average_cost_per_message": (
                    metrics.total_estimated_cost / metrics.message_count
                    if metrics.message_count > 0 else 0
                )
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/project/{project_id}")
async def get_project_metrics(project_id: str, include_sessions: bool = False):
    """
    Get metrics for a project.
    
    Args:
        project_id: Project ID to query
        include_sessions: Whether to include session metrics
        
    Returns:
        Project metrics and optionally session list
    """
    try:
        db_manager = get_db_manager()
        metrics = await db_manager.get_project_metrics(project_id)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Project metrics not found")
        
        response = {
            "status": "success",
            "metrics": metrics.to_dict()
        }
        
        if include_sessions:
            sessions = await db_manager.get_project_sessions(project_id)
            response["sessions"] = [session.to_dict() for session in sessions]
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving project metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/project/{project_id}/summary")
async def get_project_summary(project_id: str):
    """
    Get aggregated summary for a project.
    
    Args:
        project_id: Project ID to query
        
    Returns:
        Aggregated project summary
    """
    try:
        db_manager = get_db_manager()
        metrics = await db_manager.get_project_metrics(project_id)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Project metrics not found")
        
        return {
            "status": "success",
            "summary": {
                "project_id": metrics.project_id,
                "name": metrics.name,
                "session_count": metrics.session_count,
                "message_count": metrics.message_count,
                "total_tokens": metrics.total_tokens,
                "estimated_cost_usd": metrics.total_estimated_cost,
                "actual_cost_usd": metrics.total_actual_cost,
                "average_tokens_per_session": (
                    metrics.total_tokens / metrics.session_count
                    if metrics.session_count > 0 else 0
                ),
                "average_cost_per_session": (
                    metrics.total_estimated_cost / metrics.session_count
                    if metrics.session_count > 0 else 0
                )
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving project summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects")
async def list_projects():
    """
    List all projects with metrics.
    
    Returns:
        List of all projects
    """
    try:
        db_manager = get_db_manager()
        projects = await db_manager.list_all_projects()
        
        return {
            "status": "success",
            "projects": [project.to_dict() for project in projects],
            "count": len(projects)
        }
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))
