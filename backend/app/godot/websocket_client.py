"""
Godot WebSocket Client

Handles WebSocket connection to Godot engine for real-time communication.
Processes dynamic data from Godot and integrates with the status manager.
"""

import asyncio
import json
import logging
import websockets
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from enum import Enum

from app.config import Settings

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class GodotWebSocketClient:
    """
    Async WebSocket client for connecting to Godot engine.

    Features:
    - Automatic reconnection with exponential backoff
    - Dynamic message processing for any Godot data
    - Connection state management
    - Error handling and logging
    - Integration with status manager
    """

    def __init__(self, settings: Settings, status_manager, message_callback: Optional[Callable] = None):
        """
        Initialize WebSocket client.

        Args:
            settings: Application configuration
            status_manager: Status manager instance for integration
            message_callback: Optional callback for message processing
        """
        self.settings = settings
        self.status_manager = status_manager
        self.message_callback = message_callback

        # Connection state
        self.connection_state = ConnectionState.DISCONNECTED
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.connection_task: Optional[asyncio.Task] = None
        self.reconnect_task: Optional[asyncio.Task] = None

        # Connection configuration
        self.ws_url = f"ws://{self.settings.godot_ws_host}:{self.settings.godot_ws_port}"
        self.timeout = self.settings.godot_ws_timeout
        self.reconnect_interval = self.settings.godot_ws_reconnect_interval
        self.max_reconnect_attempts = self.settings.godot_ws_max_reconnect_attempts
        self.enable_auto_reconnect = self.settings.godot_ws_enable_auto_reconnect

        # Connection tracking
        self.reconnect_attempts = 0
        self.last_connected_time: Optional[datetime] = None
        self.message_count = 0
        self.last_message_time: Optional[datetime] = None

        logger.info(f"[GodotWebSocketClient] Initialized with URL: {self.ws_url}")

    async def connect(self) -> bool:
        """
        Connect to Godot WebSocket server.

        Returns:
            True if connection successful, False otherwise
        """
        if self.connection_state in [ConnectionState.CONNECTING, ConnectionState.CONNECTED]:
            logger.warning("[GodotWebSocketClient] Already connected or connecting")
            return True

        self._set_connection_state(ConnectionState.CONNECTING)

        try:
            logger.info(f"[GodotWebSocketClient] Connecting to {self.ws_url}")

            # Connect with timeout
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url,
                    ping_interval=20,  # Keep connection alive
                    ping_timeout=10
                ),
                timeout=self.timeout
            )

            # Start connection monitoring task
            self.connection_task = asyncio.create_task(self._connection_loop())

            self._set_connection_state(ConnectionState.CONNECTED)
            self.reconnect_attempts = 0
            self.last_connected_time = datetime.utcnow()

            logger.info("[GodotWebSocketClient] Successfully connected to Godot WebSocket server")

            # Update status manager
            self._update_status_manager()

            return True

        except asyncio.TimeoutError:
            error_msg = f"Connection timeout after {self.timeout} seconds"
            logger.error(f"[GodotWebSocketClient] {error_msg}")
            self._handle_connection_error(error_msg)
            return False

        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            logger.error(f"[GodotWebSocketClient] {error_msg}")
            self._handle_connection_error(error_msg)
            return False

    async def disconnect(self) -> None:
        """
        Disconnect from Godot WebSocket server.
        """
        logger.info("[GodotWebSocketClient] Disconnecting...")

        # Cancel ongoing tasks
        if self.connection_task:
            self.connection_task.cancel()
            try:
                await self.connection_task
            except asyncio.CancelledError:
                pass

        if self.reconnect_task:
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket connection
        if self.websocket:
            try:
                if hasattr(self.websocket, 'close'):
                    await self.websocket.close()
            except Exception as e:
                logger.warning(f"[GodotWebSocketClient] Error closing WebSocket: {e}")
            finally:
                self.websocket = None

        self._set_connection_state(ConnectionState.DISCONNECTED)
        self._update_status_manager()

        logger.info("[GodotWebSocketClient] Disconnected successfully")

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send a message to Godot WebSocket server.

        Args:
            message: Message dictionary to send

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self._is_connected():
            logger.warning("[GodotWebSocketClient] Cannot send message - not connected")
            return False

        try:
            message_str = json.dumps(message, ensure_ascii=False)
            await self.websocket.send(message_str)
            logger.debug(f"[GodotWebSocketClient] Sent message: {message_str}")
            return True

        except Exception as e:
            error_msg = f"Failed to send message: {str(e)}"
            logger.error(f"[GodotWebSocketClient] {error_msg}")
            self._handle_connection_error(error_msg)
            return False

    async def _connection_loop(self) -> None:
        """
        Main connection loop for receiving messages from Godot.
        """
        try:
            async for message in self.websocket:
                await self._process_message(message)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("[GodotWebSocketClient] Connection closed by server")
            self._handle_connection_disconnection()

        except websockets.exceptions.ConnectionClosedError as e:
            logger.error(f"[GodotWebSocketClient] Connection closed with error: {e}")
            self._handle_connection_disconnection()

        except Exception as e:
            error_msg = f"Unexpected error in connection loop: {str(e)}"
            logger.error(f"[GodotWebSocketClient] {error_msg}")
            self._handle_connection_error(error_msg)

    async def _process_message(self, message: str) -> None:
        """
        Process incoming message from Godot.

        Args:
            message: JSON message string from Godot
        """
        try:
            # Update message statistics
            self.message_count += 1
            self.last_message_time = datetime.utcnow()

            # Parse JSON message
            message_data = json.loads(message)
            logger.debug(f"[GodotWebSocketClient] Received message: {message_data}")

            # Process message based on its content
            await self._handle_dynamic_message(message_data)

            # Call custom message callback if provided
            if self.message_callback:
                try:
                    await self.message_callback(message_data)
                except Exception as e:
                    logger.error(f"[GodotWebSocketClient] Error in message callback: {e}")

        except json.JSONDecodeError as e:
            logger.error(f"[GodotWebSocketClient] Invalid JSON message: {e}")

        except Exception as e:
            logger.error(f"[GodotWebSocketClient] Error processing message: {e}")

    async def _handle_dynamic_message(self, message_data: Dict[str, Any]) -> None:
        """
        Handle dynamic message from Godot based on its structure.

        Args:
            message_data: Parsed JSON message from Godot
        """
        # Extract message type if available
        message_type = message_data.get("type", "unknown")

        # Update status manager with connection info
        if message_type == "connection_info":
            self.status_manager.update_status({
                "project_name": message_data.get("project_name"),
                "project_path": message_data.get("project_path"),
                "godot_version": message_data.get("godot_version"),
                "state": "connected"
            })

        # Handle different message types dynamically
        elif message_type == "status":
            self.status_manager.update_status(message_data)

        elif message_type == "error":
            self.status_manager.set_error(message_data.get("message", "Unknown error"))

        else:
            # For unknown message types, treat as real-time data
            # and broadcast via SSE
            await self._broadcast_realtime_data(message_data, message_type)

    async def _broadcast_realtime_data(self, data: Dict[str, Any], data_type: str) -> None:
        """
        Broadcast real-time data to frontend via SSE.

        Args:
            data: Real-time data from Godot
            data_type: Type of data for categorization
        """
        try:
            from app.api.streaming import sse_streamer

            # Create real-time data event
            realtime_event = {
                "type": "godot_realtime",
                "data": {
                    "data_type": data_type,
                    "payload": data,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message_count": self.message_count
                }
            }

            # Broadcast to all active streams
            for stream_id in self.status_manager.active_streams:
                await sse_streamer.send_event(stream_id, realtime_event)

        except Exception as e:
            logger.error(f"[GodotWebSocketClient] Error broadcasting real-time data: {e}")

    def _handle_connection_error(self, error_msg: str) -> None:
        """
        Handle connection error.

        Args:
            error_msg: Error message describing the issue
        """
        self._set_connection_state(ConnectionState.ERROR)
        self.status_manager.set_error(error_msg)

        # Start reconnection if enabled
        if self.enable_auto_reconnect and self.reconnect_attempts < self.max_reconnect_attempts:
            if not self.reconnect_task or self.reconnect_task.done():
                self.reconnect_task = asyncio.create_task(self._reconnect())

    def _handle_connection_disconnection(self) -> None:
        """
        Handle unexpected connection disconnection.
        """
        self._set_connection_state(ConnectionState.DISCONNECTED)
        self.status_manager.set_disconnected("Connection lost")

        # Start reconnection if enabled
        if self.enable_auto_reconnect and self.reconnect_attempts < self.max_reconnect_attempts:
            if not self.reconnect_task or self.reconnect_task.done():
                self.reconnect_task = asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """
        Attempt to reconnect to Godot WebSocket server with exponential backoff.
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"[GodotWebSocketClient] Max reconnection attempts ({self.max_reconnect_attempts}) reached")
            self._set_connection_state(ConnectionState.ERROR)
            self.status_manager.set_error("Max reconnection attempts reached")
            return

        self.reconnect_attempts += 1
        self._set_connection_state(ConnectionState.RECONNECTING)

        logger.info(f"[GodotWebSocketClient] Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}")

        # Wait before reconnection attempt with exponential backoff
        wait_time = min(self.reconnect_interval * (2 ** (self.reconnect_attempts - 1)), 60)
        await asyncio.sleep(wait_time)

        # Try to reconnect
        if await self.connect():
            logger.info(f"[GodotWebSocketClient] Successfully reconnected after {self.reconnect_attempts} attempts")
        else:
            # Schedule next reconnection attempt
            if self.enable_auto_reconnect:
                self.reconnect_task = asyncio.create_task(self._reconnect())

    def _set_connection_state(self, state: ConnectionState) -> None:
        """
        Update connection state.

        Args:
            state: New connection state
        """
        old_state = self.connection_state
        self.connection_state = state

        if old_state != state:
            logger.info(f"[GodotWebSocketClient] Connection state changed: {old_state.value} -> {state.value}")

    def _update_status_manager(self) -> None:
        """
        Update status manager with current connection state.
        """
        connection_details = {
            "websocket_connected": self.connection_state == ConnectionState.CONNECTED,
            "connection_state": self.connection_state.value,
            "server_url": self.ws_url,
            "last_connected_time": self.last_connected_time.isoformat() if self.last_connected_time else None,
            "message_count": self.message_count,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
            "reconnect_attempts": self.reconnect_attempts
        }

        self.status_manager.update_status({
            "connection_details": connection_details,
            "state": self.connection_state.value
        })

    def _is_connected(self) -> bool:
        """
        Check if WebSocket is connected.

        Returns:
            True if connected, False otherwise
        """
        return (
            self.connection_state == ConnectionState.CONNECTED and
            self.websocket is not None and
            not (hasattr(self.websocket, 'closed') and self.websocket.closed)
        )

    def get_connection_state(self) -> ConnectionState:
        """
        Get current connection state.

        Returns:
            Current connection state
        """
        return self.connection_state

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get detailed connection information.

        Returns:
            Dictionary with connection details
        """
        return {
            "state": self.connection_state.value,
            "server_url": self.ws_url,
            "connected": self._is_connected(),
            "last_connected_time": self.last_connected_time.isoformat() if self.last_connected_time else None,
            "message_count": self.message_count,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
            "reconnect_attempts": self.reconnect_attempts,
            "auto_reconnect_enabled": self.enable_auto_reconnect
        }

    async def cleanup(self) -> None:
        """
        Cleanup resources and disconnect.
        """
        await self.disconnect()
        logger.info("[GodotWebSocketClient] Cleanup completed")