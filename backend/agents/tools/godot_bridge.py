"""
Godot Bridge - WebSocket connection manager for Godot Editor integration.

This module provides a robust WebSocket client for connecting to the Godot Editor
plugin, enabling AI agents to interact with Godot projects through a stable
connection with proper project path handling and error recovery.
"""

import asyncio
import json
import logging
import pathlib
from typing import Any, Dict, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from strands import tool
from ..config import AgentConfig

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class GodotProjectInfo:
    """Information about the connected Godot project."""
    project_path: str
    project_name: str = ""
    godot_version: str = ""
    plugin_version: str = ""
    project_settings: Dict[str, Any] = field(default_factory=dict)
    is_ready: bool = True


@dataclass
class CommandResponse:
    """Response from Godot command execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    command_id: Optional[str] = None


class GodotBridge:
    """
    WebSocket bridge for connecting to Godot Editor plugin.

    Provides robust connection management, project path detection,
    and command execution with proper error handling and recovery.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Godot bridge connection.

        Args:
            config: Optional configuration dictionary. If not provided, uses AgentConfig.
        """
        if config:
            self.host = config.get("host", "localhost")
            self.port = config.get("port", 9001)
            self.timeout = config.get("timeout", 10.0)
            self.max_retries = config.get("max_retries", 3)
            self.retry_delay = config.get("retry_delay", 2.0)
            self.command_timeout = config.get("command_timeout", 30.0)
        else:
            godot_config = AgentConfig.get_godot_config()
            self.host = godot_config["host"]
            self.port = godot_config["port"]
            self.timeout = godot_config["timeout"]
            self.max_retries = godot_config["max_retries"]
            self.retry_delay = godot_config["retry_delay"]
            self.command_timeout = godot_config["command_timeout"]

        # Connection state
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connection_state = ConnectionState.DISCONNECTED
        self.project_info: Optional[GodotProjectInfo] = None


        # Command management
        self._command_id_counter = 0
        self._pending_commands: Dict[str, asyncio.Future] = {}

        # Message listener task tracking
        self._message_listener_task: Optional[asyncio.Task] = None

        # Event handling
        self._message_handlers: Dict[str, callable] = {}
        self._connection_callbacks: list[callable] = []

        # Register default message handlers
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default message handlers for common Godot messages."""
        self._message_handlers.update({
            "project_info": self._handle_project_info,
            "command_response": self._handle_command_response,
            "error": self._handle_error,
            "status": self._handle_status,
        })

    async def connect(self) -> bool:
        """
        Establish WebSocket connection to Godot plugin.

        Returns:
            True if connection successful, False otherwise
        """
        if self.connection_state == ConnectionState.CONNECTED:
            logger.warning("Already connected to Godot plugin")
            return True

        uri = f"ws://{self.host}:{self.port}"
        logger.info(f"Connecting to Godot plugin at {uri}")

        self.connection_state = ConnectionState.CONNECTING

        for attempt in range(self.max_retries):
            try:
                self.websocket = await asyncio.wait_for(
                    websockets.connect(uri),
                    timeout=self.timeout
                )

                self.connection_state = ConnectionState.CONNECTED
                logger.info(f"✓ Successfully connected to Godot plugin at {uri} (attempt {attempt + 1})")

                # Start message listener task and track it
                logger.info("🎧 Starting WebSocket message listener")
                self._message_listener_task = asyncio.create_task(self._message_listener())
                self._message_listener_task.add_done_callback(self._on_listener_done)

                # Notify connection callbacks
                for callback in self._connection_callbacks:
                    try:
                        await callback(True)
                    except Exception as e:
                        logger.error(f"Error in connection callback: {e}")

                return True

            except (OSError, asyncio.TimeoutError) as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                continue
            except Exception as e:
                logger.error(f"Unexpected error during connection: {e}")
                break

        self.connection_state = ConnectionState.ERROR
        logger.error("Failed to connect to Godot plugin after all attempts")
        return False

    async def disconnect(self):
        """Close WebSocket connection and cleanup resources."""
        # Cancel message listener task
        if self._message_listener_task and not self._message_listener_task.done():
            logger.info("🛑 Cancelling message listener task")
            self._message_listener_task.cancel()
            try:
                await self._message_listener_task
            except asyncio.CancelledError:
                pass
            self._message_listener_task = None

        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket connection: {e}")
            finally:
                self.websocket = None

        self.connection_state = ConnectionState.DISCONNECTED
        self.project_info = None

        # Cancel pending commands
        for command_id, future in self._pending_commands.items():
            if not future.done():
                future.set_exception(ConnectionError("Connection closed"))

        self._pending_commands.clear()
        logger.info("🔌 Disconnected from Godot plugin")

    async def is_connected(self) -> bool:
        """Check if WebSocket connection is active and healthy."""
        if not self.websocket or self.connection_state != ConnectionState.CONNECTED:
            return False

        try:
            # Send a ping to check connection health
            await self.websocket.ping()
            return True
        except Exception:
            self.connection_state = ConnectionState.ERROR
            return False

    async def send_command(self, command_type: str, **kwargs) -> CommandResponse:
        """
        Send a command to Godot and wait for response.

        Args:
            command_type: Type of command to execute
            **kwargs: Command-specific parameters

        Returns:
            CommandResponse with execution result
        """
        if not await self.is_connected():
            logger.info(f"🔌 Not connected, attempting to connect to Godot for command: {command_type}")
            if not await self.connect():
                logger.error(f"❌ Failed to establish connection to Godot for command: {command_type}")
                raise ConnectionError("Failed to connect to Godot plugin")

        # Verify WebSocket is actually open (not just state check)
        if not self.websocket or self.websocket.state.name != "OPEN":
            logger.warning(f"⚠️ WebSocket is not open despite connected state, reconnecting...")
            self.connection_state = ConnectionState.DISCONNECTED
            if not await self.connect():
                logger.error(f"❌ Failed to reconnect WebSocket for command: {command_type}")
                raise ConnectionError("WebSocket not open and reconnection failed")

        # Generate unique command ID
        self._command_id_counter += 1
        command_id = f"cmd_{self._command_id_counter}"

        # Prepare command message
        command = {
            "id": command_id,
            "action": command_type,
            "timestamp": asyncio.get_event_loop().time(),
            **kwargs
        }

        # Create future for response
        response_future = asyncio.Future()
        self._pending_commands[command_id] = response_future

        try:
            # Send command
            message = json.dumps(command)
            # logger.info(f"📤 Sending command {command_id}: {command_type} with params: {list(kwargs.keys())}")
            logger.info(f"📤 SENDING RAW WEBSOCKET MESSAGE: {message}")
            await self.websocket.send(message)
            logger.info(f"✓ Sent command {command_id}: {command_type} to Godot, waiting for response...")

            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=self.command_timeout)
            logger.info(f"✓ Received response for command {command_id}")
            return response

        except asyncio.TimeoutError:
            logger.warning(f"⏱ Command {command_id} ({command_type}) timed out after {self.command_timeout}s - Godot may not be responding")
            self._pending_commands.pop(command_id, None)
            return CommandResponse(
                success=False,
                error=f"Command {command_id} timed out after {self.command_timeout} seconds"
            )
        except Exception as e:
            logger.error(f"❌ Error sending command {command_id} ({command_type}): {e}")
            self._pending_commands.pop(command_id, None)
            return CommandResponse(
                success=False,
                error=f"Failed to send command: {str(e)}"
            )

    async def get_project_info(self) -> Optional[GodotProjectInfo]:
        """
        Get current project information from Godot.

        Returns:
            GodotProjectInfo if available, None otherwise
        """
        if self.project_info and self.project_info.is_ready:
            return self.project_info

        # Request project info
        response = await self.send_command("get_project_info")

        if response.success and response.data:
            self.project_info = GodotProjectInfo(**response.data)
            return self.project_info

        return None

    def get_project_path(self) -> Optional[str]:
        """
        Get the current project path.

        Returns:
            Project path as absolute path if available, None otherwise
        """
        return self.project_info.project_path if self.project_info else None

    def is_project_ready(self) -> bool:
        """Check if project is ready for operations."""
        return (
            self.connection_state == ConnectionState.CONNECTED and
            self.project_info is not None and
            self.project_info.is_ready
        )

    def is_path_safe(self, path: Union[str, pathlib.Path]) -> bool:
        """
        Check if a path is safe (within the project directory).

        Args:
            path: Path to check

        Returns:
            True if path is safe, False otherwise
        """
        if not self.project_info or not self.project_info.project_path:
            # If no project info, we can't validate against it.
            # Fallback: Check against cwd if project info is missing.
            try:
                cwd = pathlib.Path.cwd().resolve()
                target = pathlib.Path(path).resolve()
                return target.is_relative_to(cwd)
            except Exception:
                return False

        try:
            project_root = pathlib.Path(self.project_info.project_path).resolve()
            target = pathlib.Path(path).resolve()
            return target.is_relative_to(project_root)
        except Exception:
            return False

    async def _message_listener(self):
        """Background task to listen for WebSocket messages."""
        logger.info("🎧 Message listener started and listening...")
        try:
            async for message in self.websocket:
                try:
                    # logger.debug(f"📥 RAW WEBSOCKET MESSAGE: {message}")
                    logger.info(f"📥 RECEIVED RAW WEBSOCKET MESSAGE: {message[:1000]}...") # Truncate to avoid spamming too much if it's an image
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")

        except ConnectionClosed:
            logger.warning("⚠️ WebSocket connection closed, message listener stopping")
            self.connection_state = ConnectionState.DISCONNECTED
        except Exception as e:
            logger.error(f"❌ Error in message listener: {e}")
            self.connection_state = ConnectionState.ERROR

    def _on_listener_done(self, task: asyncio.Task):
        """Callback when message listener task completes."""
        try:
            task.result()  # Raise any exception that occurred
            logger.info("🛑 Message listener task completed normally")
        except asyncio.CancelledError:
            logger.info("🛑 Message listener task was cancelled")
        except Exception as e:
            logger.error(f"❌ Message listener task failed with error: {e}")

    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket message."""
        message_type = data.get("type")

        if not message_type:
            logger.warning("⚠️ Received message without type field")
            return

        logger.info(f"📨 Received message type: {message_type}")
        handler = self._message_handlers.get(message_type)
        if handler:
            try:
                await handler(data)
            except Exception as e:
                logger.error(f"❌ Error in message handler for {message_type}: {e}")
        else:
            logger.warning(f"⚠️ No handler for message type: {message_type}")

    async def _handle_project_info(self, data: Dict[str, Any]):
        """Handle project_info message from Godot."""
        project_data = data.get("data", {})
        self.project_info = GodotProjectInfo(**project_data)

        logger.info(
            f"Received project info - Path: {self.project_info.project_path}, "
            f"Version: {self.project_info.godot_version}, "
            f"Ready: {self.project_info.is_ready}"
        )

    async def _handle_command_response(self, data: Dict[str, Any]):
        """Handle command response message."""
        command_id = data.get("id")
        if not command_id or command_id not in self._pending_commands:
            logger.warning(f"⚠️ Received response for unknown command: {command_id}")
            return

        future = self._pending_commands.pop(command_id)

        if not future.done():
            # Determine success from 'success' bool or 'status' string
            is_success = data.get("success", False)
            if "success" not in data and "status" in data:
                is_success = (data["status"] == "success")

            response = CommandResponse(
                success=is_success,
                data=data.get("data"),
                error=data.get("error") or (data.get("message") if not is_success else None),
                command_id=command_id
            )
            if response.success:
                logger.info(f"✓ Received successful response for command {command_id}")
            else:
                logger.warning(f"⚠️ Received error response for command {command_id}: {response.error}")
            future.set_result(response)

    async def _handle_error(self, data: Dict[str, Any]):
        """Handle error message from Godot."""
        error_message = data.get("message", "Unknown error")
        logger.error(f"Godot plugin error: {error_message}")

    async def _handle_status(self, data: Dict[str, Any]):
        """Handle status message from Godot."""
        status_data = data.get("data", {})
        logger.debug(f"Godot plugin status: {status_data}")

    def add_message_handler(self, message_type: str, handler: callable):
        """Add custom message handler for specific message type."""
        self._message_handlers[message_type] = handler

    def add_connection_callback(self, callback: callable):
        """Add callback to be called when connection state changes."""
        self._connection_callbacks.append(callback)

    def remove_connection_callback(self, callback: callable):
        """Remove connection callback."""
        if callback in self._connection_callbacks:
            self._connection_callbacks.remove(callback)


# Global bridge instance for use across tools
_godot_bridge: Optional[GodotBridge] = None


def get_godot_bridge() -> GodotBridge:
    """Get or create global Godot bridge instance."""
    global _godot_bridge
    if _godot_bridge is None:
        _godot_bridge = GodotBridge()
    return _godot_bridge


@tool
async def ensure_godot_connection() -> bool:
    """Ensure Godot bridge is connected and ready for communication.

    Returns:
        bool: True if connection is established or already connected, False otherwise
    """
    bridge = get_godot_bridge()
    if not await bridge.is_connected():
        return await bridge.connect()
    return True


def validate_project_path(project_path: str) -> bool:
    """
    Validate that a project path is safe and within bounds.

    Args:
        project_path: Path to validate

    Returns:
        True if path is valid and safe, False otherwise
    """
    if not project_path:
        return False

    try:
        path = pathlib.Path(project_path)

        # Check if path exists and is a directory
        if not path.exists() or not path.is_dir():
            return False

        # Check for project.godot file
        project_file = path / "project.godot"
        if not project_file.exists():
            return False

        # Additional safety checks can be added here
        return True

    except Exception:
        return False


def to_godot_path(absolute_path: str, project_path: str) -> str:
    """
    Convert absolute path to Godot's res:// path format.

    Args:
        absolute_path: Absolute file system path
        project_path: Godot project root path

    Returns:
        Godot-style path (res://path/to/file)
    """
    try:
        project_dir = pathlib.Path(project_path)
        file_path = pathlib.Path(absolute_path)

        # Calculate relative path from project root
        relative_path = file_path.relative_to(project_dir)

        # Convert to Godot format
        return f"res://{relative_path.as_posix()}"

    except Exception:
        # Fallback to original path if conversion fails
        return absolute_path


def to_absolute_path(godot_path: str, project_path: str) -> str:
    """
    Convert Godot res:// path to absolute file system path.

    Args:
        godot_path: Godot-style path (res://path/to/file)
        project_path: Godot project root path

    Returns:
        Absolute file system path
    """
    if not godot_path.startswith("res://"):
        return godot_path

    try:
        # Remove res:// prefix
        relative_path = godot_path[5:]  # Remove "res://"
        project_dir = pathlib.Path(project_path)

        # Combine with project path
        return str(project_dir / relative_path)

    except Exception:
        # Fallback to original path if conversion fails
        return godot_path