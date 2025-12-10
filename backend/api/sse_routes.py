"""
Server-Sent Events (SSE) routes for real-time Godot connection status updates.
"""

import asyncio
import json
import logging
from datetime import datetime
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
        
        # Add chat readiness info
        try:
            from config_manager import get_config
            config = get_config()
            api_key_configured = config.is_configured
            godot_connected = status.get("state") == "connected"
            chat_ready = godot_connected and api_key_configured
            
            if not api_key_configured:
                chat_message = "Please configure your OpenRouter API key in Settings to start chatting."
            elif not godot_connected:
                chat_message = "Please connect to the Godot editor to start chatting."
            else:
                chat_message = "Ready to chat!"
            
            event_data["chat_ready"] = {
                "ready": chat_ready,
                "godot_connected": godot_connected,
                "api_key_configured": api_key_configured,
                "message": chat_message
            }
        except Exception:
            event_data["chat_ready"] = {
                "ready": False,
                "godot_connected": False,
                "api_key_configured": False,
                "message": "Unable to check chat readiness"
            }


        # Add context engine index status if available
        try:
            from agents.tools.context_tools import get_context_engine
            engine = get_context_engine()
            if engine:
                progress = engine.get_index_progress()
                event_data["index_status"] = progress.to_dict()
            else:
                event_data["index_status"] = {
                    "status": "not_started",
                    "phase": "Not indexed",
                    "current_step": 0,
                    "total_steps": 0,
                    "current_file": "",
                    "error": None,
                    "started_at": None,
                    "completed_at": None,
                    "progress_percent": 0
                }
        except Exception:
            event_data["index_status"] = {
                "status": "not_started",
                "phase": "Not indexed",
                "current_step": 0,
                "total_steps": 0,
                "current_file": "",
                "error": None,
                "started_at": None,
                "completed_at": None,
                "progress_percent": 0
            }

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
        
        # Add chat readiness info
        try:
            from config_manager import get_config
            config = get_config()
            api_key_configured = config.is_configured
            godot_connected = initial_status.get("state") == "connected"
            chat_ready_status = godot_connected and api_key_configured
            
            if not api_key_configured:
                chat_message = "Please configure your OpenRouter API key in Settings to start chatting."
            elif not godot_connected:
                chat_message = "Please connect to the Godot editor to start chatting."
            else:
                chat_message = "Ready to chat!"
            
            initial_data["chat_ready"] = {
                "ready": chat_ready_status,
                "godot_connected": godot_connected,
                "api_key_configured": api_key_configured,
                "message": chat_message
            }
        except Exception:
            initial_data["chat_ready"] = {
                "ready": False,
                "godot_connected": False,
                "api_key_configured": False,
                "message": "Unable to check chat readiness"
            }

        # Add context engine index status if available
        try:
            from agents.tools.context_tools import get_context_engine
            engine = get_context_engine()
            if engine:
                progress = engine.get_index_progress()
                initial_data["index_status"] = progress.to_dict()
            else:
                # No context engine yet - send default status
                initial_data["index_status"] = {
                    "status": "not_started",
                    "phase": "Not indexed",
                    "current_step": 0,
                    "total_steps": 0,
                    "current_file": "",
                    "error": None,
                    "started_at": None,
                    "completed_at": None,
                    "progress_percent": 0
                }
        except Exception as e:
            logger.debug(f"Could not get index status: {e}")
            initial_data["index_status"] = {
                "status": "not_started",
                "phase": "Not indexed",
                "current_step": 0,
                "total_steps": 0,
                "current_file": "",
                "error": None,
                "started_at": None,
                "completed_at": None,
                "progress_percent": 0
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


@router.get("/godot/status")
async def get_godot_status():
    """
    Get current Godot connection status (one-time, not streaming).

    Returns:
        Current connection status dictionary
    """
    monitor = get_connection_monitor()
    return monitor.get_status()


@router.get("/context/index/status")
async def get_context_index_status():
    """
    Get current context engine index status.
    
    Returns:
        Dictionary with index progress and metadata
    """
    try:
        from agents.tools.context_tools import get_context_engine
        
        engine = get_context_engine()
        if engine is None:
            return {
                "status": "not_initialized",
                "message": "Context engine not initialized. Connect to a Godot project first."
            }
        
        progress = engine.get_index_progress()
        metadata = engine.get_index_metadata()
        
        result = {
            "status": "ok",
            "progress": progress.to_dict(),
            "indexed": engine.is_indexed(),
            "project_path": engine.project_path
        }
        
        if metadata:
            result["metadata"] = metadata.to_dict()
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting context index status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/godoty/connection/status")
async def get_godoty_connection_status():
    """
    Get current Godot Editor connection status (compatibility endpoint).

    This endpoint provides compatibility for the frontend that expects
    /api/godoty/connection/status path.

    Returns:
        Dictionary with connection status, project info, and metadata
    """
    try:
        # Try to use GodotBridge if available
        try:
            from agents.tools.godot_bridge import GodotBridge, ConnectionState

            godot_bridge = GodotBridge()
            is_connected = godot_bridge.is_connected()
            project_info = None

            if is_connected:
                try:
                    project_info = godot_bridge.get_project_info()
                    # Handle both sync and async versions
                    if hasattr(project_info, '__await__'):
                        # It's a coroutine, try to get the current project info synchronously
                        project_info = getattr(godot_bridge, 'project_info', None)
                    # Now check if we can convert to dict
                    if project_info and hasattr(project_info, 'dict'):
                        project_info = project_info.dict()
                except Exception as e:
                    logger.warning(f"Could not get project info: {e}")
                    project_info = None

            return {
                "status": "connected" if is_connected else "disconnected",
                "connection_state": godot_bridge.connection_state.name,
                "project_info": project_info,
                "project_path": getattr(project_info, 'project_path', None) if project_info else None,
                "project_settings": getattr(project_info, 'project_settings', {}) if project_info else {},
                "last_checked": datetime.utcnow().isoformat()
            }
        except ImportError:
            # Fallback to connection monitor if GodotBridge not available
            monitor = get_connection_monitor()
            status = monitor.get_status()

            return {
                "status": "connected" if status.get("state") == "connected" else "disconnected",
                "connection_state": status.get("state", "UNKNOWN").upper(),
                "project_info": None,
                "project_path": status.get("project_path"),
                "project_settings": status.get("project_settings", {}),
                "godot_version": status.get("godot_version"),
                "plugin_version": status.get("plugin_version"),
                "last_checked": status.get("last_attempt", datetime.utcnow().isoformat())
            }

    except Exception as e:
        logger.error(f"Error getting connection status: {e}")
        return {
            "status": "error",
            "connection_state": "ERROR",
            "project_info": None,
            "project_path": None,
            "project_settings": {},
            "error": str(e),
            "last_checked": datetime.utcnow().isoformat()
        }


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
