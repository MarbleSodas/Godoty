
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agents.tools.godot_executor_tools import GodotExecutorTools, CreationResult, ModificationResult

@pytest.fixture
def mock_bridge():
    with patch('agents.tools.godot_executor_tools.get_godot_bridge') as mock_get_bridge:
        bridge = AsyncMock()
        mock_get_bridge.return_value = bridge
        yield bridge

@pytest.fixture
def tools(mock_bridge):
    return GodotExecutorTools()

@pytest.mark.asyncio
async def test_create_node(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"path": "/root/Node", "id": "123"})
    
    result = await tools.create_node("Node", "/root", "MyNode", {"prop": "val"})
    
    assert result.success
    assert result.created_path == "/root/Node"
    mock_bridge.send_command.assert_called_with(
        "create_node",
        node_type="Node",
        parent_path="/root",
        node_name="MyNode",
        properties={"prop": "val"}
    )

@pytest.mark.asyncio
async def test_delete_node(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.delete_node("/root/Node")
    
    assert result
    mock_bridge.send_command.assert_called_with("delete_node", node_path="/root/Node")

@pytest.mark.asyncio
async def test_modify_node_property(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"old_value": "old"})
    
    result = await tools.modify_node_property("/root/Node", "prop", "new")
    
    assert result.success
    assert result.old_value == "old"
    mock_bridge.send_command.assert_called_with(
        "modify_node_property",
        node_path="/root/Node",
        property_name="prop",
        new_value="new"
    )

@pytest.mark.asyncio
async def test_reparent_node(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.reparent_node("/root/Node", "/root/NewParent", 0)
    
    assert result
    mock_bridge.send_command.assert_called_with(
        "reparent_node",
        node_path="/root/Node",
        new_parent_path="/root/NewParent",
        position=0
    )

@pytest.mark.asyncio
async def test_create_new_scene(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"scene_path": "res://scene.tscn"})
    
    result = await tools.create_new_scene("MyScene", "Node2D", "res://scene.tscn")
    
    assert result.success
    assert result.created_path == "res://scene.tscn"
    mock_bridge.send_command.assert_called_with(
        "create_scene",
        scene_name="MyScene",
        root_node_type="Node2D",
        save_path="res://scene.tscn"
    )

@pytest.mark.asyncio
async def test_open_scene(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.open_scene("res://scene.tscn")
    
    assert result
    mock_bridge.send_command.assert_called_with("open_scene", scene_path="res://scene.tscn")

@pytest.mark.asyncio
async def test_save_current_scene(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.save_current_scene()
    
    assert result
    mock_bridge.send_command.assert_called_with("save_current_scene")

@pytest.mark.asyncio
async def test_select_nodes(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.select_nodes(["/root/Node1", "/root/Node2"])
    
    assert result
    mock_bridge.send_command.assert_called_with("select_nodes", node_paths=["/root/Node1", "/root/Node2"])

@pytest.mark.asyncio
async def test_focus_node(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.focus_node("/root/Node")
    
    assert result
    mock_bridge.send_command.assert_called_with("focus_node", node_path="/root/Node")

@pytest.mark.asyncio
async def test_play_scene(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.play_scene()
    
    assert result
    # This asserts the fix I made: sending "play" instead of "play_scene"
    mock_bridge.send_command.assert_called_with("play", mode="current")

@pytest.mark.asyncio
async def test_stop_playing(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.stop_playing()
    
    assert result
    mock_bridge.send_command.assert_called_with("stop_playing")

@pytest.mark.asyncio
async def test_duplicate_node(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"path": "/root/Node2", "id": "124"})
    
    result = await tools.duplicate_node("/root/Node", "Node2")
    
    assert result.success
    assert result.created_path == "/root/Node2"
    mock_bridge.send_command.assert_called_with(
        "duplicate_node",
        node_path="/root/Node",
        new_name="Node2"
    )

@pytest.mark.asyncio
async def test_create_resource(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"path": "res://res.tres"})
    
    result = await tools.create_resource("Resource", "res://res.tres", {"prop": "val"})
    
    assert result.success
    assert result.created_path == "res://res.tres"
    mock_bridge.send_command.assert_called_with(
        "create_resource",
        resource_type="Resource",
        resource_path="res://res.tres",
        initial_data={"prop": "val"}
    )

@pytest.mark.asyncio
async def test_delete_resource(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.delete_resource("res://res.tres")
    
    assert result
    mock_bridge.send_command.assert_called_with("delete_resource", resource_path="res://res.tres")

@pytest.mark.asyncio
async def test_attach_script_to_node(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True)
    
    result = await tools.attach_script_to_node("/root/Node", "res://script.gd")
    
    assert result
    mock_bridge.send_command.assert_called_with(
        "attach_script_to_node",
        node_path="/root/Node",
        script_path="res://script.gd"
    )

@pytest.mark.asyncio
async def test_create_and_attach_script(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"script_path": "res://script.gd"})
    
    result = await tools.create_and_attach_script("/root/Node", "extends Node", "script")
    
    assert result.success
    assert result.created_path == "res://script.gd"
    mock_bridge.send_command.assert_called_with(
        "create_and_attach_script",
        node_path="/root/Node",
        script_content="extends Node",
        script_name="script"
    )

@pytest.mark.asyncio
async def test_create_node_with_script(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"node_path": "/root/Node", "script_path": "res://script.gd"})
    
    result = await tools.create_node_with_script("Node", "/root", "extends Node", "MyNode", {"prop": "val"})
    
    assert result.success
    mock_bridge.send_command.assert_called_with(
        "create_node_with_script",
        node_type="Node",
        parent_path="/root",
        script_content="extends Node",
        node_name="MyNode",
        properties={"prop": "val"}
    )

@pytest.mark.asyncio
async def test_create_node_batch(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"path": "/root/Node", "id": "123"})
    
    creations = [
        {"node_type": "Node", "parent_path": "/root", "node_name": "Node1"},
        {"node_type": "Node", "parent_path": "/root", "node_name": "Node2"}
    ]
    
    results = await tools.create_node_batch(creations)
    
    assert len(results) == 2
    assert results[0].success
    assert results[1].success
    assert mock_bridge.send_command.call_count == 2

@pytest.mark.asyncio
async def test_modify_properties_batch(tools, mock_bridge):
    mock_bridge.send_command.return_value = MagicMock(success=True, data={"old_value": "old"})
    
    modifications = [
        {"node_path": "/root/Node1", "property_name": "prop1", "new_value": "val1"},
        {"node_path": "/root/Node2", "property_name": "prop2", "new_value": "val2"}
    ]
    
    results = await tools.modify_properties_batch(modifications)
    
    assert len(results) == 2
    assert results[0].success
    assert results[1].success
    assert mock_bridge.send_command.call_count == 2
