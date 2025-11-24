import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.agents.tools import godot_executor_tools
from backend.agents.tools.godot_executor_tools import (
    create_node,
    delete_node,
    modify_node_property,
    create_scene,
    reparent_node,
    select_nodes,
    get_godot_executor_tools
)

@pytest.mark.asyncio
class TestGodotToolsIntegration:
    
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        # Reset the singleton instance before and after each test
        godot_executor_tools._godot_executor_tools_instance = None
        yield
        godot_executor_tools._godot_executor_tools_instance = None

    @pytest.fixture
    def mock_bridge(self):
        # Create a mock bridge
        bridge = AsyncMock()
        # Default response to success
        bridge.send_command.return_value = MagicMock(success=True, data={}, error=None)
        bridge.ensure_connection = AsyncMock(return_value=True)
        bridge.is_connected = AsyncMock(return_value=True)
        bridge.connect = AsyncMock(return_value=True)
        # is_path_safe is synchronous
        bridge.is_path_safe = MagicMock(return_value=True)
        return bridge

    @patch('backend.agents.tools.godot_executor_tools.get_godot_bridge')
    async def test_create_node_integration(self, mock_get_bridge, mock_bridge):
        """Test that create_node tool sends correct command to Godot bridge."""
        mock_get_bridge.return_value = mock_bridge
        
        # Execute tool
        result = await create_node(
            node_type="Sprite2D",
            parent_path="Root/Player",
            node_name="Weapon",
            properties={"position": {"x": 10, "y": 0}}
        )
        
        # Verify bridge call
        mock_bridge.send_command.assert_called_once_with(
            "create_node",
            type="Sprite2D",
            parent="Root/Player",
            name="Weapon",
            properties={"position": {"x": 10, "y": 0}}
        )
        
        assert result["status"] == "success"

    @patch('backend.agents.tools.godot_executor_tools.get_godot_bridge')
    async def test_delete_node_integration(self, mock_get_bridge, mock_bridge):
        """Test that delete_node tool sends correct command to Godot bridge."""
        mock_get_bridge.return_value = mock_bridge
        
        await delete_node(node_path="Root/Enemy")
        
        mock_bridge.send_command.assert_called_once_with(
            "delete_node",
            path="Root/Enemy"
        )

    @patch('backend.agents.tools.godot_executor_tools.get_godot_bridge')
    async def test_modify_node_property_integration(self, mock_get_bridge, mock_bridge):
        """Test that modify_node_property sends correct command."""
        mock_get_bridge.return_value = mock_bridge
        
        await modify_node_property(
            node_path="Root/Player",
            property_name="health",
            new_value=100
        )
        
        mock_bridge.send_command.assert_called_once_with(
            "modify_node",
            path="Root/Player",
            properties={"health": 100}
        )

    @patch('backend.agents.tools.godot_executor_tools.get_godot_bridge')
    async def test_create_scene_integration(self, mock_get_bridge, mock_bridge):
        """Test that create_scene sends correct command."""
        mock_get_bridge.return_value = mock_bridge
        
        await create_scene(
            scene_name="Level1",
            root_node_type="Node2D",
            save_path="res://scenes/level1.tscn"
        )
        
        # Verify correct mapping of parameters
        mock_bridge.send_command.assert_called_once_with(
            "create_scene",
            name="Level1",
            root_type="Node2D",
            save_path="res://scenes/level1.tscn"
        )

    @patch('backend.agents.tools.godot_executor_tools.get_godot_bridge')
    async def test_reparent_node_integration(self, mock_get_bridge, mock_bridge):
        """Test that reparent_node sends correct command."""
        mock_get_bridge.return_value = mock_bridge
        
        await reparent_node(
            node_path="Root/Item",
            new_parent_path="Root/Inventory",
            new_position=0
        )
        
        mock_bridge.send_command.assert_called_once_with(
            "reparent_node",
            path="Root/Item",
            new_parent_path="Root/Inventory",
            index=0
        )

    @patch('backend.agents.tools.godot_executor_tools.get_godot_bridge')
    async def test_select_nodes_integration(self, mock_get_bridge, mock_bridge):
        """Test that select_nodes sends correct command."""
        mock_get_bridge.return_value = mock_bridge
        
        await select_nodes(node_paths=["Root/A", "Root/B"])
        
        mock_bridge.send_command.assert_called_once_with(
            "select_nodes",
            paths=["Root/A", "Root/B"]
        )

    @patch('backend.agents.tools.godot_executor_tools.get_godot_bridge')
    async def test_validation_failures(self, mock_get_bridge, mock_bridge):
        """Test that tools validate input before calling bridge."""
        mock_get_bridge.return_value = mock_bridge
        
        # Test create_node missing required params
        result = await create_node(node_type=None, parent_path=None)
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        mock_bridge.send_command.assert_not_called()
        
        # Test delete_node missing path
        result = await delete_node(node_path=None)
        assert result["status"] == "error"
        mock_bridge.send_command.assert_not_called()
