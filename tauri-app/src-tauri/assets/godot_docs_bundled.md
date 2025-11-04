# Godot Quick Reference (Bundled)

This bundled excerpt covers high-frequency topics to speed up RAG lookups:
- Nodes & scenes
- Creating nodes programmatically
- Scene instancing
- NodePath and ownership
- UI basics (Control)
- 2D gameplay nodes
- Signals

## Nodes and Scene Tree
- A scene is a tree of Nodes.
- Add children with `add_child()`; remove with `queue_free()`.
- Access nodes: `get_node("Path/To/Node")` or `$Path/To/Node`.
- Use `@onready var foo = $Child` to initialize after the node is in the tree.

## Creating Nodes Programmatically (GDScript)
```gdscript
var sprite := Sprite2D.new()
add_child(sprite)
```
```gdscript
var instance = preload("res://MyScene.tscn").instantiate()
add_child(instance)
```

## Node Ownership and Saving
- To persist a dynamically added node in the editor, set `node.owner` to the edited scene root or scene:
```gdscript
var node = Node3D.new()
add_child(node)
node.owner = get_tree().edited_scene_root # in @tool/_ready
```
- Only nodes owned by the root passed to `PackedScene.pack()` are saved.

## NodePath and StringName Literals
```gdscript
@export var target_path: NodePath
var target = get_node(target_path)
```
- StringName: `&"name"`
- NodePath: `^"Parent/Child"`

## UI (Control) Quick Notes
- Common nodes: Panel, MarginContainer, VBoxContainer, HBoxContainer, Label, Button, HSlider, ProgressBar.
- Control anchors: `anchor_left/top/right/bottom` and `custom_minimum_size`.

## 2D Gameplay Nodes
- Node2D: `position`, `rotation`, `scale`.
- CharacterBody2D: `velocity`, `move_and_slide()`, `is_on_floor()`.
- Sprite2D: `texture`, `centered`.
- CollisionShape2D: set `shape` and parent it to a physics body.
- Area2D: signals `body_entered`, `area_entered`.

## Signals (GDScript)
```gdscript
signal health_changed(value)
health_changed.emit(42)
my_node.health_changed.connect(_on_health_changed)
```

## Input Helpers
- `Input.is_action_pressed()`
- `Input.is_action_just_pressed()`
- `Input.get_axis("left", "right")`

## Common Patterns
### Player Movement (2D)
```gdscript
extends CharacterBody2D
@export var speed := 300.0
func _physics_process(delta):
    var dir := Input.get_axis("move_left", "move_right")
    velocity.x = dir * speed
    move_and_slide()
```

### Health System
```gdscript
extends Node
signal health_changed(new_health)
@export var max_health := 100
var hp := max_health
func take_damage(n):
    hp = max(hp - n, 0)
    health_changed.emit(hp)
```

## Scene Instancing
```gdscript
var Packed := preload("res://Enemy.tscn")
var enemy := Packed.instantiate()
add_child(enemy)
```

## Accessing Deep Children
```gdscript
@onready var anim := $HUD/ShieldBar/AnimationPlayer
```

## Editor/Tool Scripts Persistence
- In @tool scripts, set `node.owner = get_tree().edited_scene_root` to persist.

## Troubleshooting: Parent Node Not Found
- Ensure the parent exists in the scene tree at the time of addition.
- For editor-time persistence, set `owner` properly.
- Use correct NodePath (relative to the node doing `get_node`).
- For `.tscn` edits, nodes can be declared with `[node name="Child" type="Sprite2D" parent="Parent/Path"]` and will be linked on load.

## References
- Godot docs: nodes & scenes, GDScript basics, Control class, PackedScene, signals, and running code in the editor.

