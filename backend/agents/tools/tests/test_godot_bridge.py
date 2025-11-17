"""
Tests for Godot Bridge module.

This module tests the WebSocket connection management, command handling,
and project path functionality of the Godot bridge.
"""

import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, sentinel
from websockets.exceptions import ConnectionClosed, ConnectionRefusedError

from agents.tools.godot_bridge import (
    GodotBridge,
    GodotProjectInfo,
    CommandResponse,
    ConnectionState,
    get_godot_bridge,
    ensure_godot_connection,
    validate_project_path,
    to_godot_path,
    to_absolute_path
)


class TestGodotBridge:
    """Test cases for GodotBridge class."""

    @pytest.mark.asyncio
    async def test_bridge_initialization_default_config(self):
        """Test bridge initialization with default configuration."""
        with patch('agents.tools.godot_bridge.AgentConfig') as mock_config:
            mock_config.get_godot_config.return_value = {
                "host": "localhost",
                "port": 9001,
                "timeout": 10.0,
                "max_retries": 3,
                "retry_delay": 2.0,
                "command_timeout": 30.0
            }

            bridge = GodotBridge()

            assert bridge.host == "localhost"
            assert bridge.port == 9001
            assert bridge.timeout == 10.0
            assert bridge.max_retries == 3
            assert bridge.retry_delay == 2.0
            assert bridge.command_timeout == 30.0
            assert bridge.connection_state == ConnectionState.DISCONNECTED
            assert bridge.websocket is None
            assert bridge.project_info is None

    @pytest.mark.asyncio
    async def test_bridge_initialization_custom_config(self, mock_godot_config):
        """Test bridge initialization with custom configuration."""
        bridge = GodotBridge(mock_godot_config)

        assert bridge.host == mock_godot_config["host"]
        assert bridge.port == mock_godot_config["port"]
        assert bridge.timeout == mock_godot_config["timeout"]
        assert bridge.max_retries == mock_godot_config["max_retries"]
        assert bridge.retry_delay == mock_godot_config["retry_delay"]
        assert bridge.command_timeout == mock_godot_config["command_timeout"]

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_connect_success(self, mock_godot_config, mock_websocket):
        """Test successful WebSocket connection."""
        with patch('websockets.connect') as mock_connect:
            mock_connect.return_value = mock_websocket

            bridge = GodotBridge(mock_godot_config)
            result = await bridge.connect()

            assert result is True
            assert bridge.connection_state == ConnectionState.CONNECTED
            assert bridge.websocket is mock_websocket
            mock_connect.assert_called_once_with("ws://localhost:9001")

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_connect_failure_then_retry(self, mock_godot_config):
        """Test connection failure with retry mechanism."""
        with patch('websockets.connect') as mock_connect:
            # Fail first two attempts, succeed on third
            mock_connect.side_effect = [
                ConnectionRefusedError("Connection refused"),
                ConnectionRefusedError("Connection refused"),
                AsyncMock()  # Success on third attempt
            ]

            bridge = GodotBridge(mock_godot_config)
            # Set small retry delay for faster test
            bridge.retry_delay = 0.01

            result = await bridge.connect()

            assert result is True
            assert mock_connect.call_count == 3

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_connect_all_attempts_fail(self, mock_godot_config):
        """Test connection failure when all attempts fail."""
        with patch('websockets.connect') as mock_connect:
            mock_connect.side_effect = ConnectionRefusedError("Connection refused")

            bridge = GodotBridge(mock_godot_config)
            bridge.retry_delay = 0.01  # Fast retry for test

            result = await bridge.connect()

            assert result is False
            assert bridge.connection_state == ConnectionState.ERROR
            assert mock_connect.call_count == bridge.max_retries

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_is_connected_true(self, mock_godot_bridge):
        """Test is_connected returns True when connected."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.CONNECTED
        bridge.websocket = MagicMock()
        bridge.websocket.ping = AsyncMock()

        result = await bridge.is_connected()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_connected_false_no_websocket(self, mock_godot_bridge):
        """Test is_connected returns False when no websocket."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.CONNECTED
        bridge.websocket = None

        result = await bridge.is_connected()
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_is_connected_false_ping_fails(self, mock_godot_bridge):
        """Test is_connected returns False when ping fails."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.CONNECTED
        bridge.websocket = MagicMock()
        bridge.websocket.ping = AsyncMock(side_effect=Exception("Ping failed"))

        result = await bridge.is_connected()
        assert result is False
        assert bridge.connection_state == ConnectionState.ERROR

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_godot_bridge):
        """Test successful disconnection."""
        bridge = mock_godot_bridge
        bridge.websocket = MagicMock()
        bridge.websocket.close = AsyncMock()
        bridge.connection_state = ConnectionState.CONNECTED
        bridge.project_info = GodotProjectInfo(project_path="/test/path")

        await bridge.disconnect()

        assert bridge.connection_state == ConnectionState.DISCONNECTED
        assert bridge.websocket is None
        assert bridge.project_info is None
        bridge.websocket.close.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_send_command_success(self, mock_godot_bridge, mock_project_info):
        """Test successful command sending."""
        bridge = mock_godot_bridge
        bridge.websocket = MagicMock()
        bridge.websocket.send = AsyncMock()
        bridge.connection_state = ConnectionState.CONNECTED

        # Mock the future for response
        command_id = "cmd_1"
        future = asyncio.Future()
        future.set_result(CommandResponse(
            success=True,
            data=mock_project_info,
            command_id=command_id
        ))
        bridge._pending_commands[command_id] = future

        with patch.object(bridge, '_command_id_counter', 0):
            result = await bridge.send_command("test_command", param1="value")

        assert result.success is True
        assert result.data == mock_project_info
        assert result.command_id == command_id
        bridge.websocket.send.assert_called_once()

        # Verify the sent message structure
        sent_message = json.loads(bridge.websocket.send.call_args[0][0])
        assert sent_message["type"] == "test_command"
        assert sent_message["param1"] == "value"
        assert sent_message["id"] == command_id

    @pytest.mark.asyncio
    async def test_send_command_not_connected_autoconnects(self, mock_godot_bridge):
        """Test command sending auto-connects when not connected."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.DISCONNECTED
        bridge.connect = AsyncMock(return_value=True)

        with pytest.raises(Exception):  # Will fail because no websocket set up
            await bridge.send_command("test_command")

        bridge.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_command_connection_fails(self, mock_godot_bridge):
        """Test command sending when connection fails."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.DISCONNECTED
        bridge.connect = AsyncMock(return_value=False)

        result = await bridge.send_command("test_command")

        assert result.success is False
        assert "Failed to connect" in result.error

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_send_command_timeout(self, mock_godot_bridge):
        """Test command sending timeout."""
        bridge = mock_godot_bridge
        bridge.websocket = MagicMock()
        bridge.websocket.send = AsyncMock()
        bridge.connection_state = ConnectionState.CONNECTED
        bridge.command_timeout = 0.01  # Very short timeout for test

        # Create a future that doesn't get resolved
        future = asyncio.Future()
        bridge._pending_commands["cmd_1"] = future

        with patch.object(bridge, '_command_id_counter', 0):
            result = await bridge.send_command("test_command")

        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_send_command_exception(self, mock_godot_bridge):
        """Test command sending with exception."""
        bridge = mock_godot_bridge
        bridge.websocket = MagicMock()
        bridge.websocket.send = AsyncMock(side_effect=Exception("Send failed"))
        bridge.connection_state = ConnectionState.CONNECTED

        result = await bridge.send_command("test_command")

        assert result.success is False
        assert "Failed to send command" in result.error

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_get_project_info_cached(self, mock_godot_bridge, mock_project_info):
        """Test getting project info when already cached."""
        bridge = mock_godot_bridge
        bridge.project_info = GodotProjectInfo(**mock_project_info, is_ready=True)

        result = await bridge.get_project_info()

        assert result.project_path == mock_project_info["project_path"]
        assert result.project_name == mock_project_info["project_name"]

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_get_project_info_request(self, mock_godot_bridge, mock_project_info):
        """Test getting project info by requesting from Godot."""
        bridge = mock_godot_bridge
        bridge.project_info = None
        bridge.send_command = AsyncMock(return_value=CommandResponse(
            success=True,
            data=mock_project_info
        ))

        result = await bridge.get_project_info()

        assert result.project_path == mock_project_info["project_path"]
        bridge.send_command.assert_called_once_with("get_project_info")

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_get_project_info_failure(self, mock_godot_bridge):
        """Test getting project info when request fails."""
        bridge = mock_godot_bridge
        bridge.project_info = None
        bridge.send_command = AsyncMock(return_value=CommandResponse(
            success=False,
            error="Failed to get project info"
        ))

        result = await bridge.get_project_info()

        assert result is None

    def test_get_project_path_available(self, mock_godot_bridge, mock_project_path):
        """Test getting project path when available."""
        bridge = mock_godot_bridge
        bridge.project_info = GodotProjectInfo(project_path=mock_project_path)

        result = bridge.get_project_path()

        assert result == mock_project_path

    def test_get_project_path_unavailable(self, mock_godot_bridge):
        """Test getting project path when unavailable."""
        bridge = mock_godot_bridge
        bridge.project_info = None

        result = bridge.get_project_path()

        assert result is None

    def test_is_project_ready_true(self, mock_godot_bridge, mock_project_path):
        """Test project readiness when ready."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.CONNECTED
        bridge.project_info = GodotProjectInfo(project_path=mock_project_path, is_ready=True)

        result = bridge.is_project_ready()

        assert result is True

    def test_is_project_ready_false_not_connected(self, mock_godot_bridge):
        """Test project readiness when not connected."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.DISCONNECTED

        result = bridge.is_project_ready()

        assert result is False

    def test_is_project_ready_false_no_project_info(self, mock_godot_bridge):
        """Test project readiness when no project info."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.CONNECTED
        bridge.project_info = None

        result = bridge.is_project_ready()

        assert result is False

    def test_is_project_ready_false_not_ready(self, mock_godot_bridge):
        """Test project readiness when project not ready."""
        bridge = mock_godot_bridge
        bridge.connection_state = ConnectionState.CONNECTED
        bridge.project_info = GodotProjectInfo(project_path="/test", is_ready=False)

        result = bridge.is_project_ready()

        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_handle_project_info_message(self, mock_godot_bridge, mock_project_info):
        """Test handling project info message."""
        bridge = mock_godot_bridge
        bridge.security_context = MagicMock()
        bridge.security_context.set_project_path = MagicMock()

        message_data = {
            "type": "project_info",
            "data": mock_project_info
        }

        await bridge._handle_project_info(message_data)

        assert bridge.project_info.project_path == mock_project_info["project_path"]
        assert bridge.project_info.project_name == mock_project_info["project_name"]
        bridge.security_context.set_project_path.assert_called_once_with(mock_project_info["project_path"])

    @pytest.mark.asyncio
    @pytest.mark.websocket
    async def test_handle_command_response_success(self, mock_godot_bridge):
        """Test handling successful command response."""
        bridge = mock_godot_bridge
        command_id = "test_cmd_1"
        response_data = {"success": True, "data": {"result": "test"}}

        # Create and set up future
        future = asyncio.Future()
        bridge._pending_commands[command_id] = future

        message_data = {
            "type": "command_response",
            "id": command_id,
            "success": True,
            "data": {"result": "test"}
        }

        await bridge._handle_command_response(message_data)

        assert command_id not in bridge._pending_commands
        assert future.done()
        assert future.result().success is True
        assert future.result().data["result"] == "test"

    @pytest.mark.asyncio
    async def test_handle_command_response_unknown_command(self, mock_godot_bridge):
        """Test handling command response for unknown command."""
        bridge = mock_godot_bridge
        bridge._pending_commands = {}

        message_data = {
            "type": "command_response",
            "id": "unknown_cmd",
            "success": True,
            "data": {"result": "test"}
        }

        # Should not raise exception
        await bridge._handle_command_response(message_data)

    @pytest.mark.asyncio
    async def test_handle_error_message(self, mock_godot_bridge, caplog):
        """Test handling error message."""
        bridge = mock_godot_bridge

        message_data = {
            "type": "error",
            "message": "Test error message"
        }

        await bridge._handle_error(message_data)

        # Check that error was logged
        assert "Test error message" in caplog.text

    @pytest.mark.asyncio
    async def test_add_message_handler(self, mock_godot_bridge):
        """Test adding custom message handler."""
        bridge = mock_godot_bridge
        custom_handler = AsyncMock()

        bridge.add_message_handler("custom_type", custom_handler)

        assert bridge._message_handlers["custom_type"] is custom_handler

    @pytest.mark.asyncio
    async def test_add_connection_callback(self, mock_godot_bridge):
        """Test adding connection callback."""
        bridge = mock_godot_bridge
        callback = AsyncMock()

        bridge.add_connection_callback(callback)

        assert callback in bridge._connection_callbacks

    def test_remove_connection_callback(self, mock_godot_bridge):
        """Test removing connection callback."""
        bridge = mock_godot_bridge
        callback = AsyncMock()
        bridge._connection_callbacks = [callback]

        bridge.remove_connection_callback(callback)

        assert callback not in bridge._connection_callbacks


class TestGlobalBridgeFunctions:
    """Test cases for global bridge functions."""

    @pytest.mark.asyncio
    async def test_get_godot_bridge_singleton(self):
        """Test that get_godot_bridge returns singleton instance."""
        with patch('agents.tools.godot_bridge._godot_bridge', None):
            bridge1 = get_godot_bridge()
            bridge2 = get_godot_bridge()

            assert bridge1 is bridge2

    @pytest.mark.asyncio
    async def test_ensure_godot_connection_success(self):
        """Test ensure_godot_connection when connection succeeds."""
        mock_bridge = MagicMock()
        mock_bridge.is_connected = AsyncMock(return_value=True)

        with patch('agents.tools.godot_bridge.get_godot_bridge', return_value=mock_bridge):
            result = await ensure_godot_connection()

            assert result is True
            mock_bridge.is_connected.assert_called_once()
            mock_bridge.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_godot_connection_autoconnect(self):
        """Test ensure_godot_connection when auto-connection is needed."""
        mock_bridge = MagicMock()
        mock_bridge.is_connected = AsyncMock(return_value=False)
        mock_bridge.connect = AsyncMock(return_value=True)

        with patch('agents.tools.godot_bridge.get_godot_bridge', return_value=mock_bridge):
            result = await ensure_godot_connection()

            assert result is True
            mock_bridge.is_connected.assert_called_once()
            mock_bridge.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_godot_connection_failure(self):
        """Test ensure_godot_connection when connection fails."""
        mock_bridge = MagicMock()
        mock_bridge.is_connected = AsyncMock(return_value=False)
        mock_bridge.connect = AsyncMock(return_value=False)

        with patch('agents.tools.godot_bridge.get_godot_bridge', return_value=mock_bridge):
            result = await ensure_godot_connection()

            assert result is False


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_validate_project_path_valid(self, tmp_path):
        """Test validating a valid project path."""
        # Create a temporary directory with project.godot file
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        (project_dir / "project.godot").write_text("; Godot project file")

        result = validate_project_path(str(project_dir))

        assert result is True

    def test_validate_project_path_no_project_file(self, tmp_path):
        """Test validating path without project.godot file."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        result = validate_project_path(str(project_dir))

        assert result is False

    def test_validate_project_path_not_directory(self, tmp_path):
        """Test validating a file path instead of directory."""
        file_path = tmp_path / "not_a_directory.txt"
        file_path.write_text("test")

        result = validate_project_path(str(file_path))

        assert result is False

    def test_validate_project_path_does_not_exist(self):
        """Test validating a non-existent path."""
        result = validate_project_path("/non/existent/path")

        assert result is False

    def test_to_godot_path_valid(self, mock_project_path):
        """Test converting absolute path to Godot path."""
        import os
        file_path = os.path.join(mock_project_path, "scenes", "level1.tscn")

        result = to_godot_path(file_path, mock_project_path)

        assert result == "res://scenes/level1.tscn"

    def test_to_godot_path_outside_project(self, mock_project_path):
        """Test converting path outside project."""
        outside_path = "/some/other/path/file.txt"

        result = to_godot_path(outside_path, mock_project_path)

        assert result == outside_path  # Should return original path

    def test_to_godot_path_already_godot_format(self):
        """Test converting path already in Godot format."""
        godot_path = "res://scenes/level1.tscn"

        result = to_godot_path(godot_path, "/any/project/path")

        assert result == godot_path

    def test_to_absolute_path_valid(self, mock_project_path):
        """Test converting Godot path to absolute path."""
        import os
        godot_path = "res://scenes/level1.tscn"
        expected = os.path.join(mock_project_path, "scenes", "level1.tscn")

        result = to_absolute_path(godot_path, mock_project_path)

        assert result == expected

    def test_to_absolute_path_not_godot_format(self):
        """Test converting path not in Godot format."""
        regular_path = "/some/absolute/path/file.txt"

        result = to_absolute_path(regular_path, "/any/project/path")

        assert result == regular_path


class TestGodotProjectInfo:
    """Test cases for GodotProjectInfo dataclass."""

    def test_project_info_creation(self, mock_project_info):
        """Test creating GodotProjectInfo."""
        info = GodotProjectInfo(**mock_project_info)

        assert info.project_path == mock_project_info["project_path"]
        assert info.project_name == mock_project_info["project_name"]
        assert info.godot_version == mock_project_info["godot_version"]
        assert info.plugin_version == mock_project_info["plugin_version"]
        assert info.is_ready == mock_project_info["is_ready"]

    def test_project_info_defaults(self):
        """Test GodotProjectInfo with default values."""
        info = GodotProjectInfo(project_path="/test/path")

        assert info.project_path == "/test/path"
        assert info.project_name == ""
        assert info.godot_version == ""
        assert info.plugin_version == ""
        assert info.is_ready is False


class TestCommandResponse:
    """Test cases for CommandResponse dataclass."""

    def test_command_response_success(self):
        """Test creating successful CommandResponse."""
        response = CommandResponse(
            success=True,
            data={"result": "test"},
            command_id="cmd_1"
        )

        assert response.success is True
        assert response.data["result"] == "test"
        assert response.command_id == "cmd_1"
        assert response.error is None

    def test_command_response_error(self):
        """Test creating error CommandResponse."""
        response = CommandResponse(
            success=False,
            error="Something went wrong",
            command_id="cmd_2"
        )

        assert response.success is False
        assert response.error == "Something went wrong"
        assert response.command_id == "cmd_2"
        assert response.data is None

    def test_command_response_defaults(self):
        """Test CommandResponse with default values."""
        response = CommandResponse(success=True)

        assert response.success is True
        assert response.data is None
        assert response.error is None
        assert response.command_id is None


class TestConnectionState:
    """Test cases for ConnectionState enum."""

    def test_connection_state_values(self):
        """Test ConnectionState enum values."""
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.ERROR.value == "error"

    def test_connection_state_comparison(self):
        """Test ConnectionState comparison."""
        assert ConnectionState.CONNECTED == ConnectionState.CONNECTED
        assert ConnectionState.CONNECTED != ConnectionState.DISCONNECTED