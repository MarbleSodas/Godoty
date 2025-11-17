"""
FastAPI routes for the planning agent.

Provides endpoints for interacting with the planning agent:
- Streaming responses with SSE
- Non-streaming responses
- Session management
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents import get_planning_agent, close_planning_agent

logger = logging.getLogger(__name__)

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
        PlanResponse with generated plan
    """
    try:
        # Get agent
        agent = get_planning_agent()

        # Reset conversation if requested
        if request.reset_conversation:
            agent.reset_conversation()

        # Generate plan
        plan = await agent.plan_async(request.prompt)

        return PlanResponse(
            status="success",
            plan=plan
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
