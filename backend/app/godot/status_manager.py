"""
Godot Status Manager

Manages Godot engine connection state and provides real-time status updates
via Server-Sent Events (SSE) for the frontend.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, AsyncGenerator, Optional

logger = logging.getLogger(__name__)


class GodotStatusManager:
    """
    Manages Godot engine status and provides real-time updates via SSE streaming.

    This class tracks the current state of Godot integration and broadcasts
    status updates to connected frontend clients via Server-Sent Events.
    """

    def __init__(self):
        """Initialize the Godot Status Manager with default status."""
        self.current_status = {
            "state": "disconnected",  # disconnected, connected, connecting, error
            "timestamp": datetime.utcnow().isoformat(),
            "project_name": None,
            "project_path": None,
            "godot_version": None,
            "plugin_version": "1.0.0",
            "error": None,
            "connection_details": {
                "host": "localhost",
                "port": 6007,  # Default Godot remote debug port
                "protocol": "websocket"
            }
        }

        # Active streams to broadcast to
        self.active_streams: set[str] = set()

        logger.info("[GodotStatusManager] Initialized with disconnected status")

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current Godot status.

        Returns:
            Current status dictionary with timestamp
        """
        # Update timestamp before returning
        self.current_status["timestamp"] = datetime.utcnow().isoformat()
        return self.current_status.copy()

    def update_status(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update specific fields in the current status.

        Args:
            updates: Dictionary with status fields to update

        Returns:
            Updated status dictionary
        """
        # Deep merge the updates
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(self.current_status.get(key), dict):
                self.current_status[key].update(value)
            else:
                self.current_status[key] = value

        self.current_status["timestamp"] = datetime.utcnow().isoformat()

        logger.info(f"[GodotStatusManager] Status updated: {key}={value for key, value in updates.items()}")
        return self.get_status()

    async def broadcast_to_stream(self, stream_id: str) -> None:
        """
        Broadcast status updates to a specific SSE stream using the existing SSE infrastructure.

        Args:
            stream_id: Unique identifier for the SSE stream
        """
        from app.api.streaming import sse_streamer

        try:
            # Create stream queue
            queue = await sse_streamer.create_stream(stream_id)
            self.active_streams.add(stream_id)
            logger.info(f"[GodotStatusManager] Started broadcasting to stream {stream_id}")

            # Send initial status immediately
            initial_status = {
                "type": "godot_status",
                "data": self.get_status()
            }
            await sse_streamer.send_event(stream_id, initial_status)

            # Continue broadcasting updates periodically
            while stream_id in self.active_streams:
                try:
                    # Check for Godot connection (mock implementation)
                    await self._check_godot_connection()

                    # Broadcast current status
                    status = {
                        "type": "godot_status",
                        "data": self.get_status()
                    }
                    await sse_streamer.send_event(stream_id, status)

                    # Wait before next update
                    await asyncio.sleep(5)  # Update every 5 seconds

                except asyncio.CancelledError:
                    logger.info(f"[GodotStatusManager] Stream {stream_id} cancelled")
                    break
                except Exception as e:
                    logger.error(f"[GodotStatusManager] Error in stream {stream_id}: {e}")
                    # Send error status and continue
                    error_status_data = self.get_status()
                    error_status_data["error"] = str(e)
                    error_status_data["state"] = "error"

                    error_status = {
                        "type": "godot_status",
                        "data": error_status_data
                    }
                    await sse_streamer.send_event(stream_id, error_status)
                    await asyncio.sleep(5)

        finally:
            # Clean up when stream ends
            self.active_streams.discard(stream_id)
            await sse_streamer.remove_stream(stream_id)
            logger.info(f"[GodotStatusManager] Stopped broadcasting to stream {stream_id}")

    async def start_status_broadcasting(self, stream_id: str) -> AsyncGenerator[str, None]:
        """
        Start broadcasting status updates to a specific SSE stream (legacy method).

        Args:
            stream_id: Unique identifier for the SSE stream

        Yields:
            SSE-formatted status updates
        """
        self.active_streams.add(stream_id)
        logger.info(f"[GodotStatusManager] Started broadcasting to stream {stream_id}")

        try:
            # Send initial status immediately
            yield self._format_sse_message(self.get_status())

            # Continue broadcasting updates periodically
            while stream_id in self.active_streams:
                try:
                    # Check for Godot connection (mock implementation)
                    await self._check_godot_connection()

                    # Broadcast current status
                    status = self.get_status()
                    yield self._format_sse_message(status)

                    # Wait before next update
                    await asyncio.sleep(5)  # Update every 5 seconds

                except asyncio.CancelledError:
                    logger.info(f"[GodotStatusManager] Stream {stream_id} cancelled")
                    break
                except Exception as e:
                    logger.error(f"[GodotStatusManager] Error in stream {stream_id}: {e}")
                    # Send error status and continue
                    error_status = self.get_status()
                    error_status["error"] = str(e)
                    error_status["state"] = "error"
                    yield self._format_sse_message(error_status)
                    await asyncio.sleep(5)

        finally:
            # Clean up when stream ends
            self.active_streams.discard(stream_id)
            logger.info(f"[GodotStatusManager] Stopped broadcasting to stream {stream_id}")

    async def _check_godot_connection(self) -> None:
        """
        Check if Godot is running and update status accordingly.

        This is a mock implementation for development. In production,
        this would establish actual WebSocket communication with Godot.
        """
        # Mock implementation - in real scenario, this would:
        # 1. Try to connect to Godot via WebSocket/IPC
        # 2. Detect running projects
        # 3. Get project metadata
        # 4. Monitor connection health

        # For now, simulate a disconnected state
        # This can be enhanced later to actually detect Godot
        current_state = self.current_status.get("state", "disconnected")

        # Mock: if disconnected, try to connect every 30 seconds
        if current_state == "disconnected":
            # In real implementation, this would try to connect to Godot
            # For now, we stay disconnected but show we're checking
            logger.debug("[GodotStatusManager] Checking for Godot connection...")

    def _format_sse_message(self, data: Dict[str, Any]) -> str:
        """
        Format data as a Server-Sent Events message.

        Args:
            data: Dictionary to format as SSE message

        Returns:
            SSE-formatted string
        """
        json_data = json.dumps(data, ensure_ascii=False)
        return f"data: {json_data}\n\n"

    def set_connected(self, project_name: str, project_path: str, godot_version: str = None) -> None:
        """
        Set status as connected to a Godot project.

        Args:
            project_name: Name of the connected Godot project
            project_path: Path to the Godot project
            godot_version: Version of Godot engine
        """
        self.update_status({
            "state": "connected",
            "project_name": project_name,
            "project_path": project_path,
            "godot_version": godot_version,
            "error": None
        })

    def set_disconnected(self, reason: str = None) -> None:
        """
        Set status as disconnected from Godot.

        Args:
            reason: Optional reason for disconnection
        """
        updates = {
            "state": "disconnected",
            "project_name": None,
            "project_path": None,
            "godot_version": None,
            "error": reason
        }
        self.update_status(updates)

    def set_error(self, error_message: str) -> None:
        """
        Set status as error state.

        Args:
            error_message: Description of the error
        """
        self.update_status({
            "state": "error",
            "error": error_message
        })

    def get_active_stream_count(self) -> int:
        """
        Get the number of active SSE streams.

        Returns:
            Number of active streams
        """
        return len(self.active_streams)

    async def shutdown(self) -> None:
        """
        Shutdown the status manager and clean up all streams.
        """
        logger.info(f"[GodotStatusManager] Shutting down {len(self.active_streams)} active streams")
        self.active_streams.clear()