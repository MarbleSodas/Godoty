"""
Server-Sent Events (SSE) routes for real-time Godot connection status updates.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from services import get_connection_monitor
from services.godot_connection_monitor import ConnectionEvent

logger = logging.getLogger(__name__)

router = APIRouter()


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

        # Prepare event data
        event_data = event.to_dict()

        # Add project info if connected
        monitor = get_connection_monitor()
        status = monitor.get_status()
        event_data.update({
            "project_path": status.get("project_path"),
            "godot_version": status.get("godot_version"),
            "plugin_version": status.get("plugin_version"),
            "project_settings": status.get("project_settings", {})
        })

        # Send to all clients
        disconnected_clients = set()
        for client_queue in self.clients:
            try:
                await asyncio.wait_for(client_queue.put(event_data), timeout=1.0)
            except asyncio.TimeoutError:
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
        # Send initial status
        monitor = get_connection_monitor()
        initial_status = monitor.get_status()

        # Format as SSE
        initial_data = {
            "state": initial_status.get("state"),
            "timestamp": initial_status.get("last_attempt"),
            "project_path": initial_status.get("project_path"),
            "godot_version": initial_status.get("godot_version"),
            "plugin_version": initial_status.get("plugin_version"),
            "project_settings": initial_status.get("project_settings", {})
        }
        yield f"data: {json.dumps(initial_data)}\n\n"

        # Stream events
        while True:
            # Wait for events with timeout to send keepalive
            try:
                event_data = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event_data)}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield ": keepalive\n\n"
            except asyncio.CancelledError:
                logger.info("Event generator cancelled")
                break

    except Exception as e:
        logger.error(f"Error in event generator: {e}")
        raise
    finally:
        sse_manager.remove_client(client_queue)


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
