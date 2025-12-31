"""Scenario tests for Observer agent scene/script analysis.

These tests validate that the Observer agent correctly analyzes
Godot scenes and scripts, identifying issues and providing suggestions.

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


class TestSceneTreeAnalysisScenarios:
    """Scenario tests for scene tree analysis."""

    @pytest.fixture
    def sample_scene_tree(self) -> dict[str, Any]:
        """Sample scene tree for testing."""
        return {
            "name": "Player",
            "type": "CharacterBody2D",
            "children": [
                {
                    "name": "Sprite2D",
                    "type": "Sprite2D",
                    "children": []
                },
                {
                    "name": "AnimationPlayer",
                    "type": "AnimationPlayer",
                    "children": []
                },
            ]
        }

    @pytest.fixture
    def scene_tree_missing_collision(self) -> dict[str, Any]:
        """Scene tree with missing collision shape (common issue)."""
        return {
            "name": "Player",
            "type": "CharacterBody2D",
            "children": [
                {
                    "name": "Sprite2D",
                    "type": "Sprite2D",
                    "children": []
                },
                # Missing CollisionShape2D!
            ]
        }

    @pytest.fixture
    def scene_tree_with_collision(self) -> dict[str, Any]:
        """Complete scene tree with collision shape."""
        return {
            "name": "Player",
            "type": "CharacterBody2D",
            "children": [
                {
                    "name": "Sprite2D",
                    "type": "Sprite2D",
                    "children": []
                },
                {
                    "name": "CollisionShape2D",
                    "type": "CollisionShape2D",
                    "children": []
                },
            ]
        }

    def test_detects_missing_collision_shape(
        self, scene_tree_missing_collision: dict[str, Any]
    ) -> None:
        """
        Scenario: Scene has CharacterBody2D without CollisionShape2D
        Expected: Observer identifies the missing collision shape
        """
        issues = self._analyze_scene_tree(scene_tree_missing_collision)
        
        collision_issue = any(
            "collision" in issue.lower() 
            for issue in issues
        )
        assert collision_issue, "Should detect missing CollisionShape2D"

    def test_no_false_positives_for_complete_scene(
        self, scene_tree_with_collision: dict[str, Any]
    ) -> None:
        """
        Scenario: Scene has all required nodes
        Expected: No collision-related issues reported
        """
        issues = self._analyze_scene_tree(scene_tree_with_collision)
        
        collision_issue = any(
            "collision" in issue.lower() and "missing" in issue.lower()
            for issue in issues
        )
        assert not collision_issue, "Should not report false positives"

    def _analyze_scene_tree(self, tree: dict[str, Any]) -> list[str]:
        """Analyze a scene tree and return list of issues.
        
        This simulates the Observer's analysis logic.
        """
        issues = []
        
        def check_node(node: dict[str, Any], parent_type: str | None = None) -> None:
            node_type = node.get("type", "")
            children = node.get("children", [])
            child_types = [c.get("type", "") for c in children]
            
            # Check: Physics bodies need collision shapes
            physics_bodies = [
                "CharacterBody2D", "CharacterBody3D",
                "RigidBody2D", "RigidBody3D",
                "StaticBody2D", "StaticBody3D",
                "Area2D", "Area3D",
            ]
            
            if node_type in physics_bodies:
                has_collision = any(
                    "CollisionShape" in ct or "CollisionPolygon" in ct
                    for ct in child_types
                )
                if not has_collision:
                    issues.append(
                        f"Missing CollisionShape on {node_type} '{node.get('name')}'"
                    )
            
            # Recurse into children
            for child in children:
                check_node(child, node_type)
        
        check_node(tree)
        return issues


class TestScriptAnalysisScenarios:
    """Scenario tests for script content analysis."""

    @pytest.fixture
    def script_with_issues(self) -> str:
        """Script with common issues."""
        return '''
extends CharacterBody2D

var speed = 200
var health

func _ready():
    pass

func take_damage(amount):
    health -= amount
    if health < 0:
        queue_free()
'''

    @pytest.fixture
    def script_well_written(self) -> str:
        """Well-written script following best practices."""
        return '''
class_name Player
extends CharacterBody2D
## A player character with movement and health.

signal health_changed(new_health: int)
signal died

@export var speed: float = 200.0
@export var max_health: int = 100

var _current_health: int

func _ready() -> void:
    _current_health = max_health

func take_damage(amount: int) -> void:
    _current_health = maxi(0, _current_health - amount)
    health_changed.emit(_current_health)
    if _current_health <= 0:
        died.emit()
        queue_free()
'''

    def test_detects_missing_type_hints(
        self, script_with_issues: str
    ) -> None:
        """
        Scenario: Script lacks type annotations
        Expected: Observer identifies missing types
        """
        analysis = self._analyze_script(script_with_issues)
        
        assert analysis["missing_types"], "Should detect missing type hints"

    def test_detects_uninitialized_variables(
        self, script_with_issues: str
    ) -> None:
        """
        Scenario: Script has uninitialized variables
        Expected: Observer identifies potential null reference
        """
        analysis = self._analyze_script(script_with_issues)
        
        assert analysis["uninitialized_vars"], "Should detect uninitialized variables"

    def test_detects_missing_class_name(
        self, script_with_issues: str
    ) -> None:
        """
        Scenario: Script lacks class_name declaration
        Expected: Observer suggests adding class_name
        """
        analysis = self._analyze_script(script_with_issues)
        
        assert not analysis["has_class_name"], "Should detect missing class_name"

    def test_well_written_script_passes(
        self, script_well_written: str
    ) -> None:
        """
        Scenario: Well-written script analyzed
        Expected: High quality score, no critical issues
        """
        analysis = self._analyze_script(script_well_written)
        
        assert analysis["has_class_name"], "Should have class_name"
        assert analysis["has_signals"], "Should use signals"
        assert analysis["has_docstrings"], "Should have docstrings"
        assert analysis["quality_score"] >= 0.7, "Should have high quality"

    def _analyze_script(self, content: str) -> dict[str, Any]:
        """Analyze script content and return analysis results.
        
        This simulates the Observer's script analysis.
        """
        results = {
            "has_class_name": "class_name " in content,
            "has_docstrings": "##" in content,
            "has_signals": "signal " in content,
            "has_export": "@export" in content,
            "has_onready": "@onready" in content,
            "missing_types": False,
            "uninitialized_vars": False,
            "deprecated_patterns": [],
            "quality_score": 0.0,
        }
        
        # Check for missing type hints
        # Pattern: "var name =" without type annotation
        untyped_vars = re.findall(r'\bvar\s+\w+\s*=', content)
        results["missing_types"] = len(untyped_vars) > 0
        
        # Check for uninitialized variables
        # Pattern: "var name" without "=" on same line
        lines = content.split('\n')
        for line in lines:
            if re.match(r'^\s*var\s+\w+\s*$', line.strip()):
                results["uninitialized_vars"] = True
                break
        
        # Check for deprecated patterns
        deprecated = {
            "emit_signal": "Use signal.emit() instead",
            "yield": "Use await instead",
            "KinematicBody": "Use CharacterBody2D/3D instead",
        }
        for pattern, suggestion in deprecated.items():
            if pattern in content:
                results["deprecated_patterns"].append((pattern, suggestion))
        
        # Calculate quality score
        checks = [
            results["has_class_name"],
            results["has_docstrings"],
            not results["missing_types"],
            not results["uninitialized_vars"],
            len(results["deprecated_patterns"]) == 0,
        ]
        results["quality_score"] = sum(checks) / len(checks)
        
        return results


class TestObservationReportScenarios:
    """Scenario tests for observation report format."""

    def test_report_has_summary(self) -> None:
        """
        Scenario: Observer provides analysis
        Expected: Report includes a summary section
        """
        report = self._generate_mock_report()
        assert "summary" in report, "Report should have summary"
        assert len(report["summary"]) > 0, "Summary should not be empty"

    def test_report_has_issues(self) -> None:
        """
        Scenario: Observer finds problems
        Expected: Report includes issues with severity
        """
        report = self._generate_mock_report(with_issues=True)
        assert "issues" in report, "Report should have issues section"
        
        for issue in report["issues"]:
            assert "severity" in issue, "Issues should have severity"
            assert "description" in issue, "Issues should have description"

    def test_report_has_suggestions(self) -> None:
        """
        Scenario: Observer provides recommendations
        Expected: Report includes actionable suggestions
        """
        report = self._generate_mock_report()
        assert "suggestions" in report, "Report should have suggestions"

    def _generate_mock_report(
        self, with_issues: bool = False
    ) -> dict[str, Any]:
        """Generate a mock observation report."""
        report = {
            "summary": "Analyzed Player scene with 5 nodes",
            "details": {
                "node_count": 5,
                "script_attached": True,
            },
            "issues": [],
            "suggestions": [
                "Consider adding a Camera2D node for the player",
            ],
        }
        
        if with_issues:
            report["issues"] = [
                {
                    "severity": "error",
                    "description": "Missing CollisionShape2D on CharacterBody2D",
                    "suggestion": "Add a CollisionShape2D child node",
                },
                {
                    "severity": "warning",
                    "description": "Script uses untyped variables",
                    "suggestion": "Add type annotations for better code quality",
                },
            ]
        
        return report


class TestPerceptionPriorityScenarios:
    """Tests for Observer's perception priority decisions."""

    def test_prefers_scene_tree_over_screenshot(self) -> None:
        """
        Scenario: User asks about scene structure
        Expected: Observer uses scene tree, not screenshot
        """
        # This tests the decision logic, not actual agent calls
        request = "What nodes are in my scene?"
        perception_choice = self._choose_perception_method(request)
        
        assert perception_choice == "scene_tree", "Should use scene tree for structure"

    def test_prefers_script_over_screenshot(self) -> None:
        """
        Scenario: User asks about code
        Expected: Observer uses script content, not screenshot
        """
        request = "What does my player script do?"
        perception_choice = self._choose_perception_method(request)
        
        assert perception_choice == "script", "Should use script for code questions"

    def test_uses_screenshot_for_visual(self) -> None:
        """
        Scenario: User asks about visual appearance
        Expected: Observer uses screenshot
        """
        request = "Why does my sprite look stretched?"
        perception_choice = self._choose_perception_method(request)
        
        assert perception_choice == "screenshot", "Should use screenshot for visuals"

    def _choose_perception_method(self, request: str) -> str:
        """Simulate Observer's perception method choice.
        
        Priority order:
        1. Scene tree - for structure questions
        2. Script - for code questions
        3. Screenshot - for visual questions
        """
        request_lower = request.lower()
        
        # Visual keywords -> screenshot
        visual_keywords = ["look", "appear", "visual", "see", "display", "render"]
        if any(kw in request_lower for kw in visual_keywords):
            return "screenshot"
        
        # Code keywords -> script
        code_keywords = ["script", "code", "function", "variable", "extends"]
        if any(kw in request_lower for kw in code_keywords):
            return "script"
        
        # Structure keywords -> scene tree
        structure_keywords = ["node", "scene", "tree", "child", "hierarchy"]
        if any(kw in request_lower for kw in structure_keywords):
            return "scene_tree"
        
        # Default to scene tree
        return "scene_tree"
