"""
FastAPI routes for metrics tracking.

Provides endpoints for querying token usage and cost metrics at
api call, session, and project levels.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.db import get_metrics_db

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/metrics", tags=["metrics"])


# Response Models
class MetricsResponse(BaseModel):
    """Response model for individual API call metrics."""
    call_id: Optional[str] = None
    session_id: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float
    timestamp: Optional[float] = None


class SessionMetricsResponse(BaseModel):
    """Response model for session metrics."""
    session_id: str
    total_tokens: int
    total_estimated_cost: float
    call_count: int


# Routes

@router.get("/session/{session_id}")
async def get_session_metrics(session_id: str, include_calls: bool = False):
    """
    Get metrics for a session.
    """
    try:
        db = get_metrics_db()
        metrics = db.get_session_metrics(session_id)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Session metrics not found")
        
        response = {
            "status": "success",
            "metrics": metrics
        }
        
        if include_calls:
            calls = db.get_session_calls(session_id)
            response["calls"] = calls
        
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
    """
    try:
        db = get_metrics_db()
        metrics = db.get_session_metrics(session_id)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Session metrics not found")
        
        # Calculate averages safely
        call_count = metrics.get("call_count", 0)
        total_tokens = metrics.get("total_tokens", 0)
        total_cost = metrics.get("total_estimated_cost", 0.0)
        
        return {
            "status": "success",
            "summary": {
                "session_id": metrics["session_id"],
                "call_count": call_count,
                "total_tokens": total_tokens,
                "estimated_cost_usd": total_cost,
                "average_tokens_per_call": total_tokens / call_count if call_count > 0 else 0,
                "average_cost_per_call": total_cost / call_count if call_count > 0 else 0
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/project/{project_id}")
async def get_project_metrics(project_id: str):
    """
    Get metrics for a project (aggregated from all sessions).
    """
    try:
        db = get_metrics_db()
        all_sessions = db.get_all_sessions()
        
        total_tokens = sum(s["metrics"]["total_tokens"] for s in all_sessions)
        total_cost = sum(s["metrics"]["total_estimated_cost"] for s in all_sessions)
        
        return {
            "status": "success",
            "metrics": {
                "project_id": project_id,
                "total_tokens": total_tokens,
                "total_estimated_cost": total_cost,
                "session_count": len(all_sessions)
            }
        }
    except Exception as e:
        logger.error(f"Error retrieving project metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

