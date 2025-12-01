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
import random
import time
from typing import Any, Dict, Optional, Tuple, Union
from dataclasses import dataclass, field, fields
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from strands import tool
from ..config import AgentConfig
from utils.serialization import safe_json_dumps

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectionErrorType(Enum):
    """Types of connection errors for better error handling."""
    NETWORK_ERROR = "network_error"          # Network connectivity issues
    TIMEOUT_ERROR = "timeout_error"          # Connection timeouts
    REFUSED_ERROR = "refused_error"          # Connection refused (Godot not running)
    WEBSOCKET_ERROR = "websocket_error"      # WebSocket protocol errors
    AUTH_ERROR = "auth_error"                # Authentication/handshake errors
    UNKNOWN_ERROR = "unknown_error"          # Uncategorized errors


@dataclass
class ConnectionErrorInfo:
    """Detailed information about a connection error."""
    error_type: ConnectionErrorType
    message: str
    original_exception: Optional[Exception] = None
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0
    is_recoverable: bool = True


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
        self.last_connection_error: Optional[ConnectionErrorInfo] = None
        self.connection_attempts = 0
        self.successful_connections = 0


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

    def _classify_connection_error(self, exception: Exception) -> ConnectionErrorInfo:
        """
        Classify connection error for better handling and retry logic.

        Args:
            exception: The exception that occurred

        Returns:
            ConnectionErrorInfo with classified error details
        """
        error_message = str(exception)

        # Check for connection refused in error message (cross-platform)
        if "Connection refused" in error_message or "errno 61" in error_message:
            return ConnectionErrorInfo(
                error_type=ConnectionErrorType.REFUSED_ERROR,
                message=f"Godot plugin not running or not accepting connections: {error_message}",
                original_exception=exception,
                is_recoverable=True
            )
        elif isinstance(exception, asyncio.TimeoutError):
            return ConnectionErrorInfo(
                error_type=ConnectionErrorType.TIMEOUT_ERROR,
                message=f"Connection timeout - Godot may be busy: {error_message}",
                original_exception=exception,
                is_recoverable=True
            )
        elif isinstance(exception, OSError):
            if "Connection refused" in error_message or "errno 61" in error_message:
                return ConnectionErrorInfo(
                    error_type=ConnectionErrorType.REFUSED_ERROR,
                    message=f"Godot plugin not running: {error_message}",
                    original_exception=exception,
                    is_recoverable=True
                )
            elif "Network is unreachable" in error_message or "No route to host" in error_message:
                return ConnectionErrorInfo(
                    error_type=ConnectionErrorType.NETWORK_ERROR,
                    message=f"Network connectivity issue: {error_message}",
                    original_exception=exception,
                    is_recoverable=False
                )
            else:
                return ConnectionErrorInfo(
                    error_type=ConnectionErrorType.NETWORK_ERROR,
                    message=f"Network/OS error: {error_message}",
                    original_exception=exception,
                    is_recoverable=True
                )
        elif isinstance(exception, (ConnectionClosed, ConnectionClosedError)):
            return ConnectionErrorInfo(
                error_type=ConnectionErrorType.WEBSOCKET_ERROR,
                message=f"WebSocket connection lost: {error_message}",
                original_exception=exception,
                is_recoverable=True
            )
        else:
            return ConnectionErrorInfo(
                error_type=ConnectionErrorType.UNKNOWN_ERROR,
                message=f"Unexpected connection error: {error_message}",
                original_exception=exception,
                is_recoverable=True
            )

    def _calculate_backoff_delay(self, attempt: int, base_delay: float = 1.0, max_delay: float = 60.0, jitter: bool = True) -> float:
        """
        Calculate exponential backoff delay with optional jitter.

        Args:
            attempt: Current attempt number (0-based)
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            jitter: Whether to add jitter to prevent thundering herd

        Returns:
            Delay in seconds
        """
        delay = min(base_delay * (2 ** attempt), max_delay)

        if jitter:
            # Add ±25% jitter
            jitter_factor = 0.75 + (random.random() * 0.5)  # 0.75 to 1.25
            delay *= jitter_factor

        return delay

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
        Establish WebSocket connection to Godot plugin with enhanced error handling
        and intelligent retry logic.

        Returns:
            True if connection successful, False otherwise
        """
        if self.connection_state == ConnectionState.CONNECTED:
            logger.debug("Already connected to Godot plugin")
            return True

        uri = f"ws://{self.host}:{self.port}"
        logger.info(f"Connecting to Godot plugin at {uri}")

        self.connection_state = ConnectionState.CONNECTING
        self.connection_attempts += 1

        consecutive_failures = 0
        max_consecutive_failures = 3  # Give up after 3 consecutive failures with non-recoverable errors

        for attempt in range(self.max_retries):
            try:
                # Calculate delay with exponential backoff and jitter
                delay = self._calculate_backoff_delay(attempt, self.retry_delay, 60.0, jitter=True)

                if attempt > 0:
                    logger.info(f"Waiting {delay:.2f}s before retry attempt {attempt + 1}/{self.max_retries}")
                    await asyncio.sleep(delay)

                logger.info(f"Connection attempt {attempt + 1}/{self.max_retries} to {uri}")

                # Attempt connection with timeout
                self.websocket = await asyncio.wait_for(
                    websockets.connect(uri),
                    timeout=self.timeout
                )

                # Connection successful
                self.connection_state = ConnectionState.CONNECTED
                self.successful_connections += 1
                consecutive_failures = 0  # Reset consecutive failure count

                logger.info(
                    f"✅ Successfully connected to Godot plugin at {uri} "
                    f"(attempt {attempt + 1}, success rate: {self.successful_connections}/{self.connection_attempts})"
                )

                # Start message listener task and track it
                logger.info("🎧 Starting WebSocket message listener")
                self._message_listener_task = asyncio.create_task(self._message_listener())
                self._message_listener_task.add_done_callback(self._on_listener_done)

                # Clear any previous error
                self.last_connection_error = None

                # Notify connection callbacks
                for callback in self._connection_callbacks:
                    try:
                        await callback(True)
                    except Exception as e:
                        logger.error(f"Error in connection callback: {e}")

                return True

            except Exception as e:
                # Classify the error for better handling
                error_info = self._classify_connection_error(e)
                error_info.retry_count = attempt
                self.last_connection_error = error_info
                consecutive_failures += 1

                # Enhanced error logging
                logger.warning(
                    f"❌ Connection attempt {attempt + 1} failed ({error_info.error_type.value}): "
                    f"{error_info.message}"
                )

                # Check if we should give up due to consecutive non-recoverable errors
                if not error_info.is_recoverable:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(
                            f"🛑 Giving up after {max_consecutive_failures} consecutive "
                            f"non-recoverable errors: {error_info.error_type.value}"
                        )
                        break
                    else:
                        logger.info(f"Non-recoverable error, but will retry ({consecutive_failures}/{max_consecutive_failures})")
                        continue

                # For timeout errors, try with shorter timeout on next attempt
                if error_info.error_type == ConnectionErrorType.TIMEOUT_ERROR and attempt < self.max_retries - 1:
                    original_timeout = self.timeout
                    self.timeout = max(original_timeout * 0.8, 2.0)  # Don't go below 2 seconds
                    logger.info(f"Reducing timeout to {self.timeout}s for next attempt")
                    # Restore original timeout after this attempt
                    self.timeout = original_timeout

                # Continue to next attempt unless this was the last one
                if attempt < self.max_retries - 1:
                    continue

        # All attempts failed
        self.connection_state = ConnectionState.ERROR

        if self.last_connection_error:
            error_type_desc = "non-recoverable" if not self.last_connection_error.is_recoverable else "recoverable"
            logger.error(
                f"🔴 Failed to connect to Godot plugin after {self.max_retries} attempts. "
                f"Last error: {self.last_connection_error.error_type.value} ({error_type_desc}): "
                f"{self.last_connection_error.message}"
            )
        else:
            logger.error(f"🔴 Failed to connect to Godot plugin after {self.max_retries} attempts")

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
            message = safe_json_dumps(command)
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
        """Background task to listen for WebSocket messages with enhanced error handling."""
        logger.info("🎧 Message listener started and listening...")
        message_count = 0
        last_activity = time.time()

        try:
            async for message in self.websocket:
                try:
                    # Update activity tracking
                    message_count += 1
                    last_activity = time.time()

                    # Log message receipt with size information
                    message_size = len(message)
                    if message_size > 1024:  # Large messages
                        logger.info(f"📥 Received large message #{message_count} ({message_size} bytes): {message[:200]}...")
                    else:
                        logger.debug(f"📥 Received message #{message_count} ({message_size} bytes): {message}")

                    data = json.loads(message)
                    await self._handle_message(data)

                except json.JSONDecodeError as e:
                    logger.error(f"❌ Invalid JSON in message #{message_count}: {e}. Message preview: {message[:100]}...")
                    # Don't disconnect for malformed JSON, just log and continue
                except Exception as e:
                    logger.error(f"❌ Error handling message #{message_count}: {e}")
                    # Continue processing other messages

        except ConnectionClosed as e:
            logger.warning(f"⚠️ WebSocket connection closed ({e.code}): {e.reason}")
            self.connection_state = ConnectionState.DISCONNECTED

            # Log connection statistics
            logger.info(f"📊 Connection stats: {message_count} messages processed, "
                       f"duration: {time.time() - last_activity:.1f}s if available")

        except asyncio.CancelledError:
            logger.info("🛑 Message listener cancelled")
            self.connection_state = ConnectionState.DISCONNECTED

        except Exception as e:
            logger.error(f"❌ Unexpected error in message listener: {e}")
            self.connection_state = ConnectionState.ERROR

            # Store error information
            self.last_connection_error = ConnectionErrorInfo(
                error_type=ConnectionErrorType.WEBSOCKET_ERROR,
                message=f"Message listener error: {str(e)}",
                original_exception=e,
                is_recoverable=True
            )

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
        try:
            project_data = data.get("data", {})
            
            # Robustly handle data by filtering for known fields
            valid_keys = {f.name for f in fields(GodotProjectInfo)}
            filtered_data = {k: v for k, v in project_data.items() if k in valid_keys}
            
            self.project_info = GodotProjectInfo(**filtered_data)

            logger.info(
                f"Received project info - Path: {self.project_info.project_path}, "
                f"Version: {self.project_info.godot_version}, "
                f"Ready: {self.project_info.is_ready}"
            )
        except Exception as e:
            logger.error(f"Failed to process project info: {e}")

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

    def get_connection_stats(self) -> dict:
        """
        Get detailed connection statistics.

        Returns:
            Dictionary with connection statistics and error information
        """
        success_rate = 0.0
        if self.connection_attempts > 0:
            success_rate = self.successful_connections / self.connection_attempts

        stats = {
            "connection_attempts": self.connection_attempts,
            "successful_connections": self.successful_connections,
            "success_rate": success_rate,
            "current_state": self.connection_state.value,
            "last_error": None,
            "project_info": None
        }

        if self.last_connection_error:
            stats["last_error"] = {
                "type": self.last_connection_error.error_type.value,
                "message": self.last_connection_error.message,
                "timestamp": self.last_connection_error.timestamp,
                "retry_count": self.last_connection_error.retry_count,
                "is_recoverable": self.last_connection_error.is_recoverable
            }

        if self.project_info:
            stats["project_info"] = {
                "project_path": self.project_info.project_path,
                "project_name": self.project_info.project_name,
                "godot_version": self.project_info.godot_version,
                "plugin_version": self.project_info.plugin_version,
                "is_ready": self.project_info.is_ready
            }

        return stats


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