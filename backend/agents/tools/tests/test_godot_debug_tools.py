"""
Tests for Godot Debug Tools module.

This module tests the planning agent debug tools for scene analysis,
visual context capture, and project inspection capabilities.
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agents.tools.godot_debug_tools import (
    GodotDebugTools,
    get_project_overview,
    analyze_scene_tree,
    capture_visual_context,
    search_nodes,
    SceneInfo,
    NodeInfo,
    VisualSnapshot
)


class TestGodotDebugTools:
    """Test cases for GodotDebugTools class."""

    @pytest.mark.asyncio
    async def test_debug_tools_initialization(self, mock_godot_bridge):
        """Test GodotDebugTools initialization."""
        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            tools = GodotDebugTools()

            assert tools.bridge is mock_godot_bridge

    @pytest.mark.asyncio
    async def test_ensure_connection_success(self, mock_godot_bridge):
        """Test ensure_connection when connection succeeds."""
        mock_godot_bridge.is_connected = AsyncMock(return_value=True)
        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.ensure_connection()

        assert result is True
        mock_godot_bridge.is_connected.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_connection_autoconnect(self, mock_godot_bridge):
        """Test ensure_connection when auto-connection is needed."""
        mock_godot_bridge.is_connected = AsyncMock(return_value=False)
        mock_godot_bridge.connect = AsyncMock(return_value=True)
        tools = GodotDebugTools()
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
        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        with pytest.raises(ConnectionError):
            await tools.ensure_connection()

    @pytest.mark.asyncio
    async def test_get_project_overview_success(self, mock_godot_bridge, mock_project_info, mock_scene_tree):
        """Test successful project overview retrieval."""
        # Mock bridge methods
        mock_godot_bridge.get_project_info = AsyncMock(return_value=mock_project_info)
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            # get_current_scene_info
            MagicMock(success=True, data={"name": "Main", "path": "res://scenes/main.tscn"}),
            # get_project_statistics
            MagicMock(success=True, data={"total_scenes": 5, "total_scripts": 10}),
            # get_editor_state
            MagicMock(success=True, data={"playing": False, "current_tool": "Select"})
        ])

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_project_overview()

        # Verify structure
        assert "project_info" in result
        assert "current_scene" in result
        assert "statistics" in result
        assert "editor_state" in result
        assert "timestamp" in result

        # Verify content
        assert result["project_info"]["project_path"] == mock_project_info["project_path"]
        assert result["current_scene"]["name"] == "Main"
        assert result["statistics"]["total_scenes"] == 5
        assert result["editor_state"]["playing"] is False

    @pytest.mark.asyncio
    async def test_get_project_overview_connection_error(self):
        """Test project overview with connection error."""
        tools = GodotDebugTools()
        tools.bridge = MagicMock()
        tools.bridge.is_connected = AsyncMock(return_value=False)
        tools.bridge.connect = AsyncMock(return_value=False)

        with pytest.raises(ConnectionError):
            await tools.get_project_overview()

    @pytest.mark.asyncio
    async def test_get_project_overview_project_info_error(self, mock_godot_bridge):
        """Test project overview when project info fails."""
        mock_godot_bridge.get_project_info = AsyncMock(return_value=None)
        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        with pytest.raises(RuntimeError, match="Unable to retrieve project information"):
            await tools.get_project_overview()

    @pytest.mark.asyncio
    async def test_get_scene_tree_analysis_simple(self, mock_godot_bridge, mock_scene_tree):
        """Test simple scene tree analysis."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_scene_tree
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_scene_tree_analysis(detailed=False)

        assert "scene_tree" in result
        assert "analysis" in result
        assert "recommendations" in result

        # Verify analysis content
        analysis = result["analysis"]
        assert analysis["total_nodes"] > 0
        assert analysis["depth"] > 0
        assert "complexity_score" in analysis
        assert "node_types" in analysis

    @pytest.mark.asyncio
    async def test_get_scene_tree_analysis_detailed(self, mock_godot_bridge, mock_scene_tree):
        """Test detailed scene tree analysis."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_scene_tree
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_scene_tree_analysis(detailed=True)

        assert "scene_tree" in result
        assert "analysis" in result
        assert "recommendations" in result

        # Should call detailed command
        mock_godot_bridge.send_command.assert_called_with("get_scene_tree_detailed")

    @pytest.mark.asyncio
    async def test_get_scene_tree_analysis_failure(self, mock_godot_bridge):
        """Test scene tree analysis when command fails."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Failed to get scene tree"
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        with pytest.raises(RuntimeError, match="Failed to get scene tree"):
            await tools.get_scene_tree_analysis()

    @pytest.mark.asyncio
    async def test_get_node_details_success(self, mock_godot_bridge, mock_node_info):
        """Test successful node details retrieval."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_node_info
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_node_details("Root/Player")

        assert isinstance(result, NodeInfo)
        assert result.name == "Player"
        assert result.type == "CharacterBody2D"
        assert result.path == "Root/Player"
        assert result.parent == "Root"
        assert "Sprite2D" in result.children
        assert result.properties["position"]["x"] == 100
        assert "player" in result.groups
        assert result.has_script is True
        assert result.script_path == "res://scripts/player.gd"

    @pytest.mark.asyncio
    async def test_get_node_details_not_found(self, mock_godot_bridge):
        """Test node details when node not found."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Node not found"
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_node_details("Root/NonExistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_search_nodes_by_type(self, mock_godot_bridge, mock_search_results):
        """Test searching nodes by type."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_search_results
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        results = await tools.search_nodes("type", "CharacterBody2D")

        assert len(results) == 2
        assert all(isinstance(node, NodeInfo) for node in results)
        assert results[0].type == "CharacterBody2D"
        mock_godot_bridge.send_command.assert_called_with(
            "search_nodes_by_type",
            query="CharacterBody2D"
        )

    @pytest.mark.asyncio
    async def test_search_nodes_by_name(self, mock_godot_bridge, mock_search_results):
        """Test searching nodes by name."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_search_results
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        results = await tools.search_nodes("name", "Player")

        assert len(results) == 2
        assert results[0].name == "Player"
        mock_godot_bridge.send_command.assert_called_with(
            "search_nodes_by_name",
            query="Player"
        )

    @pytest.mark.asyncio
    async def test_search_nodes_by_group(self, mock_godot_bridge, mock_search_results):
        """Test searching nodes by group."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_search_results
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        results = await tools.search_nodes("group", "player")

        assert len(results) == 2
        mock_godot_bridge.send_command.assert_called_with(
            "search_nodes_by_group",
            query="player"
        )

    @pytest.mark.asyncio
    async def test_search_nodes_with_scene_root(self, mock_godot_bridge, mock_search_results):
        """Test searching nodes with scene root filter."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_search_results
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        results = await tools.search_nodes(
            "type",
            "Node2D",
            scene_root="Root/SubScene"
        )

        assert len(results) == 2
        mock_godot_bridge.send_command.assert_called_with(
            "search_nodes_by_type",
            query="Node2D",
            scene_root="Root/SubScene"
        )

    @pytest.mark.asyncio
    async def test_search_nodes_invalid_type(self, mock_godot_bridge):
        """Test searching nodes with invalid search type."""
        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        with pytest.raises(ValueError, match="Invalid search type"):
            await tools.search_nodes("invalid_type", "query")

    @pytest.mark.asyncio
    async def test_search_nodes_failure(self, mock_godot_bridge):
        """Test searching nodes when command fails."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Search failed"
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        with pytest.raises(RuntimeError, match="Search failed"):
            await tools.search_nodes("type", "Node2D")

    @pytest.mark.asyncio
    async def test_capture_visual_context_success(self, mock_godot_bridge, mock_visual_snapshot):
        """Test successful visual context capture."""
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            # capture_viewport_screenshot
            MagicMock(success=True, data=mock_visual_snapshot["screenshot_path"]),
            # get_viewport_info
            MagicMock(success=True, data={
                "width": mock_visual_snapshot["viewport_size"][0],
                "height": mock_visual_snapshot["viewport_size"][1],
                "camera": mock_visual_snapshot["camera_info"],
                "scene_tree": mock_visual_snapshot["scene_tree_state"]
            }),
            # get_selected_nodes
            MagicMock(success=True, data=mock_visual_snapshot["selected_nodes"])
        ])

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.capture_visual_context(include_3d=True)

        assert isinstance(result, VisualSnapshot)
        assert result.screenshot_path == mock_visual_snapshot["screenshot_path"]
        assert result.viewport_size == mock_visual_snapshot["viewport_size"]
        assert result.camera_info == mock_visual_snapshot["camera_info"]
        assert result.selected_nodes == mock_visual_snapshot["selected_nodes"]
        assert result.scene_tree_state == mock_visual_snapshot["scene_tree_state"]

        # Verify correct commands were called
        assert mock_godot_bridge.send_command.call_count == 3
        mock_godot_bridge.send_command.assert_any_call(
            "capture_viewport_screenshot",
            include_3d=True
        )

    @pytest.mark.asyncio
    async def test_capture_visual_context_no_3d(self, mock_godot_bridge):
        """Test visual context capture without 3D."""
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            MagicMock(success=True, data=None),  # No screenshot
            MagicMock(success=True, data={"width": 800, "height": 600}),
            MagicMock(success=True, data=[])
        ])

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.capture_visual_context(include_3d=False)

        assert result.screenshot_path is None
        assert result.viewport_size == (800, 600)
        assert result.selected_nodes == []

        mock_godot_bridge.send_command.assert_any_call(
            "capture_viewport_screenshot",
            include_3d=False
        )

    @pytest.mark.asyncio
    async def test_get_debug_output_success(self, mock_godot_bridge):
        """Test successful debug output retrieval."""
        debug_lines = [
            "INFO: Scene loaded",
            "WARNING: Missing texture",
            "ERROR: Script not found"
        ]

        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=debug_lines
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_debug_output(lines=50)

        assert len(result) == 3
        assert result[0] == "INFO: Scene loaded"
        assert result[2] == "ERROR: Script not found"

        mock_godot_bridge.send_command.assert_called_with("get_debug_output", lines=50)

    @pytest.mark.asyncio
    async def test_get_debug_output_failure(self, mock_godot_bridge):
        """Test debug output retrieval failure."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Failed to get debug output"
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_debug_output()

        assert result == []

    @pytest.mark.asyncio
    async def test_analyze_project_structure_success(self, mock_godot_bridge):
        """Test successful project structure analysis."""
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            # get_project_files
            MagicMock(success=True, data=["res://scenes/main.tscn", "res://scripts/player.gd"]),
            # analyze_all_scenes
            MagicMock(success=True, data={"total_scenes": 2, "average_nodes": 25}),
            # analyze_scripts
            MagicMock(success=True, data={"total_scripts": 5, "total_lines": 1500}),
            # analyze_resources
            MagicMock(success=True, data={"textures": 10, "sounds": 5})
        ])

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.analyze_project_structure()

        assert "project_files" in result
        assert "scenes" in result
        assert "scripts" in result
        assert "resources" in result
        assert "recommendations" in result

        assert len(result["project_files"]) == 2
        assert result["scenes"]["total_scenes"] == 2
        assert result["scripts"]["total_scripts"] == 5
        assert result["resources"]["textures"] == 10

    @pytest.mark.asyncio
    async def test_inspect_scene_file_success(self, mock_godot_bridge):
        """Test successful scene file inspection."""
        scene_data = {
            "nodes": [
                {"name": "Root", "type": "Node2D", "children": ["Root/Player"]},
                {"name": "Player", "type": "CharacterBody2D", "parent": "Root"}
            ],
            "properties": {
                "editable": True,
                "subresources": {}
            }
        }

        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=scene_data
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.inspect_scene_file("res://scenes/player.tscn")

        assert result["nodes"][0]["name"] == "Root"
        assert result["nodes"][1]["type"] == "CharacterBody2D"
        assert result["properties"]["editable"] is True

        mock_godot_bridge.send_command.assert_called_with(
            "inspect_scene_file",
            scene_path="res://scenes/player.tscn"
        )

    @pytest.mark.asyncio
    async def test_inspect_scene_file_failure(self, mock_godot_bridge):
        """Test scene file inspection failure."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Scene file not found"
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        with pytest.raises(RuntimeError, match="Scene file not found"):
            await tools.inspect_scene_file("res://scenes/nonexistent.tscn")

    @pytest.mark.asyncio
    async def test_get_performance_metrics_success(self, mock_godot_bridge):
        """Test successful performance metrics retrieval."""
        metrics = {
            "fps": 60.0,
            "frame_time": 16.67,
            "memory_usage": 256.5,
            "draw_calls": 150,
            "node_count": 42
        }

        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=metrics
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_performance_metrics()

        assert result["fps"] == 60.0
        assert result["frame_time"] == 16.67
        assert result["memory_usage"] == 256.5
        assert result["draw_calls"] == 150
        assert result["node_count"] == 42

    @pytest.mark.asyncio
    async def test_get_performance_metrics_failure(self, mock_godot_bridge):
        """Test performance metrics retrieval failure."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Performance data unavailable"
        ))

        tools = GodotDebugTools()
        tools.bridge = mock_godot_bridge

        result = await tools.get_performance_metrics()

        assert result == {}

    def test_analyze_scene_structure(self, mock_scene_tree):
        """Test scene structure analysis logic."""
        tools = GodotDebugTools()

        analysis = tools._analyze_scene_structure(mock_scene_tree)

        assert analysis["total_nodes"] == 4  # Root, Player, Sprite2D, Camera2D
        assert analysis["depth"] == 3  # Root -> Player -> Sprite2D
        assert "Node2D" in analysis["node_types"]
        assert "CharacterBody2D" in analysis["node_types"]
        assert analysis["complexity_score"] > 0

    def test_analyze_scene_structure_empty(self):
        """Test scene structure analysis with empty tree."""
        tools = GodotDebugTools()

        analysis = tools._analyze_scene_structure({})

        assert analysis["total_nodes"] == 0
        assert analysis["depth"] == 0
        assert analysis["complexity_score"] == 0
        assert analysis["node_types"] == {}

    def test_generate_scene_recommendations(self, mock_scene_tree):
        """Test scene recommendations generation."""
        tools = GodotDebugTools()

        # Create a complex scene for recommendations
        complex_scene = {
            "name": "Root",
            "type": "Node",
            "children": [{"name": f"Child{i}", "type": "Node", "children": []} for i in range(25)]
        }

        recommendations = tools._generate_scene_recommendations(complex_scene)

        assert len(recommendations) > 0
        assert any("many children" in rec.lower() for rec in recommendations)

    def test_generate_structure_recommendations(self):
        """Test project structure recommendations generation."""
        tools = GodotDebugTools()

        files = ["res://scene1.tscn", "res://scene2.tscn"] * 15  # Many scene files
        scenes = {"average_node_count": 60}  # High complexity
        scripts = {"total_lines": 15000}  # Large codebase
        resources = {"textures": 50}

        recommendations = tools._generate_structure_recommendations(
            files, scenes, scripts, resources
        )

        assert len(recommendations) > 0
        # Should recommend organizing scenes into subfolder
        assert any("scenes/" in rec for rec in recommendations)


class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    @pytest.mark.asyncio
    async def test_get_project_overview_function(self, mock_godot_bridge, mock_project_info):
        """Test get_project_overview convenience function."""
        mock_godot_bridge.get_project_info = AsyncMock(return_value=mock_project_info)
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True, data={})))

        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await get_project_overview()

            assert "project_info" in result
            assert result["project_info"]["project_path"] == mock_project_info["project_path"]

    @pytest.mark.asyncio
    async def test_analyze_scene_tree_function(self, mock_godot_bridge, mock_scene_tree):
        """Test analyze_scene_tree convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_scene_tree
        ))

        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await analyze_scene_tree()

            assert "scene_tree" in result
            assert "analysis" in result

    @pytest.mark.asyncio
    async def test_capture_visual_context_function(self, mock_godot_bridge, mock_visual_snapshot):
        """Test capture_visual_context convenience function."""
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            MagicMock(success=True, data=mock_visual_snapshot["screenshot_path"]),
            MagicMock(success=True, data={"width": 800, "height": 600}),
            MagicMock(success=True, data=mock_visual_snapshot["selected_nodes"])
        ])

        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            result = await capture_visual_context()

            assert isinstance(result, VisualSnapshot)
            assert result.screenshot_path == mock_visual_snapshot["screenshot_path"]

    @pytest.mark.asyncio
    async def test_search_nodes_function(self, mock_godot_bridge, mock_search_results):
        """Test search_nodes convenience function."""
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_search_results
        ))

        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            results = await search_nodes("type", "Node2D")

            assert len(results) == 2
            assert all(isinstance(node, NodeInfo) for node in results)


class TestDataClasses:
    """Test cases for data classes."""

    def test_scene_info_creation(self):
        """Test SceneInfo dataclass creation."""
        info = SceneInfo(
            name="MainScene",
            path="res://scenes/main.tscn",
            root_node_type="Node2D",
            node_count=10,
            has_script=True,
            script_path="res://scripts/main.gd"
        )

        assert info.name == "MainScene"
        assert info.path == "res://scenes/main.tscn"
        assert info.root_node_type == "Node2D"
        assert info.node_count == 10
        assert info.has_script is True
        assert info.script_path == "res://scripts/main.gd"

    def test_scene_info_defaults(self):
        """Test SceneInfo with default values."""
        info = SceneInfo(
            name="Test",
            path="res://test.tscn",
            root_node_type="Node",
            node_count=1,
            has_script=False
        )

        assert info.script_path is None

    def test_node_info_creation(self, mock_node_info):
        """Test NodeInfo dataclass creation."""
        info = NodeInfo(**mock_node_info)

        assert info.name == "Player"
        assert info.type == "CharacterBody2D"
        assert info.path == "Root/Player"
        assert info.parent == "Root"
        assert len(info.children) == 2
        assert info.properties["position"]["x"] == 100
        assert "player" in info.groups
        assert info.has_script is True
        assert info.script_path == "res://scripts/player.gd"

    def test_node_info_defaults(self):
        """Test NodeInfo with default values."""
        info = NodeInfo(
            name="TestNode",
            type="Node",
            path="Root/Test",
            parent="Root",
            children=[],
            properties={},
            groups=[],
            has_script=False
        )

        assert info.script_path is None

    def test_visual_snapshot_creation(self, mock_visual_snapshot):
        """Test VisualSnapshot dataclass creation."""
        snapshot = VisualSnapshot(**mock_visual_snapshot)

        assert snapshot.screenshot_path == mock_visual_snapshot["screenshot_path"]
        assert snapshot.viewport_size == mock_visual_snapshot["viewport_size"]
        assert snapshot.camera_info == mock_visual_snapshot["camera_info"]
        assert snapshot.selected_nodes == mock_visual_snapshot["selected_nodes"]
        assert snapshot.scene_tree_state == mock_visual_snapshot["scene_tree_state"]

    def test_visual_snapshot_defaults(self):
        """Test VisualSnapshot with default values."""
        snapshot = VisualSnapshot(
            screenshot_path=None,
            viewport_size=(800, 600),
            camera_info={},
            selected_nodes=[],
            scene_tree_state={}
        )

        assert snapshot.screenshot_path is None
        assert snapshot.viewport_size == (800, 600)
        assert snapshot.camera_info == {}
        assert snapshot.selected_nodes == []
        assert snapshot.scene_tree_state == {}