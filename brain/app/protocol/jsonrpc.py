from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JSONRPC_VERSION: Literal["2.0"] = "2.0"
PROTOCOL_VERSION = "0.1"


# ============================================================================
# Base JSON-RPC Models
# ============================================================================


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = JSONRPC_VERSION
    method: str
    params: dict[str, Any] | None = None
    id: int | str | None = None


class JsonRpcSuccess(BaseModel):
    jsonrpc: Literal["2.0"] = JSONRPC_VERSION
    result: Any
    id: int | str | None = None


class JsonRpcErrorPayload(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcError(BaseModel):
    jsonrpc: Literal["2.0"] = JSONRPC_VERSION
    error: JsonRpcErrorPayload
    id: int | str | None = None


# ============================================================================
# Handshake Messages
# ============================================================================


class GodotyHelloParams(BaseModel):
    client: Literal["godot"] | Literal["brain"]
    protocol_version: str = Field(default=PROTOCOL_VERSION)
    project_name: str | None = None
    godot_version: str | None = None


class GodotyHelloResult(BaseModel):
    ok: bool = True
    server: Literal["brain"] = "brain"
    protocol_version: str = Field(default=PROTOCOL_VERSION)


# ============================================================================
# User Message
# ============================================================================


class UserMessageParams(BaseModel):
    text: str


class UserMessageResult(BaseModel):
    text: str
    metrics: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Perception: Screenshots
# ============================================================================


class TakeScreenshotParams(BaseModel):
    """Parameters for requesting a screenshot from Godot."""

    viewport: Literal["3d", "2d", "editor"] = "3d"
    max_width: int = Field(default=1024, ge=64, le=4096)


class TakeScreenshotResult(BaseModel):
    """Result containing the screenshot image."""

    image: str  # Base64-encoded JPEG
    width: int
    height: int
    viewport: str


# ============================================================================
# Perception: Scene Tree
# ============================================================================


class GetSceneTreeParams(BaseModel):
    """Parameters for getting the scene tree."""

    max_depth: int = Field(default=10, ge=1, le=50)
    include_properties: bool = False


class SceneTreeNode(BaseModel):
    """A node in the scene tree."""

    name: str
    type: str
    path: str
    children: list["SceneTreeNode"] = Field(default_factory=list)
    properties: dict[str, Any] | None = None


class GetSceneTreeResult(BaseModel):
    """Result containing the scene tree structure."""

    tree: SceneTreeNode | None = None
    scene_path: str | None = None


# ============================================================================
# Perception: Script Introspection
# ============================================================================


class GetOpenScriptParams(BaseModel):
    """Parameters for getting the currently open script."""

    pass


class GetOpenScriptResult(BaseModel):
    """Result containing the open script info."""

    path: str
    content: str
    line_count: int
    cursor_line: int | None = None


# ============================================================================
# Perception: Project Settings
# ============================================================================


class GetProjectSettingsParams(BaseModel):
    """Parameters for getting project settings."""

    path: str | None = None  # Specific setting path, or None for common settings


class GetProjectSettingsResult(BaseModel):
    """Result containing project settings."""

    settings: dict[str, Any]


# ============================================================================
# Actuation: File Operations
# ============================================================================


class ReadFileParams(BaseModel):
    """Parameters for reading a project file."""

    path: str  # Relative to project root


class ReadFileResult(BaseModel):
    """Result containing file contents."""

    path: str
    content: str
    exists: bool = True


class WriteFileParams(BaseModel):
    """Parameters for writing a project file."""

    path: str
    content: str
    create_backup: bool = True
    requires_confirmation: bool = True


class WriteFileResult(BaseModel):
    """Result of file write operation."""

    success: bool
    message: str
    backup_path: str | None = None


# ============================================================================
# Actuation: Project Settings
# ============================================================================


class SetProjectSettingParams(BaseModel):
    """Parameters for setting a project setting."""

    path: str
    value: Any
    requires_confirmation: bool = True


class SetProjectSettingResult(BaseModel):
    """Result of setting change."""

    success: bool
    message: str


# ============================================================================
# Actuation: Scene Manipulation
# ============================================================================


class CreateNodeParams(BaseModel):
    """Parameters for creating a new node."""

    parent_path: str
    node_name: str
    node_type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True


class CreateNodeResult(BaseModel):
    """Result of node creation."""

    success: bool
    node_path: str | None = None
    message: str


class DeleteNodeParams(BaseModel):
    """Parameters for deleting a node."""

    node_path: str
    requires_confirmation: bool = True


class DeleteNodeResult(BaseModel):
    """Result of node deletion."""

    success: bool
    message: str


# ============================================================================
# HITL: Confirmation Workflow
# ============================================================================


class ConfirmationRequest(BaseModel):
    """Sent to Godot to request user confirmation."""

    confirmation_id: str
    action_type: Literal["write_file", "set_setting", "create_node", "delete_node"]
    description: str
    details: dict[str, Any]  # Action-specific details (diff, values, etc.)


class ConfirmationResponse(BaseModel):
    """Response from Godot after user decision."""

    confirmation_id: str
    approved: bool
    modified_content: str | None = None  # If user edited the proposed change


# ============================================================================
# Events (Godot -> Brain, no response expected)
# ============================================================================


class ConsoleErrorEvent(BaseModel):
    """Sent when an error appears in the Godot console."""

    jsonrpc: Literal["2.0"] = JSONRPC_VERSION
    method: Literal["console_error"] = "console_error"
    params: dict[str, Any]


class ConsoleErrorParams(BaseModel):
    """Parameters for console error event."""

    text: str
    type: Literal["error", "warning", "script_error"] = "error"
    script_path: str | None = None
    line: int | None = None


class SceneChangedEvent(BaseModel):
    """Sent when the active scene changes in the editor."""

    scene_path: str | None


class ScriptChangedEvent(BaseModel):
    """Sent when the open script changes."""

    script_path: str | None
