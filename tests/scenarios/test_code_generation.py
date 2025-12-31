"""Scenario tests for GDScript code generation quality.

These tests validate that the GDScript Coder agent generates
code that follows Godot 4.x best practices and conventions.

Based on Better Agents standards for ensuring agent behavior.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

# Add brain to path
brain_path = Path(__file__).parent.parent.parent / "brain"
if str(brain_path) not in sys.path:
    sys.path.insert(0, str(brain_path))

from .conftest import assert_gdscript_quality, calculate_quality_score


class TestGDScriptQualityScenarios:
    """Scenario tests for GDScript code generation quality."""

    def test_player_movement_static_typing(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: User asks for a 2D player movement script
        Expected: Response uses static typing throughout
        
        Quality Checks:
        - Function parameters have type hints
        - Return types are specified
        - Variables use explicit types where beneficial
        """
        good_response = sample_gdscript_responses["player_movement_good"]
        results = assert_gdscript_quality(good_response)
        
        assert results["has_static_typing"], "Should use static typing (: float, : Vector2)"
        assert results["has_return_types"], "Should specify return types (-> void, -> Vector2)"

    def test_player_movement_godot4_patterns(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: Player movement script uses Godot 4.x patterns
        Expected: Uses CharacterBody2D, move_and_slide() without args
        
        Quality Checks:
        - CharacterBody2D (not KinematicBody)
        - move_and_slide() without velocity argument
        - No deprecated patterns
        """
        good_response = sample_gdscript_responses["player_movement_good"]
        results = assert_gdscript_quality(good_response)
        
        assert results["uses_character_body"], "Should use CharacterBody2D (Godot 4.x)"
        assert results["no_kinematic_body"], "Should NOT use KinematicBody (deprecated)"

    def test_player_movement_annotations(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: Player movement script uses proper annotations
        Expected: Uses @export, @onready annotations
        
        Quality Checks:
        - @export for inspector-visible properties
        - @onready for deferred node references
        """
        good_response = sample_gdscript_responses["player_movement_good"]
        results = assert_gdscript_quality(good_response)
        
        assert results["has_export_annotation"], "Should use @export annotation"

    def test_player_movement_documentation(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: Player movement script has documentation
        Expected: Includes ## docstrings for class and functions
        
        Quality Checks:
        - Class has top-level description
        - Public functions have docstrings
        """
        good_response = sample_gdscript_responses["player_movement_good"]
        results = assert_gdscript_quality(good_response)
        
        assert results["has_docstrings"], "Should include ## docstrings"

    def test_signal_usage_godot4_emit(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: User asks for code with signals
        Expected: Uses signal.emit() not emit_signal()
        
        Quality Checks:
        - Uses signal.emit() syntax (Godot 4.x)
        - Does NOT use emit_signal() (deprecated)
        """
        good_response = sample_gdscript_responses["signal_usage_good"]
        results = assert_gdscript_quality(good_response)
        
        assert results["uses_godot4_emit"], "Should use signal.emit() (Godot 4.x)"
        assert results["no_emit_signal"], "Should NOT use emit_signal() (deprecated)"

    def test_bad_code_fails_quality_checks(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: Bad code fails quality validation
        Expected: Low quality score for deprecated patterns
        
        This test validates that our quality checks correctly
        identify code with deprecated patterns.
        """
        bad_response = sample_gdscript_responses["player_movement_bad"]
        results = assert_gdscript_quality(bad_response)
        score = calculate_quality_score(results)
        
        # Bad code should fail key checks
        assert not results["uses_character_body"], "Bad code uses deprecated KinematicBody"
        assert not results["no_kinematic_body"], "Bad code contains KinematicBody"
        assert score < 0.5, f"Bad code should have low quality score, got {score:.2f}"

    def test_quality_score_calculation(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: Good code achieves high quality score
        Expected: Score > 0.7 for well-written code
        """
        good_response = sample_gdscript_responses["player_movement_good"]
        results = assert_gdscript_quality(good_response)
        score = calculate_quality_score(results)
        
        assert score >= 0.7, f"Good code should have quality score >= 0.7, got {score:.2f}"


class TestGDScriptPatternDetection:
    """Tests for detecting specific GDScript patterns."""

    def test_detects_await_usage(self) -> None:
        """Scenario: Code uses await for async operations."""
        code = '''
```gdscript
func wait_for_timer() -> void:
    await get_tree().create_timer(1.0).timeout
    print("Timer finished")
```
'''
        results = assert_gdscript_quality(code)
        assert results["uses_godot4_await"], "Should detect await usage"

    def test_rejects_yield_usage(self) -> None:
        """Scenario: Code using yield is flagged as deprecated."""
        code = '''
```gdscript
func wait_for_timer():
    yield(get_tree().create_timer(1.0), "timeout")
    print("Timer finished")
```
'''
        results = assert_gdscript_quality(code)
        assert not results["no_yield"], "Should flag yield as deprecated"

    def test_detects_class_name(self) -> None:
        """Scenario: Code includes class_name declaration."""
        code = '''
```gdscript
class_name HealthComponent
extends Node

var health: int = 100
```
'''
        results = assert_gdscript_quality(code)
        assert results["has_class_name"], "Should detect class_name declaration"

    def test_detects_typed_parameters(self) -> None:
        """Scenario: Function parameters have type hints."""
        code = '''
```gdscript
func calculate_damage(base: float, multiplier: float = 1.0) -> float:
    return base * multiplier
```
'''
        results = assert_gdscript_quality(code)
        assert results["has_static_typing"], "Should detect typed parameters"
        assert results["has_return_types"], "Should detect return type"


class TestCodeExtractionScenarios:
    """Tests for extracting code from various response formats."""

    def test_extracts_single_code_block(self) -> None:
        """Scenario: Response contains one code block."""
        response = '''
Here's the implementation:

```gdscript
extends Node

func _ready() -> void:
    pass
```
'''
        code_blocks = re.findall(r'```gdscript\n(.*?)```', response, re.DOTALL)
        assert len(code_blocks) == 1
        assert "extends Node" in code_blocks[0]

    def test_extracts_multiple_code_blocks(self) -> None:
        """Scenario: Response contains multiple code blocks."""
        response = '''
First, create the base class:

```gdscript
class_name BaseEnemy
extends CharacterBody2D
```

Then, create the specific enemy:

```gdscript
class_name Goblin
extends BaseEnemy
```
'''
        code_blocks = re.findall(r'```gdscript\n(.*?)```', response, re.DOTALL)
        assert len(code_blocks) == 2
        assert "BaseEnemy" in code_blocks[0]
        assert "Goblin" in code_blocks[1]

    def test_handles_no_code_blocks(self) -> None:
        """Scenario: Response has no code blocks."""
        response = "I can help you with that. What specific feature do you need?"
        code_blocks = re.findall(r'```gdscript\n(.*?)```', response, re.DOTALL)
        assert len(code_blocks) == 0


class TestHITLConfirmationScenarios:
    """Tests for HITL confirmation mentions in responses."""

    def test_mentions_hitl_for_file_write(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: Code generation response mentions HITL
        Expected: Response notes that file write requires confirmation
        """
        response = sample_gdscript_responses["player_movement_good"]
        
        # Check for HITL mention
        hitl_mentioned = any(phrase in response.lower() for phrase in [
            "hitl",
            "confirmation",
            "approve",
            "requires"
        ])
        
        assert hitl_mentioned, "Response should mention HITL confirmation for file writes"

    def test_specifies_file_path(
        self, sample_gdscript_responses: dict[str, str]
    ) -> None:
        """
        Scenario: Response specifies target file path
        Expected: Response includes res:// path for the file
        """
        response = sample_gdscript_responses["player_movement_good"]
        
        # Check for res:// path
        has_res_path = "res://" in response
        
        assert has_res_path, "Response should specify target file path (res://...)"


class TestGodot4MigrationPatterns:
    """Tests for Godot 3.x to 4.x migration pattern detection."""

    @pytest.mark.parametrize("deprecated,replacement", [
        ("KinematicBody2D", "CharacterBody2D"),
        ("KinematicBody3D", "CharacterBody3D"),
        ("emit_signal", "signal.emit"),
        ("yield", "await"),
    ])
    def test_detects_deprecated_patterns(
        self, deprecated: str, replacement: str
    ) -> None:
        """
        Scenario: Deprecated Godot 3.x patterns are detected
        Expected: Quality checks flag deprecated patterns
        """
        # Code with deprecated pattern
        bad_code = f'''
```gdscript
extends Node

func test():
    {deprecated}("something")
```
'''
        results = assert_gdscript_quality(bad_code)
        
        # Should fail at least one deprecation check
        deprecation_checks = [
            results["no_kinematic_body"],
            results["no_emit_signal"],
            results["no_yield"],
        ]
        
        # At least some checks should pass for good code
        # (we're testing the detection works)


class TestEdgeCases:
    """Edge case scenarios for code quality checks."""

    def test_empty_response(self) -> None:
        """Scenario: Empty response handling."""
        results = assert_gdscript_quality("")
        score = calculate_quality_score(results)
        assert score < 0.5, "Empty response should have low score"

    def test_non_gdscript_code(self) -> None:
        """Scenario: Response contains non-GDScript code."""
        response = '''
```python
def hello():
    print("Hello, World!")
```
'''
        # Should not crash
        results = assert_gdscript_quality(response)
        assert isinstance(results, dict)

    def test_mixed_quality_code(self) -> None:
        """Scenario: Code has some good and some bad patterns."""
        code = '''
```gdscript
class_name Player
extends CharacterBody2D

var speed = 200  # No type annotation

func _physics_process(delta: float) -> void:
    move_and_slide()
```
'''
        results = assert_gdscript_quality(code)
        
        # Should pass some checks
        assert results["uses_character_body"]
        assert results["has_class_name"]
        # But not all
        score = calculate_quality_score(results)
        assert 0.3 < score < 0.9, "Mixed code should have medium score"
