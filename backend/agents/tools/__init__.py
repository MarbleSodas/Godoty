"""Tools for Godot Assistant agents (planning and execution)."""

from .file_system_tools import read_file, list_files, search_codebase
from .web_tools import search_documentation, fetch_webpage, get_godot_api_reference
from .godot_bridge import GodotBridge, get_godot_bridge, ensure_godot_connection
from .godot_debug_tools import (
    GodotDebugTools,
    get_project_overview,
    analyze_scene_tree,
    capture_visual_context,
    capture_editor_viewport,
    capture_game_viewport,
    get_visual_debug_info,
    get_debug_output,
    get_debug_logs,
    search_debug_logs,
    monitor_debug_output,
    get_performance_metrics,
    inspect_scene_file,
    search_nodes,
    analyze_node_performance,
    get_scene_debug_overlays,
    compare_scenes,
    get_debugger_state,
    access_debug_variables,
    get_call_stack_info,
    SceneInfo,
    NodeInfo
)
from .godot_executor_tools import (
    GodotExecutorTools,
    ErrorType,
    get_godot_executor_tools,
    # Tool wrapper functions (essential for start menu creation)
    create_node,
    modify_node_property,
    create_scene,
    open_scene,
    select_nodes,
    play_scene,
    stop_playing,
    # Note: delete_node, reparent_node, save_current_scene removed - not used by planning agent
)
from .mcp_tools import MCPToolManager, get_mcp_tools

__all__ = [
    # File system tools
    "read_file",
    "list_files",
    "search_codebase",
    # Web tools
    "search_documentation",
    "fetch_webpage",
    "get_godot_api_reference",
    # Godot bridge
    "GodotBridge",
    "get_godot_bridge",
    "ensure_godot_connection",
    # Godot debug tools (comprehensive suite)
    "GodotDebugTools",
    "get_project_overview",
    "analyze_scene_tree",
    "capture_visual_context",
    "capture_editor_viewport",
    "capture_game_viewport",
    "get_visual_debug_info",
    "get_debug_output",
    "get_debug_logs",
    "search_debug_logs",
    "monitor_debug_output",
    "get_performance_metrics",
    "inspect_scene_file",
    "search_nodes",
    "analyze_node_performance",
    "get_scene_debug_overlays",
    "compare_scenes",
    "get_debugger_state",
    "access_debug_variables",
    "get_call_stack_info",
    "SceneInfo",
    "NodeInfo",
    # Godot executor tools (essential for start menu creation)
    "GodotExecutorTools",
    "ErrorType",
    "get_godot_executor_tools",
    "create_node",
    "modify_node_property",
    "create_scene",
    "open_scene",
    "select_nodes",
    "play_scene",
    "stop_playing",
    # MCP tools
    "MCPToolManager",
    "get_mcp_tools",
]
