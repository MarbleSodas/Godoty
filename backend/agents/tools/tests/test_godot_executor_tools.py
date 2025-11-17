"""
Tests for Godot Executor Tools module.

This module tests the executor agent action tools for node manipulation,
scene management, and Godot automation capabilities.
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agents.tools.godot_executor_tools import (
    GodotExecutorTools,
    create_node,
    modify_node_property,
    create_scene,
    open_scene,
    select_nodes,
    play_scene,
    stop_playing,
    CreationResult,
    ModificationResult
)


class TestGodotExecutorTools:
    """Test cases for GodotExecutorTools class."""

    @pytest.mark.asyncio
    async def test_executor_tools_initialization(self, mock_godot_bridge):
        """Test GodotExecutorTools initialization."""
        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            tools = GodotExecutorTools()

            assert tools.bridge is mock_godot_bridge
            assert tools._operation_history == []

    @pytest.mark.asyncio
    async def test_ensure_connection_success(self, mock_godot_bridge):
        """Test ensure_connection when connection succeeds."""
        mock_godot_bridge.is_connected = AsyncMock(return_value=True)
        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.ensure_connection()

        assert result is True
        mock_godot_bridge.is_connected.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_connection_autoconnect(self, mock_godot_bridge):
        """Test ensure_connection when auto-connection is needed."""
        mock_godot_bridge.is_connected = AsyncMock(return_value=False)
        mock_godot_bridge.connect = AsyncMock(return_value=True)
        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.ensure_connection()

        assert result is True
        mock_godot_bridge.is_connected.assert_called_once()
        mock_godot_bridge.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_connection_failure(self, mock_godot_bridge):
        """Test ensure_connection when connection fails."""
        mock_godot_bridge.is_connected = AsyncMock(return_value=False)
        mock_godot_bridge.connect = AsyncMock(return_value=False)
        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        with pytest.raises(ConnectionError):
            await tools.ensure_connection()

    @pytest.mark.asyncio
    async def test_create_node_success(self, mock_godot_bridge):
        """Test successful node creation."""
        mock_response_data = {"path": "Root/NewNode", "id": "12345"}
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_response_data
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.create_node("Node2D", "Root", "NewNode", {"position": {"x": 100, "y": 100}})

        assert isinstance(result, CreationResult)
        assert result.success is True
        assert result.created_path == "Root/NewNode"
        assert result.created_id == "12345"
        assert result.error is None

        # Verify command was called correctly
        mock_godot_bridge.send_command.assert_called_once_with(
            "create_node",
            node_type="Node2D",
            parent_path="Root",
            node_name="NewNode",
            properties={"position": {"x": 100, "y": 100}}
        )

        # Verify operation was recorded
        assert len(tools._operation_history) == 1
        operation = tools._operation_history[0]
        assert operation["type"] == "create_node"
        assert operation["target"] == "Root/NewNode"
        assert operation["result"] is True

    @pytest.mark.asyncio
    async def test_create_node_minimal_params(self, mock_godot_bridge):
        """Test node creation with minimal parameters."""
        mock_response_data = {"path": "Root/Node"}
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_response_data
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.create_node("Node", "Root")

        assert result.success is True
        assert result.created_path == "Root/Node"

        mock_godot_bridge.send_command.assert_called_once_with(
            "create_node",
            node_type="Node",
            parent_path="Root"
        )

    @pytest.mark.asyncio
    async def test_create_node_failure(self, mock_godot_bridge):
        """Test node creation when command fails."""
        error_message = "Failed to create node"
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error=error_message
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.create_node("Node2D", "Root", "TestNode")

        assert isinstance(result, CreationResult)
        assert result.success is False
        assert result.error == error_message
        assert result.created_path is None

        # Verify failure was recorded
        assert len(tools._operation_history) == 1
        operation = tools._operation_history[0]
        assert operation["result"] is False
        assert "error" in operation["details"]

    @pytest.mark.asyncio
    async def test_create_node_connection_error(self):
        """Test node creation with connection error."""
        tools = GodotExecutorTools()
        tools.bridge = MagicMock()
        tools.bridge.is_connected = AsyncMock(return_value=False)
        tools.bridge.connect = AsyncMock(return_value=False)

        result = await tools.create_node("Node2D", "Root")

        assert isinstance(result, CreationResult)
        assert result.success is False
        assert "Failed to connect" in result.error

    @pytest.mark.asyncio
    async def test_create_node_exception(self, mock_godot_bridge):
        """Test node creation with exception."""
        mock_godot_bridge.send_command = AsyncMock(side_effect=Exception("Unexpected error"))
        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.create_node("Node2D", "Root")

        assert isinstance(result, CreationResult)
        assert result.success is False
        assert "Unexpected error" in result.error

    @pytest.mark.asyncio
    async def test_delete_node_success(self, mock_godot_bridge):
        """Test successful node deletion."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.delete_node("Root/TestNode")

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with(
            "delete_node",
            node_path="Root/TestNode"
        )

        # Verify operation was recorded
        assert len(tools._operation_history) == 1
        operation = tools._operation_history[0]
        assert operation["type"] == "delete_node"
        assert operation["target"] == "Root/TestNode"
        assert operation["result"] is True

    @pytest.mark.asyncio
    async def test_delete_node_failure(self, mock_godot_bridge):
        """Test node deletion when command fails."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Node not found"
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.delete_node("Root/NonExistent")

        assert result is False

        # Verify failure was recorded
        operation = tools._operation_history[0]
        assert operation["result"] is False

    @pytest.mark.asyncio
    async def test_modify_node_property_success(self, mock_godot_bridge):
        """Test successful property modification."""
        mock_response_data = {"old_value": {"x": 0, "y": 0}}
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_response_data
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.modify_node_property(
            "Root/Player",
            "position",
            {"x": 100, "y": 50}
        )

        assert isinstance(result, ModificationResult)
        assert result.success is True
        assert result.modified_path == "Root/Player"
        assert result.old_value == {"x": 0, "y": 0}
        assert result.new_value == {"x": 100, "y": 50}
        assert result.error is None

        mock_godot_bridge.send_command.assert_called_once_with(
            "modify_node_property",
            node_path="Root/Player",
            property_name="position",
            new_value={"x": 100, "y": 50}
        )

        # Verify operation was recorded
        assert len(tools._operation_history) == 1
        operation = tools._operation_history[0]
        assert operation["type"] == "modify_property"
        assert operation["details"]["property"] == "position"
        assert operation["details"]["old_value"] == {"x": 0, "y": 0}
        assert operation["details"]["new_value"] == {"x": 100, "y": 50}

    @pytest.mark.asyncio
    async def test_modify_node_property_failure(self, mock_godot_bridge):
        """Test property modification when command fails."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Property not found"
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.modify_node_property("Root/Node", "invalid_prop", "value")

        assert isinstance(result, ModificationResult)
        assert result.success is False
        assert result.error == "Property not found"
        assert result.modified_path is None

    @pytest.mark.asyncio
    async def test_reparent_node_success(self, mock_godot_bridge):
        """Test successful node reparenting."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.reparent_node("Root/Child", "Root/NewParent", 0)

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with(
            "reparent_node",
            node_path="Root/Child",
            new_parent_path="Root/NewParent",
            position=0
        )

        # Verify operation was recorded
        assert len(tools._operation_history) == 1
        operation = tools._operation_history[0]
        assert operation["type"] == "reparent_node"
        assert operation["result"] is True

    @pytest.mark.asyncio
    async def test_reparent_node_no_position(self, mock_godot_bridge):
        """Test node reparenting without position."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.reparent_node("Root/Child", "Root/NewParent")

        assert result is True

        # Position should not be included in call
        call_args = mock_godot_bridge.send_command.call_args[1]
        assert "position" not in call_args

    @pytest.mark.asyncio
    async def test_create_new_scene_success(self, mock_godot_bridge):
        """Test successful scene creation."""
        mock_response_data = {"scene_path": "res://scenes/NewScene.tscn"}
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_response_data
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.create_new_scene(
            "NewScene",
            "Node2D",
            "res://scenes/NewScene.tscn"
        )

        assert isinstance(result, CreationResult)
        assert result.success is True
        assert result.created_path == "res://scenes/NewScene.tscn"

        mock_godot_bridge.send_command.assert_called_once_with(
            "create_scene",
            scene_name="NewScene",
            root_node_type="Node2D",
            save_path="res://scenes/NewScene.tscn"
        )

    @pytest.mark.asyncio
    async def test_create_new_scene_minimal_params(self, mock_godot_bridge):
        """Test scene creation with minimal parameters."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data={"scene_path": "res://scenes/Test.tscn"}
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.create_new_scene("Test")

        assert result.success is True

        mock_godot_bridge.send_command.assert_called_once_with(
            "create_scene",
            scene_name="Test",
            root_node_type="Node"
        )

    @pytest.mark.asyncio
    async def test_open_scene_success(self, mock_godot_bridge):
        """Test successful scene opening."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.open_scene("res://scenes/main.tscn")

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with(
            "open_scene",
            scene_path="res://scenes/main.tscn"
        )

        # Verify operation was recorded
        assert len(tools._operation_history) == 1
        operation = tools._operation_history[0]
        assert operation["type"] == "open_scene"
        assert operation["target"] == "res://scenes/main.tscn"

    @pytest.mark.asyncio
    async def test_save_current_scene_success(self, mock_godot_bridge):
        """Test successful current scene saving."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.save_current_scene()

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with("save_current_scene")

    @pytest.mark.asyncio
    async def test_select_nodes_success(self, mock_godot_bridge):
        """Test successful node selection."""
        node_paths = ["Root/Node1", "Root/Node2", "Root/Node3"]
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.select_nodes(node_paths)

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with(
            "select_nodes",
            node_paths=node_paths
        )

    @pytest.mark.asyncio
    async def test_select_nodes_empty_list(self, mock_godot_bridge):
        """Test selecting empty node list."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.select_nodes([])

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with(node_paths=[])

    @pytest.mark.asyncio
    async def test_focus_node_success(self, mock_godot_bridge):
        """Test successful node focusing."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.focus_node("Root/ImportantNode")

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with(
            "focus_node",
            node_path="Root/ImportantNode"
        )

    @pytest.mark.asyncio
    async def test_play_scene_success(self, mock_godot_bridge):
        """Test successful scene playback start."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.play_scene()

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with("play_scene")

        # Verify operation was recorded
        assert len(tools._operation_history) == 1
        operation = tools._operation_history[0]
        assert operation["type"] == "play_scene"
        assert operation["target"] == "current"

    @pytest.mark.asyncio
    async def test_stop_playing_success(self, mock_godot_bridge):
        """Test successful scene playback stop."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.stop_playing()

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with("stop_playing")

    @pytest.mark.asyncio
    async def test_create_node_batch_success(self, mock_godot_bridge):
        """Test successful batch node creation."""
        # Mock multiple successful responses
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            MagicMock(success=True, data={"path": "Root/Node1"}),
            MagicMock(success=True, data={"path": "Root/Node2"}),
            MagicMock(success=True, data={"path": "Root/Node3"})
        ])

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        creations = [
            {"node_type": "Node2D", "parent_path": "Root", "node_name": "Node1"},
            {"node_type": "Sprite2D", "parent_path": "Root", "node_name": "Node2"},
            {"node_type": "Camera2D", "parent_path": "Root", "node_name": "Node3"}
        ]

        with patch('asyncio.sleep', new_callable=AsyncMock):  # Speed up test
            results = await tools.create_node_batch(creations)

        assert len(results) == 3
        assert all(result.success for result in results)
        assert results[0].created_path == "Root/Node1"
        assert results[1].created_path == "Root/Node2"
        assert results[2].created_path == "Root/Node3"

        # Verify all operations were recorded
        assert len(tools._operation_history) == 3

    @pytest.mark.asyncio
    async def test_create_node_batch_partial_failure(self, mock_godot_bridge):
        """Test batch node creation with some failures."""
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            MagicMock(success=True, data={"path": "Root/Node1"}),
            MagicMock(success=False, error="Creation failed"),
            MagicMock(success=True, data={"path": "Root/Node3"})
        ])

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        creations = [
            {"node_type": "Node2D", "parent_path": "Root", "node_name": "Node1"},
            {"node_type": "Sprite2D", "parent_path": "Root", "node_name": "Node2"},
            {"node_type": "Camera2D", "parent_path": "Root", "node_name": "Node3"}
        ]

        with patch('asyncio.sleep', new_callable=AsyncMock):
            results = await tools.create_node_batch(creations)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    @pytest.mark.asyncio
    async def test_modify_properties_batch_success(self, mock_godot_bridge):
        """Test successful batch property modification."""
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            MagicMock(success=True, data={"old_value": False, "new_value": True}),
            MagicMock(success=True, data={"old_value": 0, "new_value": 100}),
            MagicMock(success=True, data={"old_value": "Red", "new_value": "Blue"})
        ])

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        modifications = [
            {"node_path": "Root/Node1", "property_name": "visible", "new_value": True},
            {"node_path": "Root/Node2", "property_name": "health", "new_value": 100},
            {"node_path": "Root/Node3", "property_name": "color", "new_value": "Blue"}
        ]

        with patch('asyncio.sleep', new_callable=AsyncMock):
            results = await tools.modify_properties_batch(modifications)

        assert len(results) == 3
        assert all(result.success for result in results)
        assert results[0].old_value is False
        assert results[0].new_value is True
        assert results[1].old_value == 0
        assert results[1].new_value == 100

    @pytest.mark.asyncio
    async def test_get_operation_history(self, mock_godot_bridge):
        """Test getting operation history."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        # Perform some operations
        await tools.create_node("Node2D", "Root", "Test1")
        await tools.modify_node_property("Root/Test1", "visible", True)
        await tools.delete_node("Root/Test1")

        history = await tools.get_operation_history()

        assert len(history) == 3
        assert history[0]["type"] == "create_node"
        assert history[1]["type"] == "modify_property"
        assert history[2]["type"] == "delete_node"
        assert all(op["result"] for op in history)

    @pytest.mark.asyncio
    async def test_clear_operation_history(self, mock_godot_bridge):
        """Test clearing operation history."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        # Add some operations
        await tools.create_node("Node2D", "Root", "Test")
        assert len(tools._operation_history) == 1

        # Clear history
        await tools.clear_operation_history()
        assert len(tools._operation_history) == 0

    @pytest.mark.asyncio
    async def test_undo_last_operation_success(self, mock_godot_bridge):
        """Test successful undo operation."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.undo_last_operation()

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with("undo")

    @pytest.mark.asyncio
    async def test_undo_last_operation_failure(self, mock_godot_bridge):
        """Test undo operation failure."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Nothing to undo"
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.undo_last_operation()

        assert result is False

    @pytest.mark.asyncio
    async def test_redo_last_operation_success(self, mock_godot_bridge):
        """Test successful redo operation."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.redo_last_operation()

        assert result is True

        mock_godot_bridge.send_command.assert_called_once_with("redo")

    @pytest.mark.asyncio
    async def test_redo_last_operation_failure(self, mock_godot_bridge):
        """Test redo operation failure."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Nothing to redo"
        ))

        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        result = await tools.redo_last_operation()

        assert result is False

    def test_record_operation(self, mock_godot_bridge):
        """Test operation recording."""
        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        # Test recording a successful operation
        tools._record_operation("test_op", "/test/path", True, {"param": "value"})

        assert len(tools._operation_history) == 1
        operation = tools._operation_history[0]
        assert operation["type"] == "test_op"
        assert operation["target"] == "/test/path"
        assert operation["result"] is True
        assert operation["details"]["param"] == "value"
        assert "timestamp" in operation

        # Test recording a failed operation
        tools._record_operation("test_op", "/test/path", False, {"error": "test error"})

        assert len(tools._operation_history) == 2
        operation = tools._operation_history[1]
        assert operation["result"] is False
        assert operation["details"]["error"] == "test error"

    def test_operation_history_limit(self, mock_godot_bridge):
        """Test operation history size limit."""
        tools = GodotExecutorTools()
        tools.bridge = mock_godot_bridge

        # Add more operations than the limit
        for i in range(150):
            tools._record_operation(f"op_{i}", f"/path_{i}", True)

        # Should be limited to last 50 operations (after cleanup)
        assert len(tools._operation_history) == 50
        assert tools._operation_history[-1]["type"] == "op_149"


class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    @pytest.mark.asyncio
    async def test_create_node_function(self, mock_godot_bridge):
        """Test create_node convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data={"path": "Root/NewNode"}
        ))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await create_node("Node2D", "Root", "NewNode")

            assert isinstance(result, CreationResult)
            assert result.success is True
            assert result.created_path == "Root/NewNode"

    @pytest.mark.asyncio
    async def test_modify_node_property_function(self, mock_godot_bridge):
        """Test modify_node_property convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data={"old_value": False, "new_value": True}
        ))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await modify_node_property("Root/Node", "visible", True)

            assert isinstance(result, ModificationResult)
            assert result.success is True
            assert result.old_value is False
            assert result.new_value is True

    @pytest.mark.asyncio
    async def test_create_scene_function(self, mock_godot_bridge):
        """Test create_scene convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data={"scene_path": "res://scenes/NewScene.tscn"}
        ))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await create_scene("NewScene")

            assert isinstance(result, CreationResult)
            assert result.success is True
            assert result.created_path == "res://scenes/NewScene.tscn"

    @pytest.mark.asyncio
    async def test_open_scene_function(self, mock_godot_bridge):
        """Test open_scene convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await open_scene("res://scenes/main.tscn")

            assert result is True

    @pytest.mark.asyncio
    async def test_select_nodes_function(self, mock_godot_bridge):
        """Test select_nodes convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await select_nodes(["Root/Node1", "Root/Node2"])

            assert result is True

    @pytest.mark.asyncio
    async def test_play_scene_function(self, mock_godot_bridge):
        """Test play_scene convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await play_scene()

            assert result is True

    @pytest.mark.asyncio
    async def test_stop_playing_function(self, mock_godot_bridge):
        """Test stop_playing convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await stop_playing()

            assert result is True


class TestDataClasses:
    """Test cases for data classes."""

    def test_creation_result_success(self):
        """Test CreationResult for successful operation."""
        result = CreationResult(
            success=True,
            created_path="Root/NewNode",
            created_id="12345"
        )

        assert result.success is True
        assert result.created_path == "Root/NewNode"
        assert result.created_id == "12345"
        assert result.error is None

    def test_creation_result_failure(self):
        """Test CreationResult for failed operation."""
        result = CreationResult(
            success=False,
            error="Failed to create node"
        )

        assert result.success is False
        assert result.error == "Failed to create node"
        assert result.created_path is None
        assert result.created_id is None

    def test_modification_result_success(self):
        """Test ModificationResult for successful operation."""
        result = ModificationResult(
            success=True,
            modified_path="Root/Node",
            old_value=False,
            new_value=True
        )

        assert result.success is True
        assert result.modified_path == "Root/Node"
        assert result.old_value is False
        assert result.new_value is True
        assert result.error is None

    def test_modification_result_failure(self):
        """Test ModificationResult for failed operation."""
        result = ModificationResult(
            success=False,
            error="Property not found"
        )

        assert result.success is False
        assert result.error == "Property not found"
        assert result.modified_path is None
        assert result.old_value is None
        assert result.new_value is None

    def test_creation_result_defaults(self):
        """Test CreationResult with default values."""
        result = CreationResult(success=True)

        assert result.success is True
        assert result.created_path is None
        assert result.created_id is None
        assert result.error is None

    def test_modification_result_defaults(self):
        """Test ModificationResult with default values."""
        result = ModificationResult(success=True)

        assert result.success is True
        assert result.modified_path is None
        assert result.old_value is None
        assert result.new_value is None
        assert result.error is None