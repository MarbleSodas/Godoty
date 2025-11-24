import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import asyncio

from agents.tools.godot_bridge import GodotBridge, GodotProjectInfo
from agents.tools.godot_executor_tools import GodotExecutorTools
from agents.tools.file_tools import FileTools
from agents.tools.file_system_tools import read_file

@pytest.fixture
def mock_bridge():
    with patch('agents.tools.godot_bridge.get_godot_bridge') as mock_get:
        bridge = MagicMock(spec=GodotBridge)
        bridge.project_info = GodotProjectInfo(
            project_path="/tmp/mock_project",
            project_name="MockProject",
            godot_version="4.3"
        )
        
        # Mock is_path_safe to use the logic we added (simplified for test)
        def is_path_safe(path):
            try:
                project_root = Path("/tmp/mock_project").resolve()
                target = Path(path).resolve()
                return target.is_relative_to(project_root)
            except Exception:
                return False
        
        bridge.is_path_safe.side_effect = is_path_safe
        bridge.get_project_path.return_value = "/tmp/mock_project"
        bridge.is_connected.return_value = True
        
        mock_get.return_value = bridge
        yield bridge

@pytest.mark.asyncio
async def test_executor_create_scene_scoping(mock_bridge):
    tools = GodotExecutorTools()
    
    # Test unsafe path
    result = await tools.create_new_scene(
        scene_name="UnsafeScene",
        root_node_type="Node",
        save_path="/tmp/outside_project/unsafe.tscn"
    )
    
    assert result["status"] == "error"
    assert "outside the project directory" in result["content"][0]["text"]

@pytest.mark.asyncio
async def test_file_tools_write_scoping(mock_bridge):
    tools = FileTools()
    
    # Test unsafe path
    result = await tools.write_file_safe(
        file_path="/tmp/outside_project/unsafe.txt",
        content="unsafe content"
    )
    
    assert result.success is False
    assert "outside project root" in result.error

@pytest.mark.asyncio
async def test_file_system_read_scoping(mock_bridge):
    # Test unsafe path
    # We need to patch validate_path to allow the path to pass existence check if we want to test the bridge check,
    # or we can just rely on validate_path failing if the file doesn't exist.
    # But here we want to test the bridge check specifically.
    # So we'll use a path that exists but is outside.
    
    # Create a dummy file outside project
    outside_path = Path("/tmp/outside_project/test.txt")
    outside_path.parent.mkdir(parents=True, exist_ok=True)
    outside_path.touch()
    
    try:
        result = await read_file(str(outside_path))
        assert result["status"] == "error"
        assert "outside the project directory" in result["content"][0]["text"]
    finally:
        # Cleanup
        if outside_path.exists():
            outside_path.unlink()
        if outside_path.parent.exists():
            outside_path.parent.rmdir()
