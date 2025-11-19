"""
Pytest configuration and fixtures for Godot tools testing.

This module provides common fixtures, mocks, and test configuration
for all Godot tools tests.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionRefusedError

# Set up test logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture
def mock_project_path():
    """Fixture providing a mock project path."""
    return "/Users/testuser/projects/test_game"


@pytest.fixture
def mock_godot_config():
    """Fixture providing mock Godot configuration."""
    return {
        "host": "localhost",
        "port": 9001,
        "timeout": 5.0,
        "max_retries": 2,
        "retry_delay": 0.5,
        "command_timeout": 10.0,
        "screenshot_dir": ".godoty/screenshots"
    }


@pytest.fixture
def mock_project_info():
    """Fixture providing mock project information."""
    return {
        "project_path": "/Users/testuser/projects/test_game",
        "project_name": "TestGame",
        "godot_version": "4.3.0",
        "plugin_version": "1.0.0",
        "is_ready": True
    }


@pytest.fixture
def mock_scene_tree():
    """Fixture providing mock scene tree data."""
    return {
        "name": "Root",
        "type": "Node2D",
        "path": "Root",
        "properties": {
            "position": {"x": 0, "y": 0},
            "scale": {"x": 1, "y": 1},
            "rotation": 0
        },
        "children": [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "path": "Root/Player",
                "properties": {
                    "position": {"x": 100, "y": 100}
                },
                "children": [
                    {
                        "name": "Sprite2D",
                        "type": "Sprite2D",
                        "path": "Root/Player/Sprite2D",
                        "properties": {},
                        "children": []
                    }
                ]
            },
            {
                "name": "Camera2D",
                "type": "Camera2D",
                "path": "Root/Camera2D",
                "properties": {
                    "position": {"x": 0, "y": 0}
                },
                "children": []
            }
        ]
    }


@pytest.fixture
def mock_node_info():
    """Fixture providing mock node information."""
    return {
        "name": "Player",
        "type": "CharacterBody2D",
        "path": "Root/Player",
        "parent": "Root",
        "children": ["Root/Player/Sprite2D", "Root/Player/CollisionShape2D"],
        "properties": {
            "position": {"x": 100, "y": 100},
            "scale": {"x": 1, "y": 1},
            "collision_layer": 1,
            "collision_mask": 1
        },
        "groups": ["player", "character"],
        "has_script": True,
        "script_path": "res://scripts/player.gd"
    }


@pytest.fixture
def mock_visual_snapshot():
    """Fixture providing mock visual snapshot data."""
    return {
        "screenshot_path": "/Users/testuser/projects/test_game/.godoty/screenshots/screenshot_123456.png",
        "viewport_size": (1920, 1080),
        "camera_info": {
            "position": {"x": 0, "y": 0},
            "zoom": {"x": 1, "y": 1},
            "rotation": 0
        },
        "selected_nodes": ["Root/Player"],
        "scene_tree_state": {
            "current_scene": "res://scenes/main.tscn",
            "modified": False
        }
    }


@pytest.fixture
def mock_search_results():
    """Fixture providing mock search results."""
    return [
        {
            "name": "Player",
            "type": "CharacterBody2D",
            "path": "Root/Player",
            "parent": "Root",
            "children": [],
            "properties": {},
            "groups": ["player"],
            "has_script": True,
            "script_path": "res://scripts/player.gd"
        },
        {
            "name": "PlayerSprite",
            "type": "Sprite2D",
            "path": "Root/PlayerSprite",
            "parent": "Root",
            "children": [],
            "properties": {"texture": "res://assets/player.png"},
            "groups": [],
            "has_script": False,
            "script_path": None
        }
    ]


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.messages = []
        self.closed = False
        self.response_data = {}
        self.should_fail_connection = False
        self.should_fail_send = False

    async def send(self, message: str):
        """Mock sending a message."""
        if self.should_fail_send:
            raise ConnectionClosed(None, None)

        if self.closed:
            raise ConnectionClosed(None, None)

        data = json.loads(message)
        self.messages.append(data)

        # Simulate response
        command_id = data.get("id")
        if command_id and command_id in self.response_data:
            await self._simulate_response(command_id)

    async def recv(self):
        """Mock receiving a message."""
        if self.closed:
            raise ConnectionClosed(None, None)

        # Return project info on first connection
        if len(self.messages) == 1:
            return json.dumps({
                "type": "project_info",
                "data": {
                    "project_path": "/Users/testuser/projects/test_game",
                    "project_name": "TestGame",
                    "is_ready": True
                }
            })

        return await asyncio.sleep(1)  # Wait for real messages

    async def close(self):
        """Mock closing the connection."""
        self.closed = True

    async def ping(self):
        """Mock ping."""
        if self.closed:
            raise ConnectionClosed(None, None)

    def set_response(self, command_id: str, response_data: Dict[str, Any]):
        """Set response data for a specific command."""
        self.response_data[command_id] = response_data

    async def _simulate_response(self, command_id: str):
        """Simulate receiving a response."""
        # This would normally be handled by the message listener
        pass


@pytest.fixture
def mock_websocket():
    """Fixture providing a mock WebSocket."""
    return MockWebSocket()


@pytest.fixture
async def mock_godot_bridge(mock_websocket, mock_godot_config, mock_project_info):
    """Fixture providing a mock Godot bridge with WebSocket."""
    with patch('websockets.connect') as mock_connect:
        mock_connect.return_value = mock_websocket

        # Import after patching
        from agents.tools.godot_bridge import GodotBridge

        bridge = GodotBridge(mock_godot_config)

        # Set up mock responses
        mock_websocket.set_response("cmd_1", {
            "success": True,
            "data": mock_project_info
        })

        yield bridge




@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def anyio_backend():
    """Backend for anyio pytest plugin."""
    return "asyncio"


class AsyncContextManager:
    """Helper for async context managers in tests."""

    def __init__(self, async_func):
        self.async_func = async_func
        self.result = None

    async def __aenter__(self):
        self.result = await self.async_func()
        return self.result

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Cleanup if needed
        pass


def async_cm(async_func):
    """Decorator to create async context managers."""
    return AsyncContextManager(async_func)


# Helper functions for tests
def create_mock_command_response(success: bool = True, data: Any = None, error: str = None):
    """Create a mock command response."""
    response = {"success": success}
    if data is not None:
        response["data"] = data
    if error is not None:
        response["error"] = error
    return response


def create_mock_creation_result(success: bool = True, path: str = None, error: str = None):
    """Create a mock creation result."""
    from agents.tools.godot_executor_tools import CreationResult
    return CreationResult(
        success=success,
        created_path=path,
        error=error
    )


def create_mock_modification_result(success: bool = True, path: str = None,
                                  old_value: Any = None, new_value: Any = None,
                                  error: str = None):
    """Create a mock modification result."""
    from agents.tools.godot_executor_tools import ModificationResult
    return ModificationResult(
        success=success,
        modified_path=path,
        old_value=old_value,
        new_value=new_value,
        error=error
    )


# Test configuration
TEST_CONFIG = {
    "test_timeout": 30.0,
    "mock_delay": 0.1,
    "max_retries": 3,
    "test_project_path": "/tmp/test_godot_project"
}


# Pytest hooks
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: Mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: Mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "websocket: Mark test as requiring WebSocket"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    for item in items:
        # Add slow marker to integration tests
        if "integration" in item.keywords:
            item.add_marker(pytest.mark.slow)

        # Add websocket marker to tests that use websockets
        if "websocket" in item.nodeid or "mock_websocket" in item.fixturenames:
            item.add_marker(pytest.mark.websocket)