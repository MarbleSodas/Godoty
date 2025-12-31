"""Tests for project context gathering.

Tests cover:
- Context gathering when no project is connected
- Context gathering with a mock project
- project.godot parsing
- GDScript parsing for class dependencies
- Scene file parsing for hierarchies
- Context formatting for agents
"""

import tempfile
from pathlib import Path

import pytest


class TestProjectGodotParsing:
    """Tests for parsing project.godot files."""
    
    def test_parse_empty_project(self) -> None:
        """parse_project_godot returns defaults for empty project."""
        from app.agents.context import _parse_project_godot
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            # No project.godot file
            result = _parse_project_godot(project_path)
            
            assert result["project_name"] == ""
            assert result["main_scene"] is None
            assert result["autoloads"] == {}
    
    def test_parse_project_with_settings(self) -> None:
        """parse_project_godot extracts name, main scene, and autoloads."""
        from app.agents.context import _parse_project_godot
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            
            # Create a project.godot
            (project_path / "project.godot").write_text('''
[gd_resource type="ProjectSettings" load_steps=1 format=2]

[application]
config/name="Test Project"
run/main_scene="res://scenes/main.tscn"

[autoload]
GameManager="*res://autoload/game_manager.gd"
AudioManager="*res://autoload/audio_manager.gd"

[display]
window/size/width=1920
''')
            
            result = _parse_project_godot(project_path)
            
            assert result["project_name"] == "Test Project"
            assert result["main_scene"] == "res://scenes/main.tscn"
            assert "GameManager" in result["autoloads"]
            assert result["autoloads"]["GameManager"] == "res://autoload/game_manager.gd"


class TestGDScriptParsing:
    """Tests for parsing GDScript files."""
    
    def test_parse_script_with_class_name(self) -> None:
        """_parse_gdscript extracts class_name and extends."""
        from app.agents.context import _parse_gdscript
        
        content = '''class_name Player
extends CharacterBody2D

signal health_changed(new_health: int)

@export var speed: float = 200.0
@export var health: int = 100

var _internal_var: int = 0

func _ready() -> void:
    pass
'''
        result = _parse_gdscript(content, "res://player.gd")
        
        assert result.class_name == "Player"
        assert result.extends == "CharacterBody2D"
        assert "health_changed" in result.signals
        assert "speed" in result.exported_vars
        assert "health" in result.exported_vars
    
    def test_parse_script_with_dependencies(self) -> None:
        """_parse_gdscript extracts preload/load dependencies."""
        from app.agents.context import _parse_gdscript
        
        content = '''extends Node

const Utils = preload("res://utils/helpers.gd")
const Config = preload("res://config/game_config.tres")

var _texture = load("res://assets/player.png")
'''
        result = _parse_gdscript(content, "res://game.gd")
        
        assert result.extends == "Node"
        assert "res://utils/helpers.gd" in result.dependencies
        assert "res://config/game_config.tres" in result.dependencies
        assert "res://assets/player.png" in result.dependencies


class TestSceneParsing:
    """Tests for parsing .tscn scene files."""
    
    def test_parse_scene_with_root(self) -> None:
        """_parse_scene_file extracts root node info."""
        from app.agents.context import _parse_scene_file
        
        content = '''[gd_scene load_steps=2 format=3 uid="uid://abc123"]

[ext_resource type="Script" path="res://player.gd" id="1_abc"]

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_abc")

[node name="Sprite" type="Sprite2D" parent="."]

[node name="CollisionShape" type="CollisionShape2D" parent="."]
'''
        result = _parse_scene_file(content, "res://scenes/player.tscn")
        
        assert result.root_name == "Player"
        assert result.root_type == "CharacterBody2D"
        assert result.path == "res://scenes/player.tscn"


class TestContextGathering:
    """Tests for the full context gathering flow."""
    
    def test_gather_context_no_project(self) -> None:
        """gather_project_context returns None when no project connected."""
        import asyncio
        from app.agents.context import gather_project_context
        from app.agents.tools import set_project_path
        
        # Ensure no project is set
        set_project_path(None)
        
        result = asyncio.get_event_loop().run_until_complete(gather_project_context())
        assert result is None
    
    def test_gather_context_with_project(self) -> None:
        """gather_project_context returns context for valid project."""
        import asyncio
        from app.agents.context import gather_project_context
        from app.agents.tools import set_project_path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            
            # Create minimal project structure
            (project_path / "project.godot").write_text('''
[application]
config/name="Test Game"
run/main_scene="res://main.tscn"
''')
            (project_path / "main.tscn").write_text('''
[gd_scene format=3]
[node name="Main" type="Node"]
''')
            (project_path / "player.gd").write_text('''
class_name Player
extends CharacterBody2D
''')
            
            # Create scripts directory
            scripts_dir = project_path / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "utils.gd").write_text("extends Node")
            
            try:
                set_project_path(str(project_path))
                
                result = asyncio.get_event_loop().run_until_complete(gather_project_context())
                
                assert result is not None
                assert result.project_name == "Test Game"
                assert result.main_scene == "res://main.tscn"
                assert len(result.scripts) >= 1
                assert len(result.scenes) >= 1
                assert "scripts" in result.directories
            finally:
                set_project_path(None)


class TestContextFormatting:
    """Tests for formatting context for agent consumption."""
    
    def test_format_context(self) -> None:
        """format_context_for_agent produces readable output."""
        from app.agents.context import ProjectContext, ScriptInfo, SceneInfo, format_context_for_agent
        
        ctx = ProjectContext(
            project_path="/test/project",
            project_name="Test Game",
            main_scene="res://main.tscn",
            autoloads={"GameManager": "res://autoload/game.gd"},
            scripts=[
                ScriptInfo(
                    path="res://player.gd",
                    class_name="Player",
                    extends="CharacterBody2D",
                )
            ],
            scenes=[
                SceneInfo(
                    path="res://main.tscn",
                    root_name="Main",
                    root_type="Node2D",
                )
            ],
            directories=["scripts", "scenes", "assets"],
        )
        
        result = format_context_for_agent(ctx)
        
        # Check key elements are present
        assert "Test Game" in result
        assert "res://main.tscn" in result
        assert "GameManager" in result
        assert "Player" in result
        assert "CharacterBody2D" in result


class TestContextCaching:
    """Tests for context caching behavior."""
    
    def test_invalidate_cache(self) -> None:
        """invalidate_context_cache clears the cached context."""
        from app.agents.context import invalidate_context_cache, _context_cache_valid
        
        # Force cache to be "valid"
        import app.agents.context as context_module
        context_module._context_cache_valid = True
        
        invalidate_context_cache()
        
        assert context_module._context_cache_valid is False
