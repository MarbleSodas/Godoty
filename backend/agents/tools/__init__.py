"""Tools for the planning agent."""

from .file_system_tools import read_file, list_files, search_codebase
from .web_tools import search_documentation, fetch_webpage, get_godot_api_reference
from .godot_bridge import GodotBridge, get_godot_bridge, ensure_godot_connection
from .godot_debug_tools import (
    GodotDebugTools,
    get_project_overview,
    analyze_scene_tree,
    SceneInfo,
    NodeInfo
)
from .godot_executor_tools import (
    GodotExecutorTools,
    create_node,
    modify_node_property,
    delete_node,
    create_scene,
    open_scene,
    select_nodes,
    play_scene,
    stop_playing,
    CreationResult,
    ModificationResult
)
from .godot_security import (
    GodotSecurityValidator,
    SecurityContext,
    OperationRisk,
    ValidationResult,
    get_security_validator,
    set_security_context,
    create_default_security_context,
    validate_operation,
    validate_path
)

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
    # Godot debug tools (essential only)
    "GodotDebugTools",
    "get_project_overview",
    "analyze_scene_tree",
    "SceneInfo",
    "NodeInfo",
    # Godot executor tools (core functionality)
    "GodotExecutorTools",
    "create_node",
    "modify_node_property",
    "delete_node",
    "create_scene",
    "open_scene",
    "select_nodes",
    "play_scene",
    "stop_playing",
    "CreationResult",
    "ModificationResult",
    # Godot security (essential only)
    "GodotSecurityValidator",
    "SecurityContext",
    "OperationRisk",
    "ValidationResult",
    "get_security_validator",
    "set_security_context",
    "create_default_security_context",
    "validate_operation",
    "validate_path"
]
