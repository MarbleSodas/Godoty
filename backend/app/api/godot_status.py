"""
FastAPI endpoints for Godot status streaming via Server-Sent Events (SSE).

Provides real-time status updates to the frontend about Godot engine
connection state, project information, and system status.
"""

import asyncio
import logging
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.streaming import create_sse_response
from app.godot.status_manager import GodotStatusManager
from app.config import settings

logger = logging.getLogger(__name__)

# Create FastAPI router
router = APIRouter()

# Global status manager instance
status_manager = GodotStatusManager()


@router.get("/godot/status/stream")
async def stream_godot_status() -> StreamingResponse:
    """
    Server-Sent Events endpoint for real-time Godot status updates.

    Returns:
        SSE streaming response with real-time Godot status

    Raises:
        HTTPException: If streaming fails to initialize
    """
    try:
        # Generate unique stream ID
        stream_id = str(uuid.uuid4())

        logger.info(f"[GodotStatus] Starting SSE stream {stream_id}")

        # Create SSE response
        response = await create_sse_response(stream_id)

        # Start broadcasting status in the background
        asyncio.create_task(
            status_manager.broadcast_to_stream(stream_id)
        )

        return response

    except Exception as e:
        logger.error(f"[GodotStatus] Failed to create SSE stream: {e}")
        raise HTTPException(status_code=500, detail="Failed to start status stream")


@router.get("/godot/status")
async def get_godot_status() -> dict:
    """
    Get current Godot status (non-streaming endpoint).

    Returns:
        Current Godot status as JSON
    """
    try:
        return status_manager.get_status()
    except Exception as e:
        logger.error(f"[GodotStatus] Failed to get status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Godot status")


@router.post("/godot/status/update")
async def update_godot_status(status_update: dict) -> dict:
    """
    Update Godot status (for testing or external status updates).

    Args:
        status_update: Dictionary with status fields to update

    Returns:
        Updated status
    """
    try:
        updated_status = status_manager.update_status(status_update)
        logger.info(f"[GodotStatus] Status updated: {updated_status}")
        return updated_status
    except Exception as e:
        logger.error(f"[GodotStatus] Failed to update status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update Godot status")


@router.get("/api-key/status")
async def get_api_key_status() -> dict:
    """
    Get OpenRouter API key configuration status.

    Returns:
        API key status including whether it's configured in environment
    """
    try:
        has_key = bool(settings.openrouter_api_key and settings.openrouter_api_key.strip())
        key_prefix = settings.openrouter_api_key[:10] + "..." if has_key else None

        return {
            "hasKey": has_key,
            "hasBackendKey": has_key,
            "allowUserOverride": True,
            "apiKeyPrefix": key_prefix,
            "source": "environment" if has_key else "none"
        }
    except Exception as e:
        logger.error(f"[GodotStatus] Failed to get API key status: {e}")
        return {
            "hasKey": False,
            "hasBackendKey": False,
            "allowUserOverride": True,
            "apiKeyPrefix": None,
            "source": "error",
            "error": str(e)
        }