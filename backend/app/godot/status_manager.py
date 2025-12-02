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
                "protocol": "websocket",
                "websocket_connected": False
            }
        }

        # Active streams to broadcast to
        self.active_streams: set[str] = set()

        # WebSocket client (initialized later)
        self.websocket_client = None

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

    async def initialize_websocket_client(self) -> None:
        """
        Initialize WebSocket client for Godot connection.
        """
        try:
            from app.godot.websocket_client import GodotWebSocketClient
            from app.config import settings

            if not self.websocket_client:
                self.websocket_client = GodotWebSocketClient(
                    settings=settings,
                    status_manager=self
                )
                logger.info("[GodotStatusManager] WebSocket client initialized")

        except Exception as e:
            logger.error(f"[GodotStatusManager] Failed to initialize WebSocket client: {e}")
            self.set_error(f"WebSocket client initialization failed: {str(e)}")

    async def connect_to_godot(self) -> bool:
        """
        Connect to Godot WebSocket server.

        Returns:
            True if connection successful, False otherwise
        """
        if not self.websocket_client:
            await self.initialize_websocket_client()

        if self.websocket_client:
            return await self.websocket_client.connect()
        return False

    async def disconnect_from_godot(self) -> None:
        """
        Disconnect from Godot WebSocket server.
        """
        if self.websocket_client:
            await self.websocket_client.disconnect()

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

        update_str = ", ".join(f"{k}={v}" for k, v in updates.items())
        logger.info(f"[GodotStatusManager] Status updated: {update_str}")
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
        Check Godot connection status and update accordingly.

        Real implementation using WebSocket client to monitor connection health.
        """
        if not self.websocket_client:
            # Initialize WebSocket client if not already done
            await self.initialize_websocket_client()

        if self.websocket_client:
            # Get current connection state from WebSocket client
            connection_state = self.websocket_client.get_connection_state()
            connection_info = self.websocket_client.get_connection_info()

            # Update status based on WebSocket connection
            if connection_state.value == "connected":
                self.update_status({
                    "state": "connected",
                    "error": None
                })
            elif connection_state.value == "error":
                self.update_status({
                    "state": "error",
                    "error": "WebSocket connection error"
                })
            elif connection_state.value == "disconnected":
                # Try to connect if auto-reconnect is disabled
                if not self.websocket_client.enable_auto_reconnect:
                    logger.debug("[GodotStatusManager] Attempting to connect to Godot...")
                    await self.websocket_client.connect()
            else:
                # For connecting or reconnecting states
                self.update_status({
                    "state": connection_state.value,
                    "error": None
                })

            # Update connection details
            self.update_status({
                "connection_details": connection_info
            })
        else:
            # WebSocket client not available
            logger.warning("[GodotStatusManager] WebSocket client not initialized")

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
        Shutdown the status manager and clean up all streams and WebSocket connections.
        """
        logger.info(f"[GodotStatusManager] Shutting down {len(self.active_streams)} active streams")

        # Clean up WebSocket client
        if self.websocket_client:
            await self.websocket_client.cleanup()
            self.websocket_client = None

        # Clear active streams
        self.active_streams.clear()

        logger.info("[GodotStatusManager] Shutdown completed")