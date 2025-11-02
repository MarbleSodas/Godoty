# Godoty Quick Reference

## Installation (5 Minutes)

1. **Install Godot Plugin:**
   - Copy `godot-plugin/addons/godoty` to your project's `addons/` folder
   - Enable in Project Settings → Plugins

2. **Setup Tauri App:**
   ```bash
   cd tauri-app
   bun install
   bun tauri dev
   ```

3. **Configure API Key:**
   - Open Settings panel in Tauri app
   - Add your OpenAI API key
   - Click Save

## Quick Start

1. Open Godot with a scene
2. Start Tauri app: `bun tauri dev`
3. Wait for "🟢 Connected to Godot"
4. Type a command and press Execute

## Example Commands

### Basic Nodes
```
Create a Node2D named Player
Add a Sprite2D to the scene
Create a Camera2D
```

### 2D Game Objects
```
Add a 2D player character with a sprite and collision shape
Create a platform with a static body and collision
Add a coin collectible with an Area2D
```

### UI Elements
```
Create a button labeled "Start Game"
Add a label showing "Score: 0" in the top left
Create a health bar UI
```

### Complete Scenes
```
Create a platformer level with a player, ground, and obstacles
Make a main menu with title and buttons
Build a simple inventory UI
```

### Advanced
```
Add a CharacterBody2D with WASD movement script
Create an enemy that patrols between two points
Add a particle effect for collecting items
```

## Command Protocol

### Available Actions

| Action | Description | Example |
|--------|-------------|---------|
| `create_node` | Create a new node | Create a Sprite2D |
| `delete_node` | Delete a node | Remove the old player |
| `modify_node` | Change node properties | Set player position to (100, 200) |
| `attach_script` | Add a script to a node | Add movement script to player |
| `create_scene` | Create a new scene | Create a new level scene |
| `get_scene_info` | Get current scene info | Show me the scene structure |

### Common Node Types

**2D Nodes:**
- `Node2D` - Basic 2D node
- `Sprite2D` - 2D sprite
- `CharacterBody2D` - Character with physics
- `RigidBody2D` - Physics body
- `StaticBody2D` - Static collision
- `Area2D` - Detection area
- `CollisionShape2D` - Collision shape
- `Camera2D` - 2D camera

**3D Nodes:**
- `Node3D` - Basic 3D node
- `MeshInstance3D` - 3D mesh
- `CharacterBody3D` - 3D character
- `Camera3D` - 3D camera
- `DirectionalLight3D` - Directional light

**UI Nodes:**
- `Control` - Base UI node
- `Label` - Text label
- `Button` - Clickable button
- `TextureRect` - Image display
- `Panel` - UI panel
- `VBoxContainer` - Vertical layout
- `HBoxContainer` - Horizontal layout

## Troubleshooting

| Problem | Solution |
|---------|----------|
| 🔴 Disconnected | Restart Godot and Tauri app |
| ❌ API key error | Add API key in Settings |
| ⏳ Command stuck | Check Godot Output tab for errors |
| No scene open | Open or create a scene in Godot |
| Port 9001 in use | Close other apps using the port |

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Focus input | `Ctrl/Cmd + L` |
| Submit command | `Enter` |
| Clear input | `Esc` |
| Open DevTools | `Ctrl/Cmd + Shift + I` |

## File Locations

```
Config: ~/.config/godoty/config.json (Linux/Mac)
        %APPDATA%/godoty/config.json (Windows)

Logs:   Godot Output tab
        Tauri terminal
```

## Tips & Tricks

1. **Be Specific:** "Add a CharacterBody2D with Sprite2D and CollisionShape2D" works better than "Add a player"

2. **Use Node Names:** "Add a sprite to Player" references the Player node

3. **Combine Actions:** "Create a button labeled Start and position it at (400, 300)"

4. **Check History:** Review past commands to see what worked

5. **Start Simple:** Test with basic commands before complex scenes

6. **Scene First:** Always have a scene open in Godot

7. **Save Often:** Godot won't auto-save AI-generated changes

## Common Patterns

### Player Setup
```
Add a CharacterBody2D named Player with:
- Sprite2D for visuals
- CollisionShape2D for collision
- Camera2D that follows the player
```

### Enemy Setup
```
Create an enemy with:
- CharacterBody2D named Enemy
- Sprite2D with red color
- Area2D for player detection
- CollisionShape2D
```

### UI Setup
```
Create a game UI with:
- Label for score in top left
- Label for health in top right
- Button for pause in top center
```

### Level Setup
```
Create a platformer level with:
- StaticBody2D ground platform
- Multiple smaller platforms
- Player spawn point
- Goal area
```

## Status Indicators

| Icon | Meaning |
|------|---------|
| 🟢 | Connected to Godot |
| 🟡 | Connecting... |
| 🔴 | Disconnected |
| ✅ | Command succeeded |
| ❌ | Command failed |
| ⏳ | Processing... |

## Getting Help

1. Check SETUP_GUIDE.md for detailed setup
2. Read DEVELOPMENT.md for technical details
3. Review Godot Output tab for errors
4. Check Tauri console for logs
5. Try simpler commands first

## Version Info

- Godoty: 0.1.0
- Godot: 4.x required
- Tauri: 2.x
- OpenAI: GPT-4

---

**Need more help?** See SETUP_GUIDE.md for detailed instructions.

