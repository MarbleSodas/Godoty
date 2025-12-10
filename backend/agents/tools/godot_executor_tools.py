"""
Godot Executor Tools for Agent Automation.

This module provides specialized tools for executor agents to perform
actions and make changes in Godot projects. These tools focus on
execution, modification, and automation capabilities.

Refactored to follow Strands best practices with hybrid approach:
- GodotExecutorTools class (no @tool decorators on methods)
- Wrapper functions with @tool decorators using shared instance
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Union, Tuple, AsyncIterable
from dataclasses import dataclass

from strands import tool, ToolContext
from .godot_bridge import get_godot_bridge, ensure_godot_connection, CommandResponse
from .godot_debug_tools import NodeInfo

logger = logging.getLogger(__name__)


# Error type constants
class ErrorType:
    """Error type constants for structured error responses."""
    CONNECTION_ERROR = "ConnectionError"
    VALIDATION_ERROR = "ValidationError"
    CREATION_ERROR = "CreationError"
    MODIFICATION_ERROR = "ModificationError"
    DELETION_ERROR = "DeletionError"
    OPERATION_ERROR = "OperationError"
    UNKNOWN_ERROR = "UnknownError"


class GodotExecutorTools:
    """
    Collection of execution and automation tools for Godot projects.

    These tools are designed for executor agents to perform actions
    and make modifications to Godot projects.

    All tools return Strands-compatible dictionaries with the format:
    {
        "status": "success" | "error",
        "content": [{"text": "..."}],
        "data": {...}  # Optional additional data
    }

    Error responses include:
    {
        "status": "error",
        "error_type": "...",
        "content": [{"text": "..."}],
        "suggestions": [...]  # Optional recovery suggestions
    }
    """

    def __init__(self):
        """Initialize executor tools with Godot bridge connection."""
        self.bridge = get_godot_bridge()
        logger.info("🔧 GodotExecutorTools initialized")

    async def ensure_connection(self) -> bool:
        """Ensure connection to Godot is active."""
        logger.info("🔍 Checking Godot connection status...")
        connected = await ensure_godot_connection()
        if connected:
            logger.info("✓ Godot connection verified and ready")
        else:
            logger.error("❌ Failed to establish Godot connection")
        return connected

    def _create_success_response(
        self,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a standardized success response."""
        response = {
            "status": "success",
            "content": [{"text": message}]
        }
        if data:
            response["data"] = data
        return response

    def _create_error_response(
        self,
        message: str,
        error_type: str = ErrorType.UNKNOWN_ERROR,
        suggestions: Optional[List[str]] = None,
        retry_after: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a standardized error response."""
        response = {
            "status": "error",
            "error_type": error_type,
            "content": [{"text": message}]
        }
        if suggestions:
            response["suggestions"] = suggestions
        if retry_after:
            response["retry_after"] = retry_after
        return response

    # Node Creation and Management
    async def create_node(
        self,
        node_type: str,
        parent_path: str,
        node_name: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Create a new node in the Godot scene tree."""
        if not await self.ensure_connection():
            return self._create_error_response(
                "Failed to connect to Godot plugin",
                error_type=ErrorType.CONNECTION_ERROR,
                suggestions=[
                    "Ensure Godot editor is running",
                    "Verify Godoty plugin is active",
                    "Check WebSocket connection settings"
                ],
                retry_after=5
            )

        try:
            params = {
                "type": node_type,
                "parent": parent_path
            }
            if node_name:
                params["name"] = node_name
            if properties:
                params["properties"] = properties

            response = await self.bridge.send_command("create_node", **params)

            if response.success:
                created_path = response.data.get("path")
                node_id = response.data.get("id")

                # Record in agent state if context available
                if tool_context:
                    try:
                        state = tool_context.agent.state
                        if hasattr(state, "get"):
                            try:
                                operation_history = state.get("operation_history") or []
                            except TypeError:
                                operation_history = state.get("operation_history")
                                if operation_history is None:
                                    operation_history = []
                        else:
                            operation_history = []

                        operation_history.append({
                            "type": "create_node",
                            "target": created_path,
                            "result": True,
                            "timestamp": time.time(),
                            "details": params
                        })
                        state.set("operation_history", operation_history)
                    except Exception as e:
                        logger.warning(f"Failed to update agent state: {e}")

                logger.info(f"Created node {node_type} at {created_path}")

                return self._create_success_response(
                    f"Successfully created {node_type} node at {created_path}",
                    data={
                        "created_path": created_path,
                        "node_id": node_id,
                        "node_type": node_type
                    }
                )
            else:
                error_msg = response.error or "Unknown error"
                logger.error(f"Failed to create node: {error_msg}")

                return self._create_error_response(
                    f"Failed to create node: {error_msg}",
                    error_type=ErrorType.CREATION_ERROR,
                    suggestions=[
                        "Verify parent path exists",
                        f"Check that '{node_type}' is a valid Godot node type",
                        "Ensure parent node can have children"
                    ]
                )

        except ConnectionError as e:
            return self._create_error_response(
                f"Connection to Godot failed: {str(e)}",
                error_type=ErrorType.CONNECTION_ERROR,
                suggestions=[
                    "Check Godot editor is running",
                    "Verify WebSocket plugin is active"
                ],
                retry_after=5
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error creating node: {error_msg}")
            return self._create_error_response(
                f"Unexpected error creating node: {error_msg}",
                error_type=ErrorType.UNKNOWN_ERROR
            )

    async def delete_node(
        self,
        node_path: str,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Delete a node from the Godot scene tree."""
        if not await self.ensure_connection():
            return self._create_error_response(
                "Failed to connect to Godot plugin",
                error_type=ErrorType.CONNECTION_ERROR,
                retry_after=5
            )

        try:
            response = await self.bridge.send_command("delete_node", path=node_path)

            if response.success:
                if tool_context:
                    try:
                        state = tool_context.agent.state
                        if hasattr(state, "get"):
                            try:
                                operation_history = state.get("operation_history") or []
                            except TypeError:
                                operation_history = state.get("operation_history")
                                if operation_history is None:
                                    operation_history = []
                        else:
                            operation_history = []

                        operation_history.append({
                            "type": "delete_node",
                            "target": node_path,
                            "result": True,
                            "timestamp": time.time()
                        })
                        state.set("operation_history", operation_history)
                    except Exception as e:
                        logger.warning(f"Failed to update agent state: {e}")

                logger.info(f"Deleted node at {node_path}")
                return self._create_success_response(
                    f"Successfully deleted node at {node_path}",
                    data={"deleted_path": node_path}
                )
            else:
                error_msg = response.error or "Unknown error"
                logger.error(f"Failed to delete node: {error_msg}")

                return self._create_error_response(
                    f"Failed to delete node: {error_msg}",
                    error_type=ErrorType.DELETION_ERROR,
                    suggestions=[
                        f"Verify node exists at path: {node_path}",
                        "Ensure node is not protected or locked"
                    ]
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error deleting node: {error_msg}")
            return self._create_error_response(
                f"Error deleting node: {error_msg}",
                error_type=ErrorType.OPERATION_ERROR
            )

    async def modify_node_property(
        self,
        node_path: str,
        property_name: str,
        new_value: Any,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Modify a property of a node in the Godot scene tree."""
        if not await self.ensure_connection():
            return self._create_error_response(
                "Failed to connect to Godot plugin",
                error_type=ErrorType.CONNECTION_ERROR,
                retry_after=5
            )

        try:
            response = await self.bridge.send_command(
                "modify_node",
                path=node_path,
                properties={property_name: new_value}
            )

            if response.success:
                old_value = response.data.get("old_value")

                if tool_context:
                    try:
                        state = tool_context.agent.state
                        if hasattr(state, "get"):
                            try:
                                operation_history = state.get("operation_history") or []
                            except TypeError:
                                operation_history = state.get("operation_history")
                                if operation_history is None:
                                    operation_history = []
                        else:
                            operation_history = []

                        operation_history.append({
                            "type": "modify_property",
                            "target": node_path,
                            "result": True,
                            "timestamp": time.time(),
                            "details": {
                                "property": property_name,
                                "old_value": old_value,
                                "new_value": new_value
                            }
                        })
                        state.set("operation_history", operation_history)
                    except Exception as e:
                        logger.warning(f"Failed to update agent state: {e}")

                logger.info(f"Modified {property_name} on {node_path} from {old_value} to {new_value}")

                return self._create_success_response(
                    f"Successfully modified {property_name} on {node_path}",
                    data={
                        "modified_path": node_path,
                        "property": property_name,
                        "old_value": old_value,
                        "new_value": new_value
                    }
                )
            else:
                error_msg = response.error or "Unknown error"
                logger.error(f"Failed to modify property: {error_msg}")

                return self._create_error_response(
                    f"Failed to modify property: {error_msg}",
                    error_type=ErrorType.MODIFICATION_ERROR,
                    suggestions=[
                        f"Verify node exists at path: {node_path}",
                        f"Check that '{property_name}' is a valid property for this node",
                        "Ensure the new value type matches the property type"
                    ]
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error modifying property: {error_msg}")
            return self._create_error_response(
                f"Error modifying property: {error_msg}",
                error_type=ErrorType.OPERATION_ERROR
            )

    async def create_new_scene(
        self,
        scene_name: str,
        root_node_type: str = "Node",
        save_path: Optional[str] = None,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Create a new scene in the Godot project."""
        if not await self.ensure_connection():
            return self._create_error_response(
                "Failed to connect to Godot plugin",
                error_type=ErrorType.CONNECTION_ERROR,
                retry_after=5
            )

        try:
            params = {
                "name": scene_name,
                "root_type": root_node_type
            }
            if save_path:
                if not self.bridge.is_path_safe(save_path):
                    return self._create_error_response(
                        f"Save path '{save_path}' is outside the project directory",
                        error_type=ErrorType.VALIDATION_ERROR
                    )
                params["save_path"] = save_path

            response = await self.bridge.send_command("create_scene", **params)

            if response.success:
                scene_path = response.data.get("scene_path")

                if tool_context:
                    try:
                        state = tool_context.agent.state
                        if hasattr(state, "get"):
                            try:
                                operation_history = state.get("operation_history") or []
                            except TypeError:
                                operation_history = state.get("operation_history")
                                if operation_history is None:
                                    operation_history = []
                        else:
                            operation_history = []

                        operation_history.append({
                            "type": "create_scene",
                            "target": scene_name,
                            "result": True,
                            "timestamp": time.time(),
                            "details": params
                        })
                        state.set("operation_history", operation_history)
                        state.set("active_scene", scene_path)
                    except Exception as e:
                        logger.warning(f"Failed to update agent state: {e}")

                logger.info(f"Created new scene: {scene_path}")

                return self._create_success_response(
                    f"Successfully created scene: {scene_path}",
                    data={
                        "scene_path": scene_path,
                        "scene_name": scene_name,
                        "root_node_type": root_node_type
                    }
                )
            else:
                error_msg = response.error or "Unknown error"
                logger.error(f"Failed to create scene: {error_msg}")

                return self._create_error_response(
                    f"Failed to create scene: {error_msg}",
                    error_type=ErrorType.CREATION_ERROR,
                    suggestions=[
                        f"Check that '{root_node_type}' is a valid Godot node type",
                        "Verify save path is writable",
                        "Ensure scene name is valid"
                    ]
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error creating scene: {error_msg}")
            return self._create_error_response(
                f"Error creating scene: {error_msg}",
                error_type=ErrorType.OPERATION_ERROR
            )

    async def open_scene(
        self,
        scene_path: str,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Open a scene in the Godot editor."""
        if not await self.ensure_connection():
            return self._create_error_response(
                "Failed to connect to Godot plugin",
                error_type=ErrorType.CONNECTION_ERROR,
                retry_after=5
            )

        try:
            response = await self.bridge.send_command("open_scene", path=scene_path)

            if response.success:
                if tool_context:
                    try:
                        state = tool_context.agent.state
                        state.set("active_scene", scene_path)
                        
                        if hasattr(state, "get"):
                            try:
                                operation_history = state.get("operation_history") or []
                            except TypeError:
                                operation_history = state.get("operation_history")
                                if operation_history is None:
                                    operation_history = []
                        else:
                            operation_history = []

                        operation_history.append({
                            "type": "open_scene",
                            "target": scene_path,
                            "result": True,
                            "timestamp": time.time()
                        })
                        state.set("operation_history", operation_history)
                    except Exception as e:
                        logger.warning(f"Failed to update agent state: {e}")

                logger.info(f"Opened scene: {scene_path}")
                return self._create_success_response(
                    f"Successfully opened scene: {scene_path}",
                    data={"scene_path": scene_path}
                )
            else:
                error_msg = response.error or "Unknown error"
                logger.error(f"Failed to open scene: {error_msg}")

                return self._create_error_response(
                    f"Failed to open scene: {error_msg}",
                    error_type=ErrorType.OPERATION_ERROR,
                    suggestions=[
                        f"Verify scene file exists at: {scene_path}",
                        "Ensure scene file is not corrupted",
                        "Check file permissions"
                    ]
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error opening scene: {error_msg}")
            return self._create_error_response(
                f"Error opening scene: {error_msg}",
                error_type=ErrorType.OPERATION_ERROR
            )

    async def save_current_scene(
        self,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Save the currently active scene in the Godot editor."""
        if not await self.ensure_connection():
            return self._create_error_response(
                "Failed to connect to Godot plugin",
                error_type=ErrorType.CONNECTION_ERROR,
                retry_after=5
            )

        try:
            response = await self.bridge.send_command("save_current_scene")

            if response.success:
                saved_path = response.data.get("scene_path", "current scene")

                if tool_context:
                    try:
                        state = tool_context.agent.state
                        if hasattr(state, "get"):
                            try:
                                operation_history = state.get("operation_history") or []
                            except TypeError:
                                operation_history = state.get("operation_history")
                                if operation_history is None:
                                    operation_history = []
                        else:
                            operation_history = []

                        operation_history.append({
                            "type": "save_scene",
                            "target": saved_path,
                            "result": True,
                            "timestamp": time.time()
                        })
                        state.set("operation_history", operation_history)
                    except Exception as e:
                        logger.warning(f"Failed to update agent state: {e}")

                logger.info(f"Saved scene: {saved_path}")
                return self._create_success_response(
                    f"Successfully saved {saved_path}",
                    data={"scene_path": saved_path}
                )
            else:
                error_msg = response.error or "Unknown error"
                logger.error(f"Failed to save scene: {error_msg}")

                return self._create_error_response(
                    f"Failed to save scene: {error_msg}",
                    error_type=ErrorType.OPERATION_ERROR,
                    suggestions=[
                        "Ensure a scene is currently open",
                        "Check file permissions for scene file",
                        "Verify disk space is available"
                    ]
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error saving scene: {error_msg}")
            return self._create_error_response(
                f"Error saving scene: {error_msg}",
                error_type=ErrorType.OPERATION_ERROR
            )

    # Additional methods kept for completeness
    async def select_nodes(self, node_paths: List[str], tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Select nodes in the Godot editor."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command("select_nodes", paths=node_paths)
            if response.success:
                return self._create_success_response(f"Successfully selected {len(node_paths)} node(s)", data={"selected_nodes": node_paths})
            else:
                return self._create_error_response(f"Failed to select nodes: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error selecting nodes: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def play_scene(self, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Start playing the current scene in Godot."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command("play", mode="current")
            if response.success:
                return self._create_success_response("Successfully started playing scene")
            else:
                return self._create_error_response(f"Failed to play scene: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error playing scene: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def stop_playing(self, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Stop playing the current scene in Godot."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command("stop_playing")
            if response.success:
                return self._create_success_response("Successfully stopped playing scene")
            else:
                return self._create_error_response(f"Failed to stop playing: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error stopping playing: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def reparent_node(self, node_path: str, new_parent_path: str, new_position: Optional[int] = None, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Move a node to a new parent in the scene tree."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            params = {"path": node_path, "new_parent_path": new_parent_path}
            if new_position is not None:
                params["index"] = new_position
            response = await self.bridge.send_command("reparent_node", **params)
            if response.success:
                return self._create_success_response(f"Successfully moved {node_path} to {new_parent_path}", data={"node_path": node_path, "new_parent_path": new_parent_path, "position": new_position})
            else:
                return self._create_error_response(f"Failed to reparent node: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error reparenting node: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def attach_script(
        self,
        node_path: str,
        script_content: str,
        script_path: Optional[str] = None,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Attach a GDScript to a node."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            params = {
                "path": node_path,
                "script_content": script_content
            }
            if script_path:
                params["script_path"] = script_path

            response = await self.bridge.send_command("attach_script", **params)

            if response.success:
                if tool_context:
                    try:
                        state = tool_context.agent.state
                        if hasattr(state, "get"):
                            try:
                                operation_history = state.get("operation_history") or []
                            except TypeError:
                                operation_history = state.get("operation_history")
                                if operation_history is None:
                                    operation_history = []
                        else:
                            operation_history = []

                        operation_history.append({
                            "type": "attach_script",
                            "target": node_path,
                            "result": True,
                            "timestamp": time.time(),
                            "details": {"script_path": script_path}
                        })
                        state.set("operation_history", operation_history)
                    except Exception as e:
                        logger.warning(f"Failed to update agent state: {e}")
                
                return self._create_success_response(f"Successfully attached script to {node_path}", data=response.data)
            else:
                return self._create_error_response(f"Failed to attach script: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
             return self._create_error_response(f"Error attaching script: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    # === New EditorInterface Commands (expanded editor access) ===

    async def close_scene(self, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Close the currently active scene in the editor."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command("close_scene")
            if response.success:
                logger.info("Closed current scene")
                return self._create_success_response("Successfully closed the current scene")
            else:
                return self._create_error_response(f"Failed to close scene: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error closing scene: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def edit_script(
        self,
        script_path: str,
        line: int = -1,
        column: int = 0,
        grab_focus: bool = True,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Open a script in the script editor at a specific line and column."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command(
                "edit_script",
                path=script_path,
                line=line,
                column=column,
                grab_focus=grab_focus
            )
            if response.success:
                logger.info(f"Opened script {script_path} at line {line}")
                return self._create_success_response(
                    f"Successfully opened script at line {line}",
                    data={"path": script_path, "line": line, "column": column}
                )
            else:
                return self._create_error_response(
                    f"Failed to open script: {response.error or 'Unknown error'}",
                    error_type=ErrorType.OPERATION_ERROR,
                    suggestions=["Verify script path exists", "Check that it's a valid GDScript file"]
                )
        except Exception as e:
            return self._create_error_response(f"Error opening script: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def save_scene_as(
        self,
        save_path: str,
        with_preview: bool = True,
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """Save the current scene to a specific path."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            if not self.bridge.is_path_safe(save_path):
                return self._create_error_response(
                    f"Save path '{save_path}' is outside the project directory",
                    error_type=ErrorType.VALIDATION_ERROR
                )
            response = await self.bridge.send_command("save_scene_as", path=save_path, with_preview=with_preview)
            if response.success:
                logger.info(f"Saved scene as {save_path}")
                return self._create_success_response(f"Successfully saved scene as {save_path}", data={"path": save_path})
            else:
                return self._create_error_response(f"Failed to save scene: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error saving scene: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def save_all_scenes(self, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Save all open scenes in the editor."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command("save_all_scenes")
            if response.success:
                logger.info("Saved all scenes")
                return self._create_success_response("Successfully saved all open scenes")
            else:
                return self._create_error_response(f"Failed to save all scenes: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error saving all scenes: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def reload_scene(self, scene_path: str, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Reload a scene from disk."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command("reload_scene", path=scene_path)
            if response.success:
                logger.info(f"Reloaded scene {scene_path}")
                return self._create_success_response(f"Successfully reloaded scene {scene_path}", data={"path": scene_path})
            else:
                return self._create_error_response(f"Failed to reload scene: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error reloading scene: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def switch_main_screen(self, screen: str, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Switch between editor screens (2D, 3D, Script, AssetLib)."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            valid_screens = ["2D", "3D", "Script", "AssetLib"]
            if screen not in valid_screens:
                return self._create_error_response(
                    f"Invalid screen name: {screen}. Valid options: {', '.join(valid_screens)}",
                    error_type=ErrorType.VALIDATION_ERROR
                )
            response = await self.bridge.send_command("switch_main_screen", screen=screen)
            if response.success:
                logger.info(f"Switched to {screen} screen")
                return self._create_success_response(f"Successfully switched to {screen} screen", data={"screen": screen})
            else:
                return self._create_error_response(f"Failed to switch screen: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error switching screen: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def get_open_scenes(self, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Get list of currently open scenes in the editor."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command("get_open_scenes")
            if response.success:
                scenes = response.data.get("scenes", [])
                count = len(scenes)
                logger.info(f"Found {count} open scenes")
                return self._create_success_response(f"Found {count} open scene(s)", data={"scenes": scenes, "count": count})
            else:
                return self._create_error_response(f"Failed to get open scenes: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error getting open scenes: {str(e)}", error_type=ErrorType.OPERATION_ERROR)

    async def scan_filesystem(self, tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
        """Trigger a filesystem scan to detect new or changed files."""
        if not await self.ensure_connection():
            return self._create_error_response("Failed to connect to Godot plugin", error_type=ErrorType.CONNECTION_ERROR, retry_after=5)
        try:
            response = await self.bridge.send_command("scan_filesystem")
            if response.success:
                logger.info("Started filesystem scan")
                return self._create_success_response("Successfully started filesystem scan")
            else:
                return self._create_error_response(f"Failed to scan filesystem: {response.error or 'Unknown error'}", error_type=ErrorType.OPERATION_ERROR)
        except Exception as e:
            return self._create_error_response(f"Error scanning filesystem: {str(e)}", error_type=ErrorType.OPERATION_ERROR)



# ============================================================================
# Global Shared Instance
# ============================================================================

_godot_executor_tools_instance = None


def get_godot_executor_tools() -> GodotExecutorTools:
    """Get or create the shared GodotExecutorTools instance."""
    global _godot_executor_tools_instance
    if _godot_executor_tools_instance is None:
        _godot_executor_tools_instance = GodotExecutorTools()
    return _godot_executor_tools_instance


# ============================================================================
# Tool Wrapper Functions (Top Essential Tools for Start Menu Creation)
# ============================================================================

@tool(context="tool_context")
async def create_node(
    node_type: str,
    parent_path: str,
    node_name: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Create a new node in the Godot scene tree.

    Args:
        node_type: Type of node to create (e.g., 'Node2D', 'Sprite2D', 'Camera2D') (Required)
        parent_path: Path to parent node where the new node will be added (Required)
        node_name: Name for the new node (optional)
        properties: Initial properties to set (optional)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await create_node(
            node_type="Sprite2D",
            parent_path="Root/Player",
            node_name="WeaponSprite",
            properties={"position": {"x": 10, "y": 0}}
        )
    """
    logger.info(f"🛠️ TOOL CALL: create_node(node_type='{node_type}', parent_path='{parent_path}', node_name='{node_name}', properties={properties})")
    
    if not node_type or not parent_path:
         # This check is technically redundant if types are enforced, but kept for safety
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{
                "text": "Both 'node_type' and 'parent_path' are REQUIRED parameters. Please provide them (e.g., node_type='Node2D', parent_path='/root/Main')."
            }]
        }

    tools = get_godot_executor_tools()
    return await tools.create_node(node_type, parent_path, node_name, properties, tool_context)


@tool(context="tool_context")
async def delete_node(
    node_path: str,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Delete a node from the Godot scene tree.

    Args:
        node_path: Path to the node to delete (e.g., "Root/Player/Sprite") (Required)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await delete_node(node_path="Root/Player/OldWeapon")
    """
    logger.info(f"🛠️ TOOL CALL: delete_node(node_path='{node_path}')")
    
    if not node_path:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{"text": "The 'node_path' parameter is REQUIRED. Please specify which node to delete."}]
        }

    tools = get_godot_executor_tools()
    return await tools.delete_node(node_path, tool_context)


@tool(context="tool_context")
async def modify_node_property(
    node_path: str,
    property_name: str,
    new_value: Any,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Modify a property of a node in the Godot scene tree.

    Args:
        node_path: Path to the node whose property will be modified (Required)
        property_name: Name of the property to modify (Required)
        new_value: New value for the property (Required)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await modify_node_property(
            node_path="Root/Player",
            property_name="position",
            new_value={"x": 100, "y": 200}
        )
    """
    logger.info(f"🛠️ TOOL CALL: modify_node_property(node_path='{node_path}', property_name='{property_name}', new_value={new_value})")
    
    if not node_path or not property_name:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{
                "text": "Parameters 'node_path', 'property_name', and 'new_value' are all REQUIRED. Please provide them."
            }]
        }

    tools = get_godot_executor_tools()
    return await tools.modify_node_property(node_path, property_name, new_value, tool_context)


@tool(context="tool_context")
async def create_scene(
    scene_name: str,
    root_node_type: str = "Node",
    save_path: Optional[str] = None,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Create a new scene in the Godot project.

    Args:
        scene_name: Name for the new scene (Required)
        root_node_type: Type of root node (default: "Node")
        save_path: Path to save the scene (optional)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await create_scene(
            scene_name="MainMenu",
            root_node_type="Control",
            save_path="res://scenes/main_menu.tscn"
        )
    """
    logger.info(f"🛠️ TOOL CALL: create_scene(scene_name='{scene_name}', root_node_type='{root_node_type}', save_path='{save_path}')")
    
    if not scene_name:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{
                "text": "The 'scene_name' parameter is REQUIRED. You must provide a name for the scene (e.g., 'MainMenu', 'GameLevel'). Please retry with a valid 'scene_name'."
            }]
        }

    tools = get_godot_executor_tools()
    return await tools.create_new_scene(scene_name, root_node_type, save_path, tool_context)


@tool(context="tool_context")
async def open_scene(
    scene_path: str,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Open a scene in the Godot editor.

    Args:
        scene_path: Path to the .tscn file to open (Required)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await open_scene(scene_path="res://scenes/level_01.tscn")
    """
    if not scene_path:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{"text": "The 'scene_path' parameter is REQUIRED. Please specify which scene file to open."}]
        }

    tools = get_godot_executor_tools()
    return await tools.open_scene(scene_path, tool_context)


@tool(context="tool_context")
async def save_current_scene(
    tool_context: Any = None
) -> Dict[str, Any]:
    """Save the currently active scene in the Godot editor.

    Args:
    Returns:
        Strands-compatible dictionary with operation outcome
    """
    tools = get_godot_executor_tools()
    return await tools.save_current_scene(tool_context)


@tool(context="tool_context")
async def select_nodes(
    node_paths: List[str],
    tool_context: Any = None
) -> Dict[str, Any]:
    """Select nodes in the Godot editor.

    Args:
        node_paths: List of node paths to select (Required)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await select_nodes(node_paths=["Root/Player", "Root/Enemy"])
    """
    if not node_paths:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{"text": "The 'node_paths' parameter is REQUIRED. Please provide a list of node paths to select."}]
        }

    tools = get_godot_executor_tools()
    return await tools.select_nodes(node_paths, tool_context)


@tool(context="tool_context")
async def play_scene(
    tool_context: Any = None
) -> Dict[str, Any]:
    """Start playing the current scene in Godot.

    Args:
    Returns:
        Strands-compatible dictionary with operation outcome
    """
    tools = get_godot_executor_tools()
    return await tools.play_scene(tool_context)


@tool(context="tool_context")
async def stop_playing(
    tool_context: Any = None
) -> Dict[str, Any]:
    """Stop playing the current scene in Godot.

    Args:
    Returns:
        Strands-compatible dictionary with operation outcome
    """
    tools = get_godot_executor_tools()
    return await tools.stop_playing(tool_context)


@tool(context="tool_context")
async def reparent_node(
    node_path: str,
    new_parent_path: str,
    new_position: Optional[int] = None,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Move a node to a new parent in the scene tree.

    Args:
        node_path: Path to the node to move (Required)
        new_parent_path: Path to the new parent node (Required)
        new_position: Position in new parent's children (optional)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await reparent_node(
            node_path="Root/TempItem",
            new_parent_path="Root/Inventory",
            new_position=0
        )
    """
    if not node_path or not new_parent_path:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{
                "text": "Both 'node_path' and 'new_parent_path' are REQUIRED parameters. Please specify which node to move and where."
            }]
        }

    tools = get_godot_executor_tools()
    return await tools.reparent_node(node_path, new_parent_path, new_position, tool_context)


@tool(context="tool_context")
async def attach_script(
    node_path: str,
    script_content: str,
    script_path: Optional[str] = None,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Attach a GDScript to a node.

    Args:
        node_path: Path to the node to attach the script to (Required)
        script_content: The content of the GDScript (Required)
        script_path: Optional path to save the script file (e.g., "res://scripts/my_script.gd")
    Returns:
        Strands-compatible dictionary with operation outcome
    """
    if not node_path or not script_content:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{"text": "Both 'node_path' and 'script_content' are REQUIRED parameters."}]
        }

    tools = get_godot_executor_tools()
    return await tools.attach_script(node_path, script_content, script_path, tool_context)


# ============================================================================
# New EditorInterface Tool Wrapper Functions
# ============================================================================

@tool(context="tool_context")
async def close_scene(tool_context: Any = None) -> Dict[str, Any]:
    """Close the currently active scene in the editor.

    Returns:
        Strands-compatible dictionary with operation outcome
    """
    tools = get_godot_executor_tools()
    return await tools.close_scene(tool_context)


@tool(context="tool_context")
async def edit_script(
    script_path: str,
    line: int = -1,
    column: int = 0,
    grab_focus: bool = True,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Open a script in the script editor at a specific line.

    Args:
        script_path: Path to the script file (e.g., "res://scripts/player.gd") (Required)
        line: Line number to jump to (-1 for beginning)
        column: Column position (default 0)
        grab_focus: Whether to focus the script editor (default True)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await edit_script(script_path="res://scripts/player.gd", line=50)
    """
    if not script_path:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{"text": "The 'script_path' parameter is REQUIRED."}]
        }
    tools = get_godot_executor_tools()
    return await tools.edit_script(script_path, line, column, grab_focus, tool_context)


@tool(context="tool_context")
async def save_scene_as(
    save_path: str,
    with_preview: bool = True,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Save the current scene to a specific path.

    Args:
        save_path: Path to save the scene (e.g., "res://scenes/level2.tscn") (Required)
        with_preview: Whether to include a preview image (default True)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await save_scene_as(save_path="res://scenes/main_menu.tscn")
    """
    if not save_path:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{"text": "The 'save_path' parameter is REQUIRED."}]
        }
    tools = get_godot_executor_tools()
    return await tools.save_scene_as(save_path, with_preview, tool_context)


@tool(context="tool_context")
async def save_all_scenes(tool_context: Any = None) -> Dict[str, Any]:
    """Save all open scenes in the editor.

    Returns:
        Strands-compatible dictionary with operation outcome
    """
    tools = get_godot_executor_tools()
    return await tools.save_all_scenes(tool_context)


@tool(context="tool_context")
async def reload_scene(
    scene_path: str,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Reload a scene from disk, discarding any unsaved changes.

    Args:
        scene_path: Path to the scene to reload (e.g., "res://scenes/main.tscn") (Required)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await reload_scene(scene_path="res://scenes/level.tscn")
    """
    if not scene_path:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{"text": "The 'scene_path' parameter is REQUIRED."}]
        }
    tools = get_godot_executor_tools()
    return await tools.reload_scene(scene_path, tool_context)


@tool(context="tool_context")
async def switch_main_screen(
    screen: str,
    tool_context: Any = None
) -> Dict[str, Any]:
    """Switch between editor main screens.

    Args:
        screen: Screen name to switch to. Valid options: "2D", "3D", "Script", "AssetLib" (Required)
    Returns:
        Strands-compatible dictionary with operation outcome

    Example:
        await switch_main_screen(screen="Script")
    """
    if not screen:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "content": [{"text": "The 'screen' parameter is REQUIRED. Valid options: 2D, 3D, Script, AssetLib"}]
        }
    tools = get_godot_executor_tools()
    return await tools.switch_main_screen(screen, tool_context)


@tool(context="tool_context")
async def get_open_scenes(tool_context: Any = None) -> Dict[str, Any]:
    """Get list of currently open scenes in the editor.

    Returns:
        Strands-compatible dictionary with list of open scene paths
    """
    tools = get_godot_executor_tools()
    return await tools.get_open_scenes(tool_context)


@tool(context="tool_context")
async def scan_filesystem(tool_context: Any = None) -> Dict[str, Any]:
    """Trigger a filesystem scan to detect new or changed files.

    This is useful after creating files externally or when the editor
    hasn't picked up recent changes automatically.

    Returns:
        Strands-compatible dictionary with operation outcome
    """
    tools = get_godot_executor_tools()
    return await tools.scan_filesystem(tool_context)