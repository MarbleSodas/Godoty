"""
Godot Debug Tools for Planning Agents.

This module provides specialized tools for planning agents to analyze,
inspect, and understand Godot projects. These tools focus on gathering
information and context rather than making changes.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from strands import tool
from .godot_bridge import get_godot_bridge, ensure_godot_connection, CommandResponse

logger = logging.getLogger(__name__)


@dataclass
class SceneInfo:
    """Information about a Godot scene."""
    name: str
    path: str
    root_node_type: str
    node_count: int
    has_script: bool
    script_path: Optional[str] = None


@dataclass
class NodeInfo:
    """Information about a specific node in the scene tree."""
    name: str
    type: str
    path: str
    parent: Optional[str]
    children: List[str]
    properties: Dict[str, Any]
    groups: List[str]
    has_script: bool
    script_path: Optional[str] = None


@dataclass
class VisualSnapshot:
    """Visual context information from Godot viewport."""
    screenshot_path: Optional[str]
    viewport_size: Tuple[int, int]
    camera_info: Dict[str, Any]
    selected_nodes: List[str]
    scene_tree_state: Dict[str, Any]


class GodotDebugTools:
    """
    Collection of debug and analysis tools for Godot projects.

    These tools are designed for planning agents to gather information
    and context about Godot projects without making modifications.
    """

    def __init__(self):
        """Initialize debug tools with Godot bridge connection."""
        self.bridge = get_godot_bridge()

    async def ensure_connection(self) -> bool:
        """Ensure connection to Godot is active."""
        return await ensure_godot_connection()

    async def get_project_overview(self) -> Dict[str, Any]:
        """
        Get comprehensive overview of the current Godot project.

        Returns:
            Dictionary containing project information, settings, and statistics
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            # Get basic project info
            project_info = await self.bridge.get_project_info()
            if not project_info:
                raise RuntimeError("Unable to retrieve project information")

            # Get current scene info
            current_scene_response = await self.bridge.send_command("get_current_scene_info")
            current_scene = current_scene_response.data if current_scene_response.success else None

            # Get project statistics
            stats_response = await self.bridge.send_command("get_project_statistics")
            stats = stats_response.data if stats_response.success else {}

            # Get editor state
            editor_state_response = await self.bridge.send_command("get_editor_state")
            editor_state = editor_state_response.data if editor_state_response.success else {}

            return {
                "project_info": {
                    "path": project_info.project_path,
                    "name": project_info.project_name,
                    "godot_version": project_info.godot_version,
                    "plugin_version": project_info.plugin_version
                },
                "current_scene": current_scene,
                "statistics": stats,
                "editor_state": editor_state,
                "timestamp": asyncio.get_event_loop().time()
            }

        except Exception as e:
            logger.error(f"Error getting project overview: {e}")
            raise

    async def get_scene_tree_analysis(self, detailed: bool = False) -> Dict[str, Any]:
        """
        Analyze the current scene tree structure.

        Args:
            detailed: Include detailed node information

        Returns:
            Scene tree analysis with node hierarchy and properties
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            command = "get_scene_tree_detailed" if detailed else "get_scene_tree_simple"
            response = await self.bridge.send_command(command)

            if not response.success:
                raise RuntimeError(f"Failed to get scene tree: {response.error}")

            scene_tree = response.data

            # Analyze scene structure
            analysis = {
                "scene_tree": scene_tree,
                "analysis": self._analyze_scene_structure(scene_tree),
                "recommendations": self._generate_scene_recommendations(scene_tree)
            }

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing scene tree: {e}")
            raise

    async def get_node_details(self, node_path: str) -> Optional[NodeInfo]:
        """
        Get detailed information about a specific node.

        Args:
            node_path: Path to the node in scene tree

        Returns:
            NodeInfo with detailed node information, or None if not found
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            response = await self.bridge.send_command(
                "get_node_info",
                node_path=node_path
            )

            if not response.success:
                logger.warning(f"Failed to get node info for {node_path}: {response.error}")
                return None

            node_data = response.data
            return NodeInfo(
                name=node_data.get("name", ""),
                type=node_data.get("type", ""),
                path=node_data.get("path", ""),
                parent=node_data.get("parent"),
                children=node_data.get("children", []),
                properties=node_data.get("properties", {}),
                groups=node_data.get("groups", []),
                has_script=node_data.get("has_script", False),
                script_path=node_data.get("script_path")
            )

        except Exception as e:
            logger.error(f"Error getting node details for {node_path}: {e}")
            return None

    async def search_nodes(
        self,
        search_type: str = "type",
        query: str = "",
        scene_root: Optional[str] = None
    ) -> List[NodeInfo]:
        """
        Search for nodes in the scene tree.

        Args:
            search_type: Type of search ("type", "name", "group", "script")
            query: Search query
            scene_root: Root node to search within (optional)

        Returns:
            List of matching nodes
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            command_map = {
                "type": "search_nodes_by_type",
                "name": "search_nodes_by_name",
                "group": "search_nodes_by_group",
                "script": "search_nodes_by_script"
            }

            if search_type not in command_map:
                raise ValueError(f"Invalid search type: {search_type}")

            command = command_map[search_type]
            params = {"query": query}
            if scene_root:
                params["scene_root"] = scene_root

            response = await self.bridge.send_command(command, **params)

            if not response.success:
                raise RuntimeError(f"Search failed: {response.error}")

            nodes_data = response.data or []
            return [
                NodeInfo(
                    name=node.get("name", ""),
                    type=node.get("type", ""),
                    path=node.get("path", ""),
                    parent=node.get("parent"),
                    children=node.get("children", []),
                    properties=node.get("properties", {}),
                    groups=node.get("groups", []),
                    has_script=node.get("has_script", False),
                    script_path=node.get("script_path")
                )
                for node in nodes_data
            ]

        except Exception as e:
            logger.error(f"Error searching nodes: {e}")
            return []

    async def capture_visual_context(self, include_3d: bool = True) -> VisualSnapshot:
        """
        Capture visual context from current Godot viewport.

        Args:
            include_3d: Include 3D viewport information

        Returns:
            VisualSnapshot with screenshot and viewport information
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            # Capture screenshot
            screenshot_response = await self.bridge.send_command(
                "capture_viewport_screenshot",
                include_3d=include_3d
            )

            # Get viewport information
            viewport_response = await self.bridge.send_command("get_viewport_info")

            # Get selected nodes
            selection_response = await self.bridge.send_command("get_selected_nodes")

            screenshot_path = screenshot_response.data if screenshot_response.success else None
            viewport_info = viewport_response.data if viewport_response.success else {}
            selected_nodes = selection_response.data if selection_response.success else []

            return VisualSnapshot(
                screenshot_path=screenshot_path,
                viewport_size=(
                    viewport_info.get("width", 0),
                    viewport_info.get("height", 0)
                ),
                camera_info=viewport_info.get("camera", {}),
                selected_nodes=selected_nodes,
                scene_tree_state=viewport_info.get("scene_tree", {})
            )

        except Exception as e:
            logger.error(f"Error capturing visual context: {e}")
            raise

    async def get_debug_output(self, lines: int = 100) -> List[str]:
        """
        Get recent debug output from Godot editor.

        Args:
            lines: Number of recent lines to retrieve

        Returns:
            List of debug output lines
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            response = await self.bridge.send_command(
                "get_debug_output",
                lines=lines
            )

            if not response.success:
                raise RuntimeError(f"Failed to get debug output: {response.error}")

            return response.data or []

        except Exception as e:
            logger.error(f"Error getting debug output: {e}")
            return []

    async def analyze_project_structure(self) -> Dict[str, Any]:
        """
        Analyze overall project structure and organization.

        Returns:
            Project structure analysis with recommendations
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            # Get project file list
            files_response = await self.bridge.send_command("get_project_files")
            project_files = files_response.data if files_response.success else []

            # Get scene analysis
            scenes_response = await self.bridge.send_command("analyze_all_scenes")
            scenes_analysis = scenes_response.data if scenes_response.success else {}

            # Get script analysis
            scripts_response = await self.bridge.send_command("analyze_scripts")
            scripts_analysis = scripts_response.data if scripts_response.success else {}

            # Get resource analysis
            resources_response = await self.bridge.send_command("analyze_resources")
            resources_analysis = resources_response.data if resources_response.success else {}

            analysis = {
                "project_files": project_files,
                "scenes": scenes_analysis,
                "scripts": scripts_analysis,
                "resources": resources_analysis,
                "recommendations": self._generate_structure_recommendations(
                    project_files, scenes_analysis, scripts_analysis, resources_analysis
                )
            }

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing project structure: {e}")
            raise

    async def inspect_scene_file(self, scene_path: str) -> Dict[str, Any]:
        """
        Inspect a scene file without loading it.

        Args:
            scene_path: Path to the .tscn file

        Returns:
            Scene file analysis
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            response = await self.bridge.send_command(
                "inspect_scene_file",
                scene_path=scene_path
            )

            if not response.success:
                raise RuntimeError(f"Failed to inspect scene file: {response.error}")

            return response.data

        except Exception as e:
            logger.error(f"Error inspecting scene file {scene_path}: {e}")
            raise

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics from Godot.

        Returns:
            Performance metrics including FPS, memory usage, etc.
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")

        try:
            response = await self.bridge.send_command("get_performance_metrics")

            if not response.success:
                raise RuntimeError(f"Failed to get performance metrics: {response.error}")

            return response.data

        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}

    def _analyze_scene_structure(self, scene_tree: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze scene tree structure and identify patterns."""
        analysis = {
            "total_nodes": 0,
            "node_types": {},
            "depth": 0,
            "complexity_score": 0,
            "issues": []
        }

        def analyze_node(node: Dict[str, Any], depth: int = 0):
            analysis["total_nodes"] += 1
            analysis["depth"] = max(analysis["depth"], depth)

            node_type = node.get("type", "Unknown")
            analysis["node_types"][node_type] = analysis["node_types"].get(node_type, 0) + 1

            # Check for potential issues
            children = node.get("children", [])
            if len(children) > 20:
                analysis["issues"].append(f"Node '{node.get('name', '')}' has too many children ({len(children)})")

            for child in children:
                analyze_node(child, depth + 1)

        if scene_tree:
            analyze_node(scene_tree)

        # Calculate complexity score
        analysis["complexity_score"] = (
            analysis["total_nodes"] * 0.1 +
            analysis["depth"] * 2 +
            len(analysis["node_types"]) * 0.5
        )

        return analysis

    def _generate_scene_recommendations(self, scene_tree: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on scene analysis."""
        recommendations = []

        analysis = self._analyze_scene_structure(scene_tree)

        if analysis["total_nodes"] > 100:
            recommendations.append("Consider splitting large scenes into smaller sub-scenes")

        if analysis["depth"] > 10:
            recommendations.append("Scene hierarchy is very deep, consider flattening some levels")

        if "Node2D" in analysis["node_types"] and analysis["node_types"]["Node2D"] > 50:
            recommendations.append("Many Node2D nodes found, consider grouping them under Container nodes")

        if len(analysis["issues"]) > 0:
            recommendations.append(f"Found {len(analysis['issues'])} potential issues to address")

        return recommendations

    def _generate_structure_recommendations(
        self,
        files: List[str],
        scenes: Dict[str, Any],
        scripts: Dict[str, Any],
        resources: Dict[str, Any]
    ) -> List[str]:
        """Generate project structure recommendations."""
        recommendations = []

        # File organization
        scene_files = [f for f in files if f.endswith('.tscn')]
        script_files = [f for f in files if f.endswith(('.gd', '.cs'))]

        if len(scene_files) > 20 and not any('scenes/' in f for f in scene_files):
            recommendations.append("Consider organizing scenes into a 'scenes/' subfolder")

        if len(script_files) > 20 and not any('scripts/' in f for f in script_files):
            recommendations.append("Consider organizing scripts into a 'scripts/' subfolder")

        # Scene complexity
        if scenes.get("average_node_count", 0) > 50:
            recommendations.append("Average scene complexity is high, consider scene optimization")

        # Script analysis
        if scripts.get("total_lines", 0) > 10000:
            recommendations.append("Large codebase detected, consider code organization and refactoring")

        return recommendations


# Convenience functions for direct tool access
@tool
async def get_project_overview() -> Dict[str, Any]:
    """Get comprehensive project overview from Godot.

    Returns:
        Dict containing project structure, scenes, resources, and metadata
    """
    tools = GodotDebugTools()
    return await tools.get_project_overview()


@tool
async def analyze_scene_tree(detailed: bool = False) -> Dict[str, Any]:
    """Analyze the current scene tree structure in Godot.

    Args:
        detailed: Whether to include detailed node properties

    Returns:
        Dict containing scene tree hierarchy and node information
    """
    tools = GodotDebugTools()
    return await tools.get_scene_tree_analysis(detailed)


@tool
async def capture_visual_context(include_3d: bool = True) -> VisualSnapshot:
    """Capture visual context from the Godot viewport.

    Args:
        include_3d: Whether to capture 3D viewport information

    Returns:
        VisualSnapshot containing screenshot path and viewport information
    """
    tools = GodotDebugTools()
    return await tools.capture_visual_context(include_3d)


@tool
async def search_nodes(search_type: str, query: str, scene_root: Optional[str] = None) -> List[NodeInfo]:
    """Search for nodes in the Godot scene tree.

    Args:
        search_type: Type of search ('name', 'type', 'group', 'script')
        query: Search query string
        scene_root: Optional scene root path to limit search scope

    Returns:
        List of NodeInfo objects matching the search criteria
    """
    tools = GodotDebugTools()
    return await tools.search_nodes(search_type, query, scene_root)