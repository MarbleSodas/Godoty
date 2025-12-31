# Godoty JSON-RPC Protocol

- **Transport:** WebSocket
- **Envelope:** JSON-RPC 2.0
- **Protocol Version:** `0.2`
- **Endpoints:**
  - Godot: `ws://127.0.0.1:8000/ws/godot`
  - Tauri: `ws://127.0.0.1:8000/ws/tauri`
  - Legacy: `ws://127.0.0.1:8000/ws` (routes to Godot)

## Overview

The Godoty protocol enables bidirectional communication between:
- **Godot Editor plugin** - Handles perception (screenshots, scene tree) and actuation (file writes, node creation)
- **Tauri Desktop App** - Handles UI, chat, authentication, and HITL confirmations
- **Python Brain** - Orchestrates AI agents, routes messages, manages connections

All messages follow JSON-RPC 2.0 format.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Tauri App      │     │  Python Brain   │     │  Godot Editor   │
│  (UI + Auth)    │◄───►│  (Orchestrator) │◄───►│  (Perception)   │
│  /ws/tauri      │     │                 │     │  /ws/godot      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  LiteLLM Proxy  │
                        │  (Remote/Cloud) │
                        └─────────────────┘
```

## Message Types

1. **Requests:** Have an `id` field and expect a response
2. **Responses:** Have `result` or `error` field with matching `id`
3. **Events:** Have `method` but no `id`, no response expected

---

## Handshake

### `hello` (Godot)

Initial handshake when Godot connects to the brain.

**Request params:**
```json
{
  "client": "godot",
  "protocol_version": "0.2",
  "project_name": "My Game",
  "project_path": "/Users/dev/MyGame",
  "godot_version": "4.3"
}
```

**Response result:**
```json
{
  "client": "godot",
  "session_id": "uuid-string",
  "protocol_version": "0.2"
}
```

### `hello` (Tauri)

Initial handshake when Tauri connects to the brain.

**Request params:**
```json
{
  "client": "tauri",
  "protocol_version": "0.2"
}
```

**Response result:**
```json
{
  "session_id": "uuid-string",
  "protocol_version": "0.2",
  "godot_connected": true
}
```

---

## User Interaction (Tauri → Brain)

### `user_message`

Send a user message to the agent team.

**Request params:**
```json
{
  "text": "How do I implement a double jump?",
  "authorization": "Bearer eyJ..."  // Optional Supabase JWT
}
```

**Response result:**
```json
{
  "text": "To implement a double jump in Godot 4...",
  "metrics": {
    "input_tokens": 150,
    "output_tokens": 420,
    "session_total_tokens": 1250
  }
}
```

---

## Notifications (Brain → Tauri)

### `godot_connected`

Sent when Godot connects to the brain.

**Params:**
```json
{
  "project": {
    "name": "My Game",
    "path": "/Users/dev/MyGame",
    "godotVersion": "4.3"
  }
}
```

### `godot_disconnected`

Sent when Godot disconnects.

**Params:** `{}`

### `token_update`

Sent after processing a user message with token count.

**Params:**
```json
{
  "total": 1250
}
```

---

## Perception Methods (Brain → Godot)

### `take_screenshot`

Capture a screenshot from the editor.

**Request params:**
```json
{
  "viewport": "3d",  // "3d", "2d", or "editor"
  "max_width": 1024
}
```

**Response result:**
```json
{
  "image": "base64-encoded-jpeg...",
  "width": 1024,
  "height": 576,
  "viewport": "3d"
}
```

### `get_scene_tree`

Get the structure of the currently edited scene.

**Request params:**
```json
{
  "max_depth": 10,
  "include_properties": false
}
```

**Response result:**
```json
{
  "tree": {
    "name": "Player",
    "type": "CharacterBody2D",
    "path": "/root/Player",
    "children": [
      {
        "name": "CollisionShape2D",
        "type": "CollisionShape2D",
        "path": "/root/Player/CollisionShape2D",
        "children": []
      }
    ]
  },
  "scene_path": "res://scenes/player.tscn"
}
```

### `get_open_script`

Get the currently open script in the Script Editor.

**Request params:** `{}`

**Response result:**
```json
{
  "path": "res://scripts/player.gd",
  "content": "extends CharacterBody2D\n\nvar speed := 300.0\n...",
  "line_count": 45
}
```

### `get_project_settings`

Get project settings.

**Request params:**
```json
{
  "path": "display/window/size/viewport_width"  // Optional, null for common settings
}
```

**Response result:**
```json
{
  "settings": {
    "display/window/size/viewport_width": 1920
  }
}
```

---

## Actuation Methods (Brain → Godot)

### `read_file`

Read a file from the project.

**Request params:**
```json
{
  "path": "scripts/player.gd"
}
```

**Response result:**
```json
{
  "path": "res://scripts/player.gd",
  "content": "extends CharacterBody2D\n...",
  "exists": true
}
```

### `write_file`

Write content to a file. **Requires HITL confirmation.**

**Request params:**
```json
{
  "path": "scripts/player.gd",
  "content": "extends CharacterBody2D\n\nvar speed := 400.0\n...",
  "create_backup": true,
  "requires_confirmation": true
}
```

**Response result:**
```json
{
  "success": true,
  "message": "File written successfully",
  "backup_path": "res://scripts/player.gd.bak"
}
```

### `set_project_setting`

Modify a project setting. **Requires HITL confirmation.**

**Request params:**
```json
{
  "path": "display/window/size/viewport_width",
  "value": 1920,
  "requires_confirmation": true
}
```

**Response result:**
```json
{
  "success": true,
  "message": "Setting updated"
}
```

### `create_node`

Create a new node in the scene. **Requires HITL confirmation.**

**Request params:**
```json
{
  "parent_path": "/root/Player",
  "node_name": "Sprite2D",
  "node_type": "Sprite2D",
  "properties": {},
  "requires_confirmation": true
}
```

**Response result:**
```json
{
  "success": true,
  "node_path": "/root/Player/Sprite2D",
  "message": "Node created"
}
```

### `delete_node`

Delete a node from the scene. **Requires HITL confirmation.**

**Request params:**
```json
{
  "node_path": "/root/Player/OldSprite",
  "requires_confirmation": true
}
```

**Response result:**
```json
{
  "success": true,
  "message": "Node deleted"
}
```

---

## HITL Confirmation Flow

When an actuation method has `requires_confirmation: true`, the following flow occurs:

### `confirmation_request` (Brain → Godot)

The brain sends a confirmation request to display in the editor.

**Params:**
```json
{
  "confirmation_id": "uuid-string",
  "action_type": "write_file",
  "description": "Update player movement speed",
  "details": {
    "path": "res://scripts/player.gd",
    "content": "...",
    "original_content": "..."
  }
}
```

### `confirmation_response` (Godot → Brain)

User's decision after reviewing the proposed change.

**Params:**
```json
{
  "confirmation_id": "uuid-string",
  "approved": true,
  "modified_content": null  // Or user's edited version
}
```

---

## Events (Godot → Brain)

Events are fire-and-forget notifications with no response.

### `console_error`

Report an error from the Godot console.

**Params:**
```json
{
  "text": "Attempt to call function on null instance",
  "type": "script_error",
  "script_path": "res://scripts/player.gd",
  "line": 42
}
```

### `scene_changed`

Notify when the active scene changes.

**Params:**
```json
{
  "scene_path": "res://scenes/level_1.tscn"
}
```

### `script_changed`

Notify when the open script changes.

**Params:**
```json
{
  "script_path": "res://scripts/enemy.gd"
}
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| -32700 | Parse error (invalid JSON) |
| -32600 | Invalid Request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |

---

## REST Endpoints

The brain also exposes REST endpoints for monitoring:

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "ok"
}
```

### `GET /status`

Current connection status.

**Response:**
```json
{
  "connected": true,
  "session_id": "uuid-string",
  "project_name": "My Game",
  "total_tokens": 5420
}
```
