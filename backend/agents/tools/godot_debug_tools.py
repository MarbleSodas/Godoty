"""
Godot Debug Tools for Planning Agents.

This module provides specialized tools for planning agents to analyze,
inspect, and understand Godot projects. These tools focus on gathering
information and context rather than making changes.
"""

import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timedelta
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
    """

    def __init__(self):
        self.bridge = get_godot_bridge()

    async def ensure_connection(self) -> bool:
        return await ensure_godot_connection()

    async def get_project_overview(self) -> Dict[str, Any]:
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")
        try:
            project_info = await self.bridge.get_project_info()
            current_scene_response = await self.bridge.send_command("get_current_scene_detailed")
            current_scene = current_scene_response.data if current_scene_response.success else None
            return {
                "project_info": project_info.__dict__ if project_info else {},
                "current_scene": current_scene,
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error getting project overview: {e}")
            raise

    async def get_scene_tree_analysis(self, detailed: bool = False) -> Dict[str, Any]:
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")
        try:
            response = await self.bridge.send_command("get_current_scene_detailed")
            if not response.success:
                raise RuntimeError(f"Failed to get scene tree: {response.error}")
            scene_data = response.data
            scene_tree = scene_data.get("root", {}) if scene_data else {}
            return {
                "scene_tree": scene_tree,
                "analysis": self._analyze_scene_structure(scene_tree),
                "recommendations": self._generate_scene_recommendations(scene_tree)
            }
        except Exception as e:
            logger.error(f"Error analyzing scene tree: {e}")
            raise

    async def capture_visual_context(self, include_3d: bool = True) -> VisualSnapshot:
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")
        try:
            response = await self.bridge.send_command("capture_visual_context", include_3d=include_3d)
            if not response.success:
                raise RuntimeError(f"Failed to capture visual context: {response.error}")
            data = response.data
            viewport_info = data.get("viewport_info", {})
            editor_state = data.get("editor_state", {})
            return VisualSnapshot(
                screenshot_path=None,
                viewport_size=(viewport_info.get("size", {}).get("x", 0), viewport_info.get("size", {}).get("y", 0)),
                camera_info=viewport_info.get("camera_transform", {}),
                selected_nodes=editor_state.get("selected_nodes", []),
                scene_tree_state=data.get("scene_tree", {})
            )
        except Exception as e:
            logger.error(f"Error capturing visual context: {e}")
            raise

    async def get_debug_output(self, lines: int = 100, severity_filter: Optional[str] = None) -> Dict[str, Any]:
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")
        try:
            response = await self.bridge.send_command("get_debug_output", limit=lines)
            if not response.success:
                raise RuntimeError(f"Failed to get debug output: {response.error}")
            data = response.data or {}
            raw_lines = data.get("messages", [])
            parsed_messages = []
            for line in raw_lines:
                severity = "info"
                if "ERROR:" in line or "[ERROR]" in line: severity = "error"
                elif "WARNING:" in line or "[WARNING]" in line: severity = "warning"
                parsed_messages.append({"severity": severity, "message": line, "raw": line})
            if severity_filter:
                parsed_messages = [msg for msg in parsed_messages if msg["severity"] == severity_filter]
            return {"messages": parsed_messages, "raw_lines": raw_lines}
        except Exception as e:
            logger.error(f"Error getting debug output: {e}")
            return {"messages": [], "raw_lines": []}

    async def capture_editor_viewport(self, include_3d: bool = True, include_2d: bool = True) -> Dict[str, Any]:
        """Capture editor viewport and return image data for vision model processing.
        
        Returns a dictionary with:
        - image: Strands ImageContent format with raw bytes for vision models
        - metadata: Additional capture information
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")
        try:
            response = await self.bridge.send_command("get_visual_snapshot")
            if not response.success:
                raise RuntimeError(f"Failed to capture editor viewport: {response.error}")
            
            data = response.data
            result = {
                "metadata": {
                    "width": data.get("width"),
                    "height": data.get("height"),
                    "timestamp": data.get("timestamp"),
                    "image_path": data.get("image_path"),
                    "viewport_type": data.get("viewport_type", "2d")
                }
            }
            
            # If base64 data is available, include it as Strands ImageContent format
            base64_data = data.get("base64_data")
            if base64_data:
                # Decode base64 to raw bytes for Strands ImageContent
                image_bytes = base64.b64decode(base64_data)
                result["image"] = {
                    "format": "png",
                    "source": {"bytes": image_bytes}
                }
                result["has_image"] = True
            else:
                result["has_image"] = False
                
            return result
        except Exception as e:
            logger.error(f"Error capturing editor viewport: {e}")
            raise

    async def capture_game_viewport(self, wait_frames: int = 3) -> Dict[str, Any]:
        """Capture game viewport and return image data for vision model processing.
        
        Returns a dictionary with:
        - image: Strands ImageContent format with raw bytes for vision models
        - metadata: Additional capture information
        """
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")
        try:
            response = await self.bridge.send_command("capture_game_screenshot", wait_frames=wait_frames)
            if not response.success:
                raise RuntimeError(f"Failed to capture game viewport: {response.error}")
            
            data = response.data
            size = data.get("size", {})
            result = {
                "metadata": {
                    "width": size.get("w"),
                    "height": size.get("h"),
                    "timestamp": data.get("timestamp"),
                    "image_path": data.get("absolute_path")
                }
            }
            
            # GDScript uses "image_b64" for game screenshots, check both keys
            base64_data = data.get("image_b64") or data.get("base64_data")
            if base64_data:
                # Decode base64 to raw bytes for Strands ImageContent
                image_bytes = base64.b64decode(base64_data)
                result["image"] = {
                    "format": "png",
                    "source": {"bytes": image_bytes}
                }
                result["has_image"] = True
            else:
                result["has_image"] = False
                
            return result
        except Exception as e:
            logger.error(f"Error capturing game viewport: {e}")
            raise


    async def search_nodes(self, search_type: str = "type", query: str = "", scene_root: Optional[str] = None) -> List[NodeInfo]:
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
            params = {}
            if search_type == "type": params["type"] = query
            elif search_type == "name": params["name"] = query
            elif search_type == "group": params["group"] = query
            elif search_type == "script": params["script_path"] = query
            if scene_root: params["scene_root"] = scene_root
            response = await self.bridge.send_command(command_map[search_type], **params)
            if not response.success: raise RuntimeError(f"Search failed: {response.error}")
            data = response.data
            matches = data.get("matches", [])
            return [NodeInfo(name=p.split("/")[-1], type="Unknown", path=p, parent=None, children=[], properties={}, groups=[], has_script=False) for p in matches]
        except Exception as e:
            logger.error(f"Error searching nodes: {e}")
            return []

    async def inspect_scene_file(self, scene_path: str) -> Dict[str, Any]:
        if not await self.ensure_connection():
            raise ConnectionError("Failed to connect to Godot plugin")
        try:
            response = await self.bridge.send_command("inspect_scene_file", path=scene_path)
            if not response.success: raise RuntimeError(f"Failed to inspect scene file: {response.error}")
            return response.data
        except Exception as e:
            logger.error(f"Error inspecting scene file {scene_path}: {e}")
            raise

    async def get_performance_metrics(self) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Performance metrics not supported in current plugin version"}

    # --- Restored Methods (Stubbed or Implemented via Composition) ---

    async def get_visual_debug_info(self) -> Dict[str, Any]:
        """Stub for get_visual_debug_info."""
        return {"status": "not_implemented", "message": "Visual debug info not supported in current plugin version"}

    async def get_debug_logs(self, severity_filter: Optional[str] = None, time_range: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
        """Get filtered debug logs using get_debug_output."""
        output = await self.get_debug_output(lines=limit, severity_filter=severity_filter)
        return {"logs": output.get("messages", []), "analytics": {}}

    async def search_debug_logs(self, pattern: str, case_sensitive: bool = False, regex: bool = False) -> Dict[str, Any]:
        """Search debug logs."""
        output = await self.get_debug_output(lines=500)
        raw_lines = output.get("raw_lines", [])
        matches = []
        for line in raw_lines:
            if pattern in line:
                matches.append({"message": line})
        return {"matches": matches}

    async def monitor_debug_output(self, duration: int = 10, severity_filter: Optional[str] = None) -> Dict[str, Any]:
        """Stub for monitor."""
        return {"status": "not_implemented", "message": "Real-time monitoring not implemented"}

    async def analyze_node_performance(self, node_path: str) -> Dict[str, Any]:
        """Stub for node performance."""
        return {"status": "not_implemented"}

    async def get_scene_debug_overlays(self, scene_path: Optional[str] = None) -> Dict[str, Any]:
        """Stub."""
        return {"status": "not_implemented"}

    async def compare_scenes(self, scene_path_a: str, scene_path_b: str) -> Dict[str, Any]:
        """Compare using inspect_scene_file."""
        a = await self.inspect_scene_file(scene_path_a)
        b = await self.inspect_scene_file(scene_path_b)
        return {"scene_a": a, "scene_b": b, "diff": "Comparison logic simplified"}

    async def get_debugger_state(self) -> Dict[str, Any]:
        return {"status": "not_implemented"}

    async def access_debug_variables(self, variable_filter: Optional[str] = None) -> Dict[str, Any]:
        return {"status": "not_implemented"}

    async def get_call_stack_info(self, max_depth: int = 10) -> Dict[str, Any]:
        return {"status": "not_implemented"}

    # Helpers
    def _analyze_scene_structure(self, scene_tree: Dict[str, Any]) -> Dict[str, Any]:
        analysis = {"total_nodes": 0, "node_types": {}, "depth": 0, "complexity_score": 0, "issues": []}
        def analyze_node(node: Dict[str, Any], depth: int = 0):
            analysis["total_nodes"] += 1
            analysis["depth"] = max(analysis["depth"], depth)
            node_type = node.get("type", "Unknown")
            analysis["node_types"][node_type] = analysis["node_types"].get(node_type, 0) + 1
            children = node.get("children", [])
            if len(children) > 20: analysis["issues"].append(f"Node '{node.get('name', '')}' has too many children")
            for child in children: analyze_node(child, depth + 1)
        if scene_tree: analyze_node(scene_tree)
        return analysis

    def _generate_scene_recommendations(self, scene_tree: Dict[str, Any]) -> List[str]:
        return ["Consider splitting large scenes"] if self._analyze_scene_structure(scene_tree)["total_nodes"] > 100 else []


# --- Tool Wrappers ---

@tool
async def get_project_overview() -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_project_overview()

@tool
async def analyze_scene_tree(detailed: bool = False) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_scene_tree_analysis(detailed)

@tool
async def capture_visual_context(include_3d: bool = True) -> VisualSnapshot:
    tools = GodotDebugTools()
    return await tools.capture_visual_context(include_3d)

@tool
async def search_nodes(search_type: str, query: str, scene_root: Optional[str] = None) -> List[NodeInfo]:
    tools = GodotDebugTools()
    return await tools.search_nodes(search_type, query, scene_root)

@tool
async def get_debug_output(lines: int = 100, severity_filter: Optional[str] = None) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_debug_output(lines, severity_filter)

@tool
async def get_performance_metrics() -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_performance_metrics()

@tool
async def inspect_scene_file(scene_path: str) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.inspect_scene_file(scene_path)

@tool
async def capture_editor_viewport(include_3d: bool = True, include_2d: bool = True) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.capture_editor_viewport(include_3d, include_2d)

@tool
async def capture_game_viewport(wait_frames: int = 3) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.capture_game_viewport(wait_frames)

@tool
async def get_visual_debug_info() -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_visual_debug_info()

@tool
async def get_debug_logs(severity_filter: Optional[str] = None, time_range: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_debug_logs(severity_filter, time_range, limit)

@tool
async def search_debug_logs(pattern: str, case_sensitive: bool = False, regex: bool = False) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.search_debug_logs(pattern, case_sensitive, regex)

@tool
async def monitor_debug_output(duration: int = 10, severity_filter: Optional[str] = None) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.monitor_debug_output(duration, severity_filter)

@tool
async def analyze_node_performance(node_path: str) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.analyze_node_performance(node_path)

@tool
async def get_scene_debug_overlays(scene_path: Optional[str] = None) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_scene_debug_overlays(scene_path)

@tool
async def compare_scenes(scene_path_a: str, scene_path_b: str) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.compare_scenes(scene_path_a, scene_path_b)

@tool
async def get_debugger_state() -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_debugger_state()

@tool
async def access_debug_variables(variable_filter: Optional[str] = None) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.access_debug_variables(variable_filter)

@tool
async def get_call_stack_info(max_depth: int = 10) -> Dict[str, Any]:
    tools = GodotDebugTools()
    return await tools.get_call_stack_info(max_depth)