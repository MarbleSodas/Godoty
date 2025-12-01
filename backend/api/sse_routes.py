"""
Server-Sent Events (SSE) routes for real-time Godot connection status updates.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from services import get_connection_monitor
from services.godot_connection_monitor import ConnectionEvent
from utils.serialization import safe_json_dumps

logger = logging.getLogger(__name__)

router = APIRouter()


def extract_project_name(project_info, project_settings, project_path):
    """Extract project name with multiple fallback options."""
    if project_info and hasattr(project_info, 'project_name') and project_info.project_name:
        return project_info.project_name

    if project_settings and project_settings.get('name'):
        return project_settings['name']

    if project_path:
        import os
        return os.path.basename(project_path.rstrip('/'))

    return None


class SSEManager:
    """Manager for SSE client connections."""

    def __init__(self):
        self.clients: set[asyncio.Queue] = set()

    def add_client(self, queue: asyncio.Queue):
        """Add a new SSE client."""
        self.clients.add(queue)
        logger.info(f"SSE client connected. Total clients: {len(self.clients)}")

    def remove_client(self, queue: asyncio.Queue):
        """Remove an SSE client."""
        self.clients.discard(queue)
        logger.info(f"SSE client disconnected. Total clients: {len(self.clients)}")

    async def broadcast(self, event: ConnectionEvent):
        """Broadcast an event to all connected clients."""
        if not self.clients:
            return

        # Prepare event data with defensive error handling
        try:
            event_data = event.to_dict()
        except Exception as e:
            logger.error(f"Error serializing event: {e}")
            event_data = {
                "state": "error",
                "timestamp": event.timestamp.isoformat() if hasattr(event, 'timestamp') else None,
                "error": "Failed to serialize event data"
            }

        # Add project info with defensive error handling
        try:
            monitor = get_connection_monitor()
            status = monitor.get_status()
            project_info = None

            # Defensive access to bridge and project_info
            if hasattr(monitor, 'bridge') and monitor.bridge:
                project_info = getattr(monitor.bridge, 'project_info', None)

            project_name = extract_project_name(
                project_info,
                status.get("project_settings", {}),
                status.get("project_path")
            )

            event_data.update({
                "project_path": status.get("project_path"),
                "project_name": project_name,
                "godot_version": status.get("godot_version"),
                "plugin_version": status.get("plugin_version"),
                "project_settings": status.get("project_settings", {})
            })
        except Exception as e:
            logger.warning(f"Failed to enrich event data with project info: {e}")
            # Continue with basic event_data without project info

        # Send to all clients with enhanced error handling
        disconnected_clients = set()
        for client_queue in self.clients:
            try:
                await asyncio.wait_for(client_queue.put(event_data), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("Client queue full, disconnecting slow client")
                disconnected_clients.add(client_queue)
            except asyncio.QueueFull:
                logger.warning("Client queue full, disconnecting slow client")
                disconnected_clients.add(client_queue)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected_clients.add(client_queue)

        # Remove disconnected clients
        for client in disconnected_clients:
            self.remove_client(client)


# Global SSE manager
sse_manager = SSEManager()


async def event_generator(client_queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    """
    Generate SSE events from the client queue.

    Yields:
        SSE formatted event strings
    """
    try:
        # Send initial status with defensive error handling
        try:
            monitor = get_connection_monitor()
            initial_status = monitor.get_status()

            # Defensive access to bridge and project_info
            project_info = None
            if hasattr(monitor, 'bridge') and monitor.bridge:
                project_info = getattr(monitor.bridge, 'project_info', None)

            project_name = extract_project_name(
                project_info,
                initial_status.get("project_settings", {}),
                initial_status.get("project_path")
            )

            initial_data = {
                "state": initial_status.get("state"),
                "timestamp": initial_status.get("last_attempt"),
                "project_path": initial_status.get("project_path"),
                "project_name": project_name,
                "godot_version": initial_status.get("godot_version"),
                "plugin_version": initial_status.get("plugin_version"),
                "project_settings": initial_status.get("project_settings", {})
            }
            yield f"data: {safe_json_dumps(initial_data)}\n\n"
        except Exception as e:
            logger.error(f"Error sending initial status: {e}")
            # Send a minimal safe initial status
            fallback_data = {
                "state": "unknown",
                "timestamp": None,
                "project_path": None,
                "project_name": None,
                "godot_version": None,
                "plugin_version": None,
                "project_settings": {},
                "error": "Failed to get initial status"
            }
            yield f"data: {safe_json_dumps(fallback_data)}\n\n"

        # Stream events with enhanced error handling
        while True:
            try:
                # Wait for events with timeout to send keepalive
                event_data = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                yield f"data: {safe_json_dumps(event_data)}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield ": keepalive\n\n"
            except asyncio.CancelledError:
                logger.info("Event generator cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing event data: {e}")
                # Send error event but continue streaming
                error_data = {
                    "state": "error",
                    "timestamp": None,
                    "error": "Failed to process event data"
                }
                yield f"data: {safe_json_dumps(error_data)}\n\n"

    except Exception as e:
        logger.error(f"Critical error in event generator: {e}")
        # Try to send error notification before dying
        try:
            error_data = {
                "state": "error",
                "timestamp": None,
                "error": "Event generator failed"
            }
            yield f"data: {safe_json_dumps(error_data)}\n\n"
        except Exception:
            # If we can't even serialize the error, just give up
            pass
        raise
    finally:
        sse_manager.remove_client(client_queue)


@router.get("/godot/status")
async def get_godot_status():
    """Get current Godot connection status (REST endpoint)"""
    try:
        monitor = get_connection_monitor()
        status = monitor.get_status()
        return status
    except Exception as e:
        logger.error(f"Error getting Godot status: {e}")
        # Return a safe fallback status instead of just throwing an error
        return {
            "state": "error",
            "running": False,
            "project_path": None,
            "godot_version": None,
            "plugin_version": None,
            "project_settings": {},
            "error": f"Failed to get status: {str(e)}",
            "performance": {
                "total_connections": 0,
                "successful_connections": 0,
                "success_rate": 0.0,
                "total_downtime": 0.0,
                "uptime_percentage": 0.0,
                "last_successful_connection": None,
                "currently_in_downtime": False
            },
            "error_statistics": {
                "error_type_counts": {},
                "recent_failures": 0,
                "total_failures": 0
            },
            "bridge_stats": None,
            "retry_logic": {
                "backoff_multiplier": 2.0,
                "max_backoff": 60.0,
                "jitter_factor": 0.1,
                "adaptive_enabled": True
            },
            "recent_errors": []
        }


@router.get("/godot/status/stream")
async def stream_godot_status():
    """
    Stream real-time Godot connection status updates via Server-Sent Events (SSE).

    Returns:
        StreamingResponse with SSE events containing connection status updates

    Example event:
        ```
        data: {"state": "connected", "timestamp": "2025-11-19T...", "project_path": "...", ...}
        ```
    """
    # Create queue for this client
    client_queue = asyncio.Queue(maxsize=10)

    # Register with SSE manager
    sse_manager.add_client(client_queue)

    return StreamingResponse(
        event_generator(client_queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive"
        }
    )




def setup_sse_listener():
    """
    Setup the connection monitor listener to broadcast to SSE clients.
    Should be called during app initialization.
    """
    monitor = get_connection_monitor()

    async def on_state_change(event: ConnectionEvent):
        """Callback for connection state changes."""
        await sse_manager.broadcast(event)

    monitor.add_state_change_listener(on_state_change)
    logger.info("SSE listener registered with connection monitor")
