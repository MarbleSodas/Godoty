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


async def _request_hitl_confirmation(
    action_type: str,
    description: str,
    details: dict[str, Any],
) -> bool:
    """Request human-in-the-loop confirmation via Tauri UI.
    
    Args:
        action_type: Type of action ('write_file', 'delete_node', etc.)
        description: Human-readable description of the action
        details: Detailed information about the change (diff, paths, etc.)
    
    Returns:
        True if user approved, False otherwise
    """
    if _connection_manager is None:
        # No connection manager - deny for safety
        return False
    
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
    # Connection management
    "set_ws_connection",
    "get_ws_connection",
    "set_connection_manager",
    "get_connection_manager",
    "resolve_response",
]
