---
name: godot
description: "Godot game engine automation and documentation"
mcp:
  godot:
    command: ["node", "./dist/server.js"]
    env:
      GODOT_PATH: "${GODOT_PATH}"
  godot-doc:
    command: ["node", "./dist/doc-server.js"]
    env:
      GODOT_DOC_DIR: "${GODOT_DOC_DIR}"
allowed-tools: ["skill_mcp", "Read", "Write", "Bash"]
---

# Godot Skill

This skill provides tools for Godot game engine automation and documentation.

## Prerequisites

The following environment variables must be set:

- `GODOT_PATH`: Absolute path to the Godot executable (e.g. `/Applications/Godot.app/Contents/MacOS/Godot` or `C:\Program Files\Godot\Godot.exe`).
- `GODOT_DOC_DIR`: Path to the Godot documentation XML files (usually `godot/doc/classes` in the Godot source repository).

## Usage

### Automation Tools (`godot` server)

These tools allow you to control the Godot editor and project execution:

- `launch_editor`: Open the Godot editor for a specific project.
- `run_project`: Run a project (or specific scene) in debug mode.
- `stop_project`: Stop the currently running project.
- `get_debug_output`: Retrieve stdout/stderr from the running project.
- `capture_viewport`: Take a screenshot of the running project viewport.
- `list_projects`: Find Godot projects in a directory.
- `get_project_info`: Get details about a project (version, structure, name).
- `get_godot_version`: Check the configured Godot version.

**Scene Manipulation:**
- `create_scene`: Create a new scene file (`.tscn`).
- `save_scene`: Save or rename a scene.
- `add_node`: Add a node to a scene.
- `load_sprite`: Load a texture into a Sprite2D node.
- `export_mesh_library`: Export a scene as a MeshLibrary.

**Resource Management:**
- `get_uid`: Get the unique ID (UID) of a resource file.
- `update_project_uids`: Force update of UIDs in the project.

### Documentation Tools (`godot-doc` server)

These tools provide access to the Godot Class Reference:

- `godot_search`: Search for classes, methods, properties, signals, or constants.
- `godot_get_class`: Get detailed documentation for a class (description, members, inheritance).
- `godot_get_symbol`: Get documentation for a specific member (e.g. `Node._ready`).
- `godot_list_classes`: List all available classes.
