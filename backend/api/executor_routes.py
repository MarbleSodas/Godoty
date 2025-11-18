"""
Executor API Routes.

API endpoints for the executor agent.
"""

import logging
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from ..agents.executor_agent import get_executor_agent
from ..models.executor_api import (
    ExecutePlanRequest,
    StreamEventModel,
    ExecutionStatus,
    ErrorResponse
)

logger = logging.getLogger(__name__)

# Create router
executor_router = APIRouter(prefix="/api/executor", tags=["executor"])


@executor_router.post("/execute", response_model=EventSourceResponse)
async def execute_plan(request: ExecutePlanRequest):
    """
    Execute a plan with streaming events.

    Args:
        request: Execution request with structured plan

    Returns:
        Server-Sent Events stream
    """
    try:
        agent = get_executor_agent()

        async def event_stream():
            try:
                async for event in agent.execute_plan(request.plan, request.context):
                    yield {
                        "event": event.type,
                        "data": {
                            **event.data,
                            "timestamp": event.timestamp.isoformat()
                        }
                    }
            except Exception as e:
                logger.error(f"Execution stream error: {e}")
                yield {
                    "event": "error",
                    "data": {
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                }

        return EventSourceResponse(event_stream())

    except Exception as e:
        logger.error(f"Execute plan failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@executor_router.get("/status/{execution_id}", response_model=ExecutionStatus)
async def get_execution_status(execution_id: str):
    """
    Get execution status.

    Args:
        execution_id: Execution ID

    Returns:
        Execution status
    """
    try:
        agent = get_executor_agent()
        status = agent.get_execution_status(execution_id)

        if status is None:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )

        return ExecutionStatus(**status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get status failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@executor_router.post("/cancel/{execution_id}")
async def cancel_execution(execution_id: str):
    """
    Cancel an execution.

    Args:
        execution_id: Execution ID

    Returns:
        Success response
    """
    try:
        agent = get_executor_agent()
        success = await agent.cancel_execution(execution_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )

        return {"message": "Execution cancelled", "execution_id": execution_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel execution failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@executor_router.get("/active")
async def list_active_executions():
    """
    List active executions.

    Returns:
        List of active executions
    """
    try:
        agent = get_executor_agent()
        executions = agent.list_active_executions()
        return {"executions": executions, "count": len(executions)}

    except Exception as e:
        logger.error(f"List executions failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@executor_router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "service": "simple-executor",
        "timestamp": datetime.now().isoformat()
    }