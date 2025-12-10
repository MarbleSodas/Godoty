"""
Tests for Godot file parsers.

These tests verify the regex-based parsers for:
- .tscn (Text Scene) files
- .tres (Text Resource) files
- .gd (GDScript) files
- project.godot configuration
"""

import pytest
import tempfile
import os
from pathlib import Path

from context.godot_parsers import (
    parse_tscn, parse_tres, parse_gdscript, parse_project_godot,
    GodotPatterns
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_tscn_content():
    """Sample .tscn file content for testing."""
    return '''[gd_scene load_steps=3 format=3 uid="uid://abc123"]

[ext_resource type="Script" uid="uid://xyz789" path="res://player.gd" id="1_abc"]
[ext_resource type="PackedScene" uid="uid://def456" path="res://weapon.tscn" id="2_xyz"]

[sub_resource type="CircleShape2D" id="CircleShape2D_abc"]
radius = 16.0

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_abc")
speed = 200.0

[node name="CollisionShape2D" type="CollisionShape2D" parent="."]
shape = SubResource("CircleShape2D_abc")

[node name="Sprite2D" type="Sprite2D" parent="."]

[node name="Weapon" type="Node2D" parent="." instance=ExtResource("2_xyz")]

[connection signal="body_entered" from="." to="." method="_on_body_entered"]
[connection signal="health_changed" from="." to="Sprite2D" method="_on_health_changed" flags=1]
'''


@pytest.fixture
def sample_gdscript_content():
    """Sample GDScript content for testing."""
    return '''## Player controller script
## Handles movement and combat

class_name Player
extends CharacterBody2D

signal health_changed(new_health: int)
signal died

const MAX_HEALTH: int = 100
const SPEED: float = 200.0

@export var health: int = 100
@export_range(0, 500) var max_speed: float = 300.0

@onready var sprite: Sprite2D = $Sprite2D
@onready var collision: CollisionShape2D = $CollisionShape2D

var _is_dead: bool = false


## Handles physics movement
func _physics_process(delta: float) -> void:
    var velocity := Vector2.ZERO
    
    if Input.is_action_pressed("move_right"):
        velocity.x += 1
    if Input.is_action_pressed("move_left"):
        velocity.x -= 1
    
    velocity = velocity.normalized() * SPEED
    move_and_slide()


## Take damage and emit signal
func take_damage(amount: int) -> void:
    health -= amount
    health_changed.emit(health)
    
    if health <= 0:
        _die()


func _die() -> void:
    _is_dead = true
    died.emit()


static func get_player_count() -> int:
    return 1
'''


@pytest.fixture
def sample_project_godot_content():
    """Sample project.godot content."""
    return '''config_version=5

[application]
config/name="My Game"
config/features=PackedStringArray("4.2", "Forward Plus")
run/main_scene="res://main.tscn"

[autoload]
Events="*res://autoloads/events.gd"
GameManager="*res://autoloads/game_manager.gd"

[input]
move_left={
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":65,"key_label":0,"unicode":97,"echo":false,"script":null)]
}
move_right={
"deadzone": 0.5,
"events": []
}

[display]
window/size/viewport_width=1280
window/size/viewport_height=720
'''


# =============================================================================
# Pattern Tests
# =============================================================================

class TestGodotPatterns:
    """Tests for regex patterns."""
    
    def test_scene_header_pattern(self):
        """Test parsing scene header."""
        header = '[gd_scene load_steps=3 format=3 uid="uid://abc123"]'
        match = GodotPatterns.SCENE_HEADER.search(header)
        
        assert match is not None
        assert match.group(1) == "3"  # load_steps
        assert match.group(2) == "3"  # format
        assert match.group(3) == "uid://abc123"  # uid
    
    def test_ext_resource_pattern(self):
        """Test parsing external resource."""
        line = '[ext_resource type="Script" uid="uid://xyz" path="res://player.gd" id="1_abc"]'
        match = GodotPatterns.EXT_RESOURCE_V4.search(line)
        
        assert match is not None
        assert match.group(1) == "Script"  # type
        assert match.group(2) == "uid://xyz"  # uid
        assert match.group(3) == "res://player.gd"  # path
        assert match.group(4) == "1_abc"  # id
    
    def test_node_pattern(self):
        """Test parsing node definitions."""
        # Root node
        line1 = '[node name="Player" type="CharacterBody2D"]'
        match1 = GodotPatterns.NODE.search(line1)
        assert match1 is not None
        assert match1.group(1) == "Player"
        assert match1.group(2) == "CharacterBody2D"
        assert match1.group(3) is None  # no parent
        
        # Child node
        line2 = '[node name="Sprite2D" type="Sprite2D" parent="."]'
        match2 = GodotPatterns.NODE.search(line2)
        assert match2 is not None
        assert match2.group(1) == "Sprite2D"
        assert match2.group(3) == "."  # parent
    
    def test_connection_pattern(self):
        """Test parsing signal connections."""
        line = '[connection signal="body_entered" from="." to="Player" method="_on_body_entered" flags=1]'
        match = GodotPatterns.CONNECTION.search(line)
        
        assert match is not None
        assert match.group(1) == "body_entered"  # signal
        assert match.group(2) == "."  # from
        assert match.group(3) == "Player"  # to
        assert match.group(4) == "_on_body_entered"  # method
        assert match.group(5) == "1"  # flags
    
    def test_gdscript_class_name(self):
        """Test parsing class_name."""
        line = "class_name Player"
        match = GodotPatterns.GDSCRIPT_CLASS_NAME.search(line)
        
        assert match is not None
        assert match.group(1) == "Player"
    
    def test_gdscript_extends(self):
        """Test parsing extends."""
        line = "extends CharacterBody2D"
        match = GodotPatterns.GDSCRIPT_EXTENDS.search(line)
        
        assert match is not None
        assert match.group(1) == "CharacterBody2D"
    
    def test_gdscript_signal(self):
        """Test parsing signal definitions."""
        line = "signal health_changed(new_health: int)"
        match = GodotPatterns.GDSCRIPT_SIGNAL.search(line)
        
        assert match is not None
        assert match.group(1) == "health_changed"
        assert match.group(2) == "new_health: int"
    
    def test_gdscript_function(self):
        """Test parsing function definitions."""
        line = "func _physics_process(delta: float) -> void:"
        match = GodotPatterns.GDSCRIPT_FUNC.search(line)
        
        assert match is not None
        assert match.group(1) is None  # not static
        assert match.group(2) == "_physics_process"
        assert match.group(3) == "delta: float"
        assert match.group(4) == "void"
    
    def test_gdscript_static_function(self):
        """Test parsing static function."""
        line = "static func get_count() -> int:"
        match = GodotPatterns.GDSCRIPT_FUNC.search(line)
        
        assert match is not None
        assert match.group(1) is not None  # is static
        assert match.group(2) == "get_count"
    
    def test_gdscript_export(self):
        """Test parsing exports."""
        line = "@export var health: int = 100"
        match = GodotPatterns.GDSCRIPT_EXPORT.search(line)
        
        assert match is not None
        assert match.group(2) == "health"  # var name
        assert match.group(3) == "int"  # type
        assert match.group(4) == "100"  # default


# =============================================================================
# Parser Tests
# =============================================================================

class TestSceneParser:
    """Tests for .tscn parser."""
    
    def test_parse_tscn(self, sample_tscn_content):
        """Test parsing a complete scene file."""
        with tempfile.NamedTemporaryFile(suffix='.tscn', delete=False, mode='w') as f:
            f.write(sample_tscn_content)
            f.flush()
            
            try:
                scene = parse_tscn(f.name)
                
                # Check header
                assert scene.uid == "uid://abc123"
                assert scene.format_version == 3
                
                # Check external resources
                assert len(scene.ext_resources) == 2
                assert "1_abc" in scene.ext_resources
                assert scene.ext_resources["1_abc"].path == "res://player.gd"
                assert scene.ext_resources["1_abc"].type == "Script"
                
                # Check nodes
                assert len(scene.nodes) == 4
                
                # Check root node
                assert scene.root_node is not None
                assert scene.root_node.name == "Player"
                assert scene.root_node.type == "CharacterBody2D"
                
                # Check signal connections
                assert len(scene.connections) == 2
                conn = scene.connections[0]
                assert conn.signal == "body_entered"
                assert conn.method == "_on_body_entered"
                
            finally:
                os.unlink(f.name)


class TestGDScriptParser:
    """Tests for .gd parser."""
    
    def test_parse_gdscript(self, sample_gdscript_content):
        """Test parsing a complete GDScript file."""
        with tempfile.NamedTemporaryFile(suffix='.gd', delete=False, mode='w') as f:
            f.write(sample_gdscript_content)
            f.flush()
            
            try:
                script = parse_gdscript(f.name)
                
                # Check class info
                assert script.class_name == "Player"
                assert script.extends == "CharacterBody2D"
                
                # Check docstring
                assert script.docstring is not None
                assert "Player controller" in script.docstring
                
                # Check signals
                assert len(script.signals) == 2
                signal_names = [s.name for s in script.signals]
                assert "health_changed" in signal_names
                assert "died" in signal_names
                
                # Check functions
                assert len(script.functions) >= 4
                func_names = [f.name for f in script.functions]
                assert "_physics_process" in func_names
                assert "take_damage" in func_names
                assert "_die" in func_names
                assert "get_player_count" in func_names
                
                # Check function details
                physics = next(f for f in script.functions if f.name == "_physics_process")
                assert physics.return_type == "void"
                assert physics.is_virtual  # starts with _
                
                static_func = next(f for f in script.functions if f.name == "get_player_count")
                assert static_func.is_static
                
                # Check exports
                assert len(script.exports) == 2
                export_names = [e.name for e in script.exports]
                assert "health" in export_names
                assert "max_speed" in export_names
                
                # Check constants
                assert "MAX_HEALTH" in script.constants
                assert "SPEED" in script.constants
                
                # Check onready
                assert "sprite" in script.onready_vars
                assert "collision" in script.onready_vars
                
            finally:
                os.unlink(f.name)


class TestProjectGodotParser:
    """Tests for project.godot parser."""
    
    def test_parse_project_godot(self, sample_project_godot_content):
        """Test parsing project.godot file."""
        with tempfile.NamedTemporaryFile(delete=False, mode='w') as f:
            f.write(sample_project_godot_content)
            f.flush()
            
            try:
                config = parse_project_godot(f.name)
                
                # Check project name
                assert config.project_name == "My Game"
                
                # Check features
                assert "4.2" in config.features
                
                # Check autoloads
                assert "Events" in config.autoloads
                assert "GameManager" in config.autoloads
                
                # Check settings exist
                assert "application" in config.settings
                assert "display" in config.settings
                
            finally:
                os.unlink(f.name)


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_scene(self):
        """Test parsing an empty/minimal scene."""
        content = '[gd_scene format=3]\n\n[node name="Root" type="Node"]\n'
        
        with tempfile.NamedTemporaryFile(suffix='.tscn', delete=False, mode='w') as f:
            f.write(content)
            f.flush()
            
            try:
                scene = parse_tscn(f.name)
                assert len(scene.nodes) == 1
                assert scene.root_node.name == "Root"
            finally:
                os.unlink(f.name)
    
    def test_gdscript_no_class_name(self):
        """Test parsing script without class_name."""
        content = '''extends Node

func _ready():
    pass
'''
        with tempfile.NamedTemporaryFile(suffix='.gd', delete=False, mode='w') as f:
            f.write(content)
            f.flush()
            
            try:
                script = parse_gdscript(f.name)
                assert script.class_name is None
                assert script.extends == "Node"
            finally:
                os.unlink(f.name)
    
    def test_invalid_file(self):
        """Test handling of invalid file content."""
        content = "This is not a valid scene file"
        
        with tempfile.NamedTemporaryFile(suffix='.tscn', delete=False, mode='w') as f:
            f.write(content)
            f.flush()
            
            try:
                scene = parse_tscn(f.name)
                # Should return empty scene, not crash
                assert len(scene.nodes) == 0
            finally:
                os.unlink(f.name)
