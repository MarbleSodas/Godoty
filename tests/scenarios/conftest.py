"""Shared fixtures for Better Agents scenario tests.

These fixtures provide mocked environments for testing agent behavior
without requiring actual LLM calls or Godot connections.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add brain to path for imports
brain_path = Path(__file__).parent.parent.parent / "brain"
if str(brain_path) not in sys.path:
    sys.path.insert(0, str(brain_path))


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_godot_ws() -> Generator[MagicMock, None, None]:
    """Mock the Godot WebSocket connection.
    
    Prevents actual WebSocket communication during tests.
    """
    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()
    
    with patch("app.agents.tools._ws_connection", mock_ws):
        yield mock_ws


@pytest.fixture
def mock_connection_manager() -> Generator[MagicMock, None, None]:
    """Mock the ConnectionManager for HITL confirmations.
    
    Auto-approves all HITL requests by default.
    """
    mock_manager = MagicMock()
    
    # Create a mock response object
    mock_response = MagicMock()
    mock_response.approved = True
    mock_manager.request_confirmation = AsyncMock(return_value=mock_response)
    
    with patch("app.agents.tools._connection_manager", mock_manager):
        yield mock_manager


@pytest.fixture
def mock_project_path(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a mock Godot project directory.
    
    Creates a minimal project structure for testing.
    """
    # Create project.godot
    (tmp_path / "project.godot").write_text('''
[application]
config/name="Test Project"
run/main_scene="res://scenes/main.tscn"

[autoload]
GameManager="*res://autoload/game_manager.gd"
''')
    
    # Create scenes directory
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    (scenes_dir / "main.tscn").write_text('''
[gd_scene format=3]
[node name="Main" type="Node2D"]
''')
    
    # Create scripts directory
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "player.gd").write_text('''
class_name Player
extends CharacterBody2D

signal health_changed(new_health: int)

@export var speed: float = 200.0

func _physics_process(delta: float) -> void:
    move_and_slide()
''')
    
    # Create autoload directory
    autoload_dir = tmp_path / "autoload"
    autoload_dir.mkdir()
    (autoload_dir / "game_manager.gd").write_text('''
extends Node

var score: int = 0
''')
    
    # Set the project path in tools module
    with patch("app.agents.tools._project_path", str(tmp_path)):
        yield tmp_path


@pytest.fixture
def mock_llm_response() -> Generator[MagicMock, None, None]:
    """Mock the LLM model to return predictable responses.
    
    This allows testing agent behavior without actual API calls.
    """
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Mocked LLM response"
    mock_model.run = AsyncMock(return_value=mock_response)
    
    with patch("app.agents.team._get_model", return_value=mock_model):
        yield mock_model


class MockTeamResponse:
    """Mock team response for testing."""
    
    def __init__(self, content: str, metrics: dict[str, Any] | None = None):
        self.content = content
        self.metrics = metrics or {}


@pytest.fixture
def sample_gdscript_responses() -> dict[str, str]:
    """Sample GDScript responses for testing code quality."""
    return {
        "player_movement_good": '''
I'll create a responsive 2D player controller using CharacterBody2D.

```gdscript
class_name Player
extends CharacterBody2D
## A responsive 2D player controller with WASD movement.

@export var speed: float = 200.0
@export var acceleration: float = 1000.0
@export var friction: float = 800.0

func _physics_process(delta: float) -> void:
    var input_dir: Vector2 = _get_input_direction()
    _apply_movement(input_dir, delta)
    move_and_slide()

func _get_input_direction() -> Vector2:
    return Vector2(
        Input.get_axis("ui_left", "ui_right"),
        Input.get_axis("ui_up", "ui_down")
    ).normalized()

func _apply_movement(direction: Vector2, delta: float) -> void:
    if direction != Vector2.ZERO:
        velocity = velocity.move_toward(direction * speed, acceleration * delta)
    else:
        velocity = velocity.move_toward(Vector2.ZERO, friction * delta)
```

This will require HITL confirmation to save to `res://scripts/player.gd`.
''',
        "player_movement_bad": '''
Here's a player script:

```gdscript
extends KinematicBody2D

var speed = 200

func _physics_process(delta):
    var velocity = Vector2()
    if Input.is_action_pressed("ui_right"):
        velocity.x += 1
    if Input.is_action_pressed("ui_left"):
        velocity.x -= 1
    velocity = move_and_slide(velocity * speed)
```
''',
        "signal_usage_good": '''
```gdscript
class_name Health
extends Resource
## Manages entity health with signals for state changes.

signal health_changed(current: int, maximum: int)
signal died

@export var max_health: int = 100
var current_health: int

func _init() -> void:
    current_health = max_health

func take_damage(amount: int) -> void:
    current_health = maxi(0, current_health - amount)
    health_changed.emit(current_health, max_health)
    if current_health <= 0:
        died.emit()
```
''',
        "signal_usage_bad": '''
```gdscript
extends Node

var max_health = 100
var health = 100

func take_damage(amount):
    health -= amount
    emit_signal("health_changed", health)
    if health <= 0:
        emit_signal("died")
```
''',
    }


# Utilities for scenario assertions

def assert_gdscript_quality(response: str) -> dict[str, bool]:
    """Check GDScript response quality and return results."""
    import re
    
    # Extract code blocks
    code_blocks = re.findall(r'```gdscript\n(.*?)```', response, re.DOTALL)
    code = "\n".join(code_blocks) if code_blocks else response
    
    results = {
        "has_static_typing": bool(re.search(r':\s*(int|float|String|Vector[234]i?|Array|bool|void)\b', code)),
        "has_return_types": bool(re.search(r'\)\s*->\s*\w+:', code)),
        "uses_godot4_emit": ".emit(" in code,
        "uses_godot4_await": "await " in code and "yield(" not in code,
        "no_kinematic_body": "KinematicBody" not in code,
        "no_emit_signal": "emit_signal(" not in code,
        "no_yield": "yield(" not in code,
        "has_export_annotation": "@export" in code,
        "has_onready_annotation": "@onready" in code or "@export" in code,
        "has_docstrings": bool(re.search(r'##\s*.+', code)),
        "has_class_name": "class_name " in code,
        "uses_character_body": "CharacterBody2D" in code or "CharacterBody3D" in code,
    }
    
    return results


def calculate_quality_score(results: dict[str, bool]) -> float:
    """Calculate overall quality score from check results."""
    return sum(results.values()) / len(results) if results else 0.0
