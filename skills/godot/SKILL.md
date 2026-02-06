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

## MCP Servers

- `godot`: General Godot automation tools.
- `godot-doc`: Tools for interacting with Godot documentation.
