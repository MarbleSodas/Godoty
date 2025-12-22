"""Godoty Agent Tools - Actions the agents can perform.

Tools are categorized into:
- Perception: Screenshot, scene tree, script introspection
- Actuation: File read/write, project settings modification
- HITL: Tools requiring human confirmation before execution

HITL Flow (Split-Brain Architecture):
1. Actuation tools request confirmation via ConnectionManager (→ Tauri UI)
2. User approves/denies in Tauri desktop app
3. If approved, command is sent to Godot plugin for execution
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


# Global reference to the WebSocket connection for Godot communication
# This will be set by the main server when a connection is established
_ws_connection: Any = None

# Global reference to the ConnectionManager for HITL confirmations
# This enables routing confirmations through Tauri
_connection_manager: Any = None

# Global project path for scoped file operations
# Set when Godot connects with a project, cleared on disconnect
_project_path: str | None = None

# Global Godot version for version-specific documentation queries
# Set when Godot connects, parsed to major.minor format (e.g., "4.3")
_godot_version: str | None = None

_pending_requests: dict[int, asyncio.Future] = {}
_request_id_counter = 1000


def set_ws_connection(ws: Any) -> None:
    """Set the active WebSocket connection for tool communication."""
    global _ws_connection
    _ws_connection = ws


def get_ws_connection() -> Any:
    """Get the active WebSocket connection."""
    return _ws_connection


def set_connection_manager(manager: Any) -> None:
    """Set the ConnectionManager for HITL confirmation routing."""
    global _connection_manager
    _connection_manager = manager


def get_connection_manager() -> Any:
    """Get the ConnectionManager for HITL confirmations."""
    return _connection_manager


def set_project_path(path: str | None) -> None:
    """Set the current Godot project path.
    
    Called when Godot connects with a project. This path is used
    to scope file operations to prevent access outside the project.
    
    Args:
        path: Absolute path to the Godot project root, or None to clear
    """
    global _project_path
    _project_path = path


def get_project_path() -> str | None:
    """Get the current Godot project path."""
    return _project_path


def set_godot_version(version: str | None) -> None:
    global _godot_version
    _godot_version = version


def get_godot_version() -> str | None:
    return _godot_version


def clear_pending_requests() -> None:
    """Clear all pending requests when connection is lost.
    
    This should be called when the Godot WebSocket disconnects to prevent
    orphaned futures from accumulating.
    """
    for request_id, future in list(_pending_requests.items()):
        if not future.done():
            future.set_exception(ConnectionError("Godot connection closed"))
    _pending_requests.clear()


async def _send_request(method: str, params: dict | None = None) -> Any:
    """Send a JSON-RPC request to the Godot plugin and await response.

    This is used by tools to communicate with the Godot Editor.
    """
    global _request_id_counter

    if _ws_connection is None:
        return {"error": "No active Godot connection"}

    request_id = _request_id_counter
    _request_id_counter += 1

    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": request_id,
    }

    # Create a future to await the response
    future: asyncio.Future = asyncio.Future()
    _pending_requests[request_id] = future

    try:
        import json
        await _ws_connection.send_text(json.dumps(request))
        # Wait for response with timeout
        result = await asyncio.wait_for(future, timeout=30.0)
        return result
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    finally:
        _pending_requests.pop(request_id, None)


import logging

_hitl_logger = logging.getLogger("godoty.hitl")


async def _request_hitl_confirmation(
    action_type: str,
    description: str,
    details: dict[str, Any],
) -> bool:
    """Request human-in-the-loop confirmation via Tauri UI. Checks device-level preferences first."""
    if _connection_manager is None:
        return False
    
    prefs = _connection_manager.get_hitl_preferences()
    if prefs:
        if prefs.always_allow_all:
            _hitl_logger.info(f"HITL auto-approved (always_allow_all): {action_type} - {description}")
            return True
        
        if prefs.always_allow.get(action_type, False):
            _hitl_logger.info(f"HITL auto-approved ({action_type}): {description}")
            return True
    
    response = await _connection_manager.request_confirmation(
        action_type=action_type,
        description=description,
        details=details,
    )
    
    return response.approved


def resolve_response(request_id: int, result: Any) -> None:
    """Resolve a pending request with its response.

    Called by the main server when receiving responses from Godot.
    """
    if request_id in _pending_requests:
        _pending_requests[request_id].set_result(result)


# ============================================================================
# Perception Tools
# ============================================================================


class ScreenshotParams(BaseModel):
    """Parameters for screenshot request."""

    viewport: str = Field(
        default="3d",
        description="Which viewport to capture: '3d', '2d', or 'editor'"
    )
    max_width: int = Field(
        default=1024,
        description="Maximum width to downscale image to (for token efficiency)"
    )


async def request_screenshot(viewport: str = "3d", max_width: int = 1024) -> str:
    """Request a screenshot from the Godot Editor.

    Args:
        viewport: Which viewport to capture ('3d', '2d', or 'editor')
        max_width: Maximum width for the image (will be downscaled)

    Returns:
        Base64-encoded JPEG image or error message
    """
    result = await _send_request("take_screenshot", {
        "viewport": viewport,
        "max_width": max_width,
    })

    if isinstance(result, dict) and "error" in result:
        return f"Screenshot failed: {result['error']}"

    if isinstance(result, dict) and "image" in result:
        return result["image"]  # Base64 encoded

    return "Screenshot failed: unexpected response"


async def get_scene_tree() -> dict:
    """Get the scene tree structure of the currently edited scene.

    Returns:
        A dictionary representing the scene tree hierarchy with node names,
        types, and children.
    """
    result = await _send_request("get_scene_tree", {})

    if isinstance(result, dict) and "error" in result:
        return {"error": result["error"]}

    if isinstance(result, dict) and "tree" in result:
        return result["tree"]

    return {"error": "Failed to get scene tree"}


async def get_open_script() -> dict:
    """Get the currently open script in the Godot Script Editor.

    Returns:
        A dictionary with 'path' and 'content' keys, or an error.
    """
    result = await _send_request("get_open_script", {})

    if isinstance(result, dict) and "error" in result:
        return {"error": result["error"]}

    if isinstance(result, dict) and "path" in result:
        return {
            "path": result.get("path", ""),
            "content": result.get("content", ""),
        }

    return {"error": "Failed to get open script"}


async def get_project_settings(setting_path: str | None = None) -> dict:
    """Get project settings from the Godot project.

    Args:
        setting_path: Optional specific setting path (e.g., 'display/window/size/viewport_width')
                     If None, returns common project settings.

    Returns:
        Dictionary of settings or specific setting value
    """
    result = await _send_request("get_project_settings", {
        "path": setting_path,
    })

    if isinstance(result, dict):
        return result

    return {"error": "Failed to get project settings"}


# ============================================================================
# Actuation Tools
# ============================================================================


async def read_project_file(path: str) -> str:
    """Read a file from the Godot project.

    Args:
        path: The file path relative to project root (e.g., 'scripts/player.gd')

    Returns:
        The file contents as a string, or an error message
    """
    result = await _send_request("read_file", {"path": path})

    if isinstance(result, dict) and "error" in result:
        return f"Error reading file: {result['error']}"

    if isinstance(result, dict) and "content" in result:
        return result["content"]

    return "Error: unexpected response"


class WriteFileResult(BaseModel):
    """Result of a file write operation."""

    success: bool
    message: str
    requires_confirmation: bool = True


async def write_project_file(
    path: str,
    content: str,
    *,
    create_backup: bool = True,
) -> dict:
    """Write content to a file in the Godot project.

    IMPORTANT: This tool requires HITL confirmation before execution.
    The request will be sent to the Tauri desktop app for user approval
    before the file is actually modified.

    Args:
        path: The file path relative to project root
        content: The new content to write
        create_backup: Whether to backup the original file first

    Returns:
        Result dictionary with success status and message
    """
    # First, request HITL confirmation via Tauri
    approved = await _request_hitl_confirmation(
        action_type="write_file",
        description=f"Write to file: {path}",
        details={
            "path": path,
            "content": content,
            "create_backup": create_backup,
        },
    )
    
    if not approved:
        return {
            "success": False,
            "message": "Operation denied by user",
            "denied": True,
        }
    
    # User approved - send command to Godot (without requires_confirmation)
    result = await _send_request("write_file", {
        "path": path,
        "content": content,
        "create_backup": create_backup,
    })

    if isinstance(result, dict):
        return result

    return {"error": "Unexpected response from write operation"}


async def set_project_setting(path: str, value: Any) -> dict:
    """Set a project setting in the Godot project.

    IMPORTANT: This tool requires HITL confirmation via Tauri.

    Args:
        path: The setting path (e.g., 'display/window/size/viewport_width')
        value: The value to set

    Returns:
        Result dictionary with success status
    """
    # Request HITL confirmation via Tauri
    approved = await _request_hitl_confirmation(
        action_type="set_project_setting",
        description=f"Set project setting: {path}",
        details={
            "path": path,
            "value": value,
        },
    )
    
    if not approved:
        return {
            "success": False,
            "message": "Operation denied by user",
            "denied": True,
        }
    
    # User approved - send to Godot
    result = await _send_request("set_project_setting", {
        "path": path,
        "value": value,
    })

    if isinstance(result, dict):
        return result

    return {"error": "Unexpected response"}


async def create_node(
    parent_path: str,
    node_name: str,
    node_type: str,
    properties: dict | None = None,
) -> dict:
    """Create a new node in the scene tree.

    IMPORTANT: This tool requires HITL confirmation via Tauri.

    Args:
        parent_path: NodePath to the parent node
        node_name: Name for the new node
        node_type: Godot node type (e.g., 'CharacterBody2D', 'Sprite2D')
        properties: Optional dictionary of properties to set on the node

    Returns:
        Result dictionary with success status
    """
    # Request HITL confirmation via Tauri
    approved = await _request_hitl_confirmation(
        action_type="create_node",
        description=f"Create {node_type} node '{node_name}' under {parent_path}",
        details={
            "parent_path": parent_path,
            "node_name": node_name,
            "node_type": node_type,
            "properties": properties or {},
        },
    )
    
    if not approved:
        return {
            "success": False,
            "message": "Operation denied by user",
            "denied": True,
        }
    
    # User approved - send to Godot
    result = await _send_request("create_node", {
        "parent_path": parent_path,
        "node_name": node_name,
        "node_type": node_type,
        "properties": properties or {},
    })

    if isinstance(result, dict):
        return result

    return {"error": "Unexpected response"}


async def delete_node(node_path: str) -> dict:
    """Delete a node from the scene tree.

    IMPORTANT: This tool requires HITL confirmation via Tauri.

    Args:
        node_path: NodePath to the node to delete

    Returns:
        Result dictionary with success status
    """
    # Request HITL confirmation via Tauri
    approved = await _request_hitl_confirmation(
        action_type="delete_node",
        description=f"Delete node: {node_path}",
        details={
            "node_path": node_path,
        },
    )
    
    if not approved:
        return {
            "success": False,
            "message": "Operation denied by user",
            "denied": True,
        }
    
    # User approved - send to Godot
    result = await _send_request("delete_node", {
        "node_path": node_path,
    })

    if isinstance(result, dict):
        return result

    return {"error": "Unexpected response"}


# ============================================================================
# Knowledge Base Tools
# ============================================================================


async def query_godot_docs(query: str, num_results: int = 5) -> list[dict]:
    """Search the Godot documentation knowledge base.
    
    Searches the locally-indexed Godot documentation for relevant information
    about classes, methods, properties, signals, and best practices.
    
    Args:
        query: Natural language query about Godot APIs, nodes, or GDScript
               Examples: "How to use move_and_slide", "AnimationPlayer signals"
        num_results: Maximum number of results to return (default: 5)
    
    Returns:
        List of relevant documentation chunks with content and metadata
    """
    try:
        from app.knowledge import get_godot_knowledge
        
        version = get_godot_version() or "4.5"
        knowledge = get_godot_knowledge(version=version)
        results = await knowledge.search(query, num_results=num_results)
        return results
    except Exception as e:
        return [{"error": f"Knowledge search failed: {e}"}]


async def get_symbol_info(
    file_path: str,
    line: int,
    character: int,
) -> dict:
    """Get documentation for a symbol at a specific position via LSP.
    
    Connects to Godot's running GDScript language server (port 6005) to fetch
    real-time documentation, type info, and signatures for the symbol at the
    given position.
    
    Args:
        file_path: Absolute path to the .gd file
        line: Line number (0-indexed)
        character: Character position in the line (0-indexed)
    
    Returns:
        Dictionary with hover documentation from the LSP, or error message
    """
    try:
        from app.knowledge import get_lsp_client
        
        client = get_lsp_client()
        result = await client.get_hover(file_path, line, character)
        
        if result is None:
            return {"error": "No symbol information available at this position"}
        
        # Extract content from hover result
        contents = result.get("contents", {})
        if isinstance(contents, dict):
            return {
                "documentation": contents.get("value", ""),
                "kind": contents.get("kind", "plaintext"),
            }
        elif isinstance(contents, str):
            return {"documentation": contents}
        elif isinstance(contents, list):
            return {"documentation": "\n\n".join(str(c) for c in contents)}
        
        return result
        
    except ConnectionError:
        return {"error": "GDScript LSP not available. Is Godot editor running?"}
    except Exception as e:
        return {"error": f"LSP request failed: {e}"}


async def get_code_completions(
    file_path: str,
    line: int,
    character: int,
) -> list[dict]:
    """Get autocompletion suggestions from the GDScript LSP.
    
    Connects to Godot's language server to get context-aware completion
    suggestions for the current cursor position.
    
    Args:
        file_path: Absolute path to the .gd file
        line: Line number (0-indexed)
        character: Character position in the line (0-indexed)
    
    Returns:
        List of completion items with label, kind, and documentation
    """
    try:
        from app.knowledge import get_lsp_client
        
        client = get_lsp_client()
        completions = await client.get_completions(file_path, line, character)
        
        # Simplify completion items for agent consumption
        return [
            {
                "label": item.get("label", ""),
                "kind": item.get("kind", 0),
                "detail": item.get("detail", ""),
                "documentation": item.get("documentation", ""),
            }
            for item in completions[:20]  # Limit to 20 items
        ]
        
    except ConnectionError:
        return [{"error": "GDScript LSP not available. Is Godot editor running?"}]
    except Exception as e:
        return [{"error": f"LSP request failed: {e}"}]


# ============================================================================
# Scoped File Tools (Project-Restricted)
# ============================================================================


from pathlib import Path as PathType


def _validate_path_in_project(relative_path: str) -> PathType:
    """Validate a path is within the project and return the absolute path.
    
    Security: Uses Path.resolve() to handle '..' traversal and symlinks.
    The resolved path must still be under the project root.
    
    Args:
        relative_path: A path relative to the project root
        
    Returns:
        Absolute Path object pointing to the validated location
        
    Raises:
        ValueError: If no project is connected or path escapes project
    """
    from pathlib import Path
    
    if _project_path is None:
        raise ValueError("No Godot project connected")
    
    project_root = Path(_project_path).resolve()
    
    # Handle both relative and absolute paths
    if Path(relative_path).is_absolute():
        target_path = Path(relative_path).resolve()
    else:
        target_path = (project_root / relative_path).resolve()
    
    # Security check: ensure resolved path is within project
    try:
        target_path.relative_to(project_root)
    except ValueError:
        raise ValueError(
            f"Path '{relative_path}' escapes project directory. "
            f"Only files within the project are accessible."
        )
    
    return target_path


async def list_project_files(
    directory: str = "",
    pattern: str = "*",
    recursive: bool = False,
) -> list[dict]:
    """List files in a project directory.
    
    Args:
        directory: Directory path relative to project root (empty = root)
        pattern: Glob pattern to filter files (e.g., '*.gd', '*.tscn')
        recursive: If True, search recursively in subdirectories
        
    Returns:
        List of file info dicts with 'name', 'path', 'is_dir', 'size' keys
    """
    from pathlib import Path
    
    try:
        if directory:
            target_dir = _validate_path_in_project(directory)
        elif _project_path:
            target_dir = Path(_project_path).resolve()
        else:
            return [{"error": "No Godot project connected"}]
    except ValueError as e:
        return [{"error": str(e)}]
    
    if not target_dir.is_dir():
        return [{"error": f"'{directory}' is not a directory"}]
    
    try:
        if recursive:
            files = list(target_dir.rglob(pattern))
        else:
            files = list(target_dir.glob(pattern))
        
        max_files = 100
        if len(files) > max_files:
            files = files[:max_files]
        
        if _project_path is None:
            return [{"error": "No Godot project connected"}]
        project_root = Path(_project_path).resolve()
        return [
            {
                "name": f.name,
                "path": str(f.relative_to(project_root)),
                "is_dir": f.is_dir(),
                "size": f.stat().st_size if f.is_file() else None,
            }
            for f in sorted(files)
        ]
    except Exception as e:
        return [{"error": f"Failed to list files: {e}"}]


async def read_file(path: str) -> str:
    """Read a file from the Godot project.
    
    This tool reads files directly from the filesystem, unlike read_project_file
    which routes through the Godot plugin. Use this for files that don't need
    to be open in the editor.
    
    Args:
        path: File path relative to project root (e.g., 'scripts/player.gd')
        
    Returns:
        The file contents as a string, or an error message
    """
    try:
        target_path = _validate_path_in_project(path)
    except ValueError as e:
        return f"Error: {e}"
    
    if not target_path.is_file():
        return f"Error: '{path}' is not a file or does not exist"
    
    try:
        return target_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: '{path}' is not a text file (binary content)"
    except Exception as e:
        return f"Error reading file: {e}"


async def write_file(
    path: str,
    content: str,
    *,
    create_dirs: bool = False,
) -> dict:
    """Write content to a file in the Godot project.
    
    IMPORTANT: This tool requires HITL confirmation before execution.
    
    Args:
        path: File path relative to project root
        content: The content to write
        create_dirs: If True, create parent directories if they don't exist
        
    Returns:
        Result dictionary with success status and message
    """
    try:
        target_path = _validate_path_in_project(path)
    except ValueError as e:
        return {"success": False, "message": str(e)}
    
    # Request HITL confirmation via Tauri
    approved = await _request_hitl_confirmation(
        action_type="write_file",
        description=f"Write to file: {path}",
        details={
            "path": path,
            "content": content,
            "create_dirs": create_dirs,
        },
    )
    
    if not approved:
        return {
            "success": False,
            "message": "Operation denied by user",
            "denied": True,
        }
    
    try:
        if create_dirs:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        
        target_path.write_text(content, encoding="utf-8")
        return {"success": True, "message": f"File written: {path}"}
    except Exception as e:
        return {"success": False, "message": f"Failed to write file: {e}"}


async def delete_file(path: str) -> dict:
    """Delete a file from the Godot project.
    
    IMPORTANT: This tool requires HITL confirmation before execution.
    
    Args:
        path: File path relative to project root
        
    Returns:
        Result dictionary with success status and message
    """
    try:
        target_path = _validate_path_in_project(path)
    except ValueError as e:
        return {"success": False, "message": str(e)}
    
    if not target_path.exists():
        return {"success": False, "message": f"File not found: {path}"}
    
    if target_path.is_dir():
        return {"success": False, "message": f"'{path}' is a directory, not a file"}
    
    # Request HITL confirmation via Tauri
    approved = await _request_hitl_confirmation(
        action_type="delete_file",
        description=f"Delete file: {path}",
        details={"path": path},
    )
    
    if not approved:
        return {
            "success": False,
            "message": "Operation denied by user",
            "denied": True,
        }
    
    try:
        target_path.unlink()
        return {"success": True, "message": f"File deleted: {path}"}
    except Exception as e:
        return {"success": False, "message": f"Failed to delete file: {e}"}


async def file_exists(path: str) -> bool:
    """Check if a file or directory exists in the Godot project."""
    try:
        target_path = _validate_path_in_project(path)
        return target_path.exists()
    except ValueError:
        return False


async def create_directory(path: str) -> dict:
    """Create a new directory in the Godot project. Requires HITL confirmation."""
    from pathlib import Path
    
    try:
        target_path = _validate_path_in_project(path)
    except ValueError as e:
        return {"success": False, "message": str(e)}
    
    if target_path.exists():
        if target_path.is_dir():
            return {"success": True, "message": f"Directory already exists: {path}"}
        return {"success": False, "message": f"A file already exists at this path: {path}"}
    
    approved = await _request_hitl_confirmation(
        action_type="create_directory",
        description=f"Create directory: {path}",
        details={"path": path},
    )
    
    if not approved:
        return {"success": False, "message": "Operation denied by user", "denied": True}
    
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "message": f"Directory created: {path}"}
    except Exception as e:
        return {"success": False, "message": f"Failed to create directory: {e}"}


async def rename_file(old_path: str, new_name: str) -> dict:
    """Rename a file or directory in the Godot project. Requires HITL confirmation."""
    from pathlib import Path
    
    if _project_path is None:
        return {"success": False, "message": "No Godot project connected"}
    
    try:
        old_target = _validate_path_in_project(old_path)
    except ValueError as e:
        return {"success": False, "message": str(e)}
    
    if not old_target.exists():
        return {"success": False, "message": f"Path not found: {old_path}"}
    
    if "/" in new_name or "\\" in new_name:
        return {"success": False, "message": "new_name should be just a filename, not a path. Use move_file for moving."}
    
    new_target = old_target.parent / new_name
    project_root = Path(_project_path).resolve()
    
    try:
        new_target.relative_to(project_root)
    except ValueError:
        return {"success": False, "message": "New path would escape project directory"}
    
    if new_target.exists():
        return {"success": False, "message": f"Target already exists: {new_name}"}
    
    new_path_relative = str(new_target.relative_to(project_root))
    
    approved = await _request_hitl_confirmation(
        action_type="rename_file",
        description=f"Rename: {old_path} → {new_name}",
        details={"old_path": old_path, "new_path": new_path_relative, "new_name": new_name},
    )
    
    if not approved:
        return {"success": False, "message": "Operation denied by user", "denied": True}
    
    try:
        old_target.rename(new_target)
        return {"success": True, "message": f"Renamed: {old_path} → {new_path_relative}", "new_path": new_path_relative}
    except Exception as e:
        return {"success": False, "message": f"Failed to rename: {e}"}


async def move_file(source_path: str, destination_path: str) -> dict:
    """Move a file or directory to a new location in the Godot project. Requires HITL confirmation."""
    from pathlib import Path
    
    if _project_path is None:
        return {"success": False, "message": "No Godot project connected"}
    
    try:
        source = _validate_path_in_project(source_path)
    except ValueError as e:
        return {"success": False, "message": f"Invalid source path: {e}"}
    
    try:
        project_root = Path(_project_path).resolve()
        dest = (project_root / destination_path).resolve()
        dest.relative_to(project_root)
    except ValueError:
        return {"success": False, "message": "Destination path escapes project directory"}
    
    if not source.exists():
        return {"success": False, "message": f"Source not found: {source_path}"}
    
    if dest.exists():
        return {"success": False, "message": f"Destination already exists: {destination_path}"}
    
    approved = await _request_hitl_confirmation(
        action_type="move_file",
        description=f"Move: {source_path} → {destination_path}",
        details={"source_path": source_path, "destination_path": destination_path},
    )
    
    if not approved:
        return {"success": False, "message": "Operation denied by user", "denied": True}
    
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)
        return {"success": True, "message": f"Moved: {source_path} → {destination_path}"}
    except Exception as e:
        return {"success": False, "message": f"Failed to move: {e}"}


async def copy_file(source_path: str, destination_path: str) -> dict:
    """Copy a file to a new location in the Godot project. Requires HITL confirmation. Only works for files, not directories."""
    import shutil
    from pathlib import Path
    
    if _project_path is None:
        return {"success": False, "message": "No Godot project connected"}
    
    try:
        source = _validate_path_in_project(source_path)
    except ValueError as e:
        return {"success": False, "message": f"Invalid source path: {e}"}
    
    try:
        project_root = Path(_project_path).resolve()
        dest = (project_root / destination_path).resolve()
        dest.relative_to(project_root)
    except ValueError:
        return {"success": False, "message": "Destination path escapes project directory"}
    
    if not source.exists():
        return {"success": False, "message": f"Source not found: {source_path}"}
    
    if not source.is_file():
        return {"success": False, "message": f"Source must be a file, not a directory: {source_path}"}
    
    if dest.exists():
        return {"success": False, "message": f"Destination already exists: {destination_path}"}
    
    approved = await _request_hitl_confirmation(
        action_type="copy_file",
        description=f"Copy: {source_path} → {destination_path}",
        details={"source_path": source_path, "destination_path": destination_path},
    )
    
    if not approved:
        return {"success": False, "message": "Operation denied by user", "denied": True}
    
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return {"success": True, "message": f"Copied: {source_path} → {destination_path}"}
    except Exception as e:
        return {"success": False, "message": f"Failed to copy: {e}"}


# ============================================================================
# File Discovery Tools
# ============================================================================


async def find_files(
    pattern: str = "**/*.gd",
    max_results: int = 50,
) -> list[dict]:
    """Find files in the project matching a glob pattern.
    
    Use this tool to discover files before reading them. Supports recursive
    patterns like '**/*.gd' to find all GDScript files.
    
    Args:
        pattern: Glob pattern (e.g., '**/*.gd', '**/player*.gd', 'scripts/**/*.gd')
        max_results: Maximum number of files to return (default: 50)
        
    Returns:
        List of matching files with path, name, and size
    """
    from pathlib import Path
    
    if _project_path is None:
        return [{"error": "No Godot project connected"}]
    
    project_root = Path(_project_path).resolve()
    
    try:
        matches = list(project_root.glob(pattern))
        matches = [m for m in matches if m.is_file()]
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        if len(matches) > max_results:
            matches = matches[:max_results]
        
        return [
            {
                "path": str(m.relative_to(project_root)),
                "name": m.name,
                "size": m.stat().st_size,
            }
            for m in matches
        ]
    except Exception as e:
        return [{"error": f"Failed to find files: {e}"}]


async def search_project_files(
    pattern: str,
    file_pattern: str = "*.gd",
    max_results: int = 20,
    context_lines: int = 1,
) -> list[dict]:
    """Search project files for content matching a text pattern.
    
    Use this tool to find code by content (like grep). Useful for finding
    where a function is defined, where a signal is emitted, etc.
    
    Args:
        pattern: Text pattern to search for (case-insensitive)
        file_pattern: Glob pattern to filter files (e.g., '*.gd', '*.tscn')
        max_results: Maximum number of matching lines to return (default: 20)
        context_lines: Number of lines of context around each match (default: 1)
        
    Returns:
        List of matches with file path, line number, and matching content
    """
    import re
    from pathlib import Path
    
    if _project_path is None:
        return [{"error": "No Godot project connected"}]
    
    project_root = Path(_project_path).resolve()
    results: list[dict] = []
    
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)
    
    try:
        files = list(project_root.rglob(file_pattern))
        files = [f for f in files if f.is_file() and not str(f).startswith(str(project_root / ".godot"))]
        
        for file_path in files:
            if len(results) >= max_results:
                break
                
            try:
                content = file_path.read_text(encoding="utf-8")
                lines = content.splitlines()
                
                for i, line in enumerate(lines):
                    if len(results) >= max_results:
                        break
                        
                    if regex.search(line):
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        context = lines[start:end]
                        
                        results.append({
                            "file": str(file_path.relative_to(project_root)),
                            "line": i + 1,
                            "match": line.strip(),
                            "context": "\n".join(context),
                        })
            except (UnicodeDecodeError, IOError):
                continue
        
        return results if results else [{"message": f"No matches found for '{pattern}'"}]
        
    except Exception as e:
        return [{"error": f"Search failed: {e}"}]


# ============================================================================
# Project Context Tool
# ============================================================================


async def get_project_context(include_details: bool = True) -> str:
    """Get comprehensive context about the current Godot project.
    
    Returns information about:
    - Project settings (name, main scene, autoloads)
    - Scene hierarchy and node structure
    - Script dependencies and class relationships
    - Directory structure
    
    Use this tool when you need to understand the project structure
    before making changes or answering questions about the codebase.
    
    Args:
        include_details: If True, includes detailed script/scene analysis.
                        If False, returns just basic project info.
    
    Returns:
        Formatted string with project context, or error message if no project connected.
    """
    try:
        from app.agents.context import get_cached_context, format_context_for_agent
        
        ctx = await get_cached_context()
        if ctx is None:
            return "Error: No Godot project connected. Please connect a project from the Godot Editor."
        
        return format_context_for_agent(ctx)
    except Exception as e:
        return f"Error gathering project context: {e}"


# ============================================================================
# Exported tool list for agents
# ============================================================================

__all__ = [
    # Perception
    "request_screenshot",
    "get_scene_tree",
    "get_open_script",
    "get_project_settings",
    # Actuation
    "read_project_file",
    "write_project_file",
    "set_project_setting",
    "create_node",
    "delete_node",
    # Scoped file tools
    "list_project_files",
    "read_file",
    "write_file",
    "delete_file",
    "file_exists",
    "create_directory",
    "rename_file",
    "move_file",
    "copy_file",
    # File discovery
    "find_files",
    "search_project_files",
    # Knowledge & LSP
    "query_godot_docs",
    "get_symbol_info",
    "get_code_completions",
    # Project context
    "get_project_context",
    # Connection management
    "set_ws_connection",
    "get_ws_connection",
    "set_connection_manager",
    "get_connection_manager",
    "set_project_path",
    "get_project_path",
    "set_godot_version",
    "get_godot_version",
    "resolve_response",
    "clear_pending_requests",
]

