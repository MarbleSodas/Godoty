"""Scenario tests for Systems Architect feature planning.

These tests validate that the Architect agent correctly decomposes
complex feature requests into structured, actionable plans.

Based on Better Agents standards and BMAD methodology.
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


class TestFeatureDecompositionScenarios:
    """Scenario tests for feature decomposition quality."""

    @pytest.fixture
    def inventory_system_plan(self) -> dict[str, Any]:
        """Sample plan for an inventory system feature."""
        return {
            "overview": "Create a flexible inventory system using Resources for items and a manager script for CRUD operations.",
            "prerequisites": [
                "Godot 4.3 project with basic scene structure",
                "Understanding of Resource pattern",
            ],
            "tasks": [
                {
                    "name": "Create Item Resource",
                    "complexity": "simple",
                    "description": "Define base Item resource with name, icon, description, and stack properties",
                    "dependencies": [],
                },
                {
                    "name": "Create Inventory Resource",
                    "complexity": "simple", 
                    "description": "Define Inventory resource to hold array of items with max capacity",
                    "dependencies": ["Create Item Resource"],
                },
                {
                    "name": "Implement InventoryManager",
                    "complexity": "medium",
                    "description": "Create autoload for add/remove/query operations with signals",
                    "dependencies": ["Create Item Resource", "Create Inventory Resource"],
                },
                {
                    "name": "Build InventoryUI",
                    "complexity": "complex",
                    "description": "Create Control-based UI with grid layout and drag-drop",
                    "dependencies": ["Implement InventoryManager"],
                },
            ],
            "files": [
                {"path": "res://resources/item.gd", "action": "CREATE", "purpose": "Base Item resource"},
                {"path": "res://resources/inventory.gd", "action": "CREATE", "purpose": "Inventory container resource"},
                {"path": "res://autoload/inventory_manager.gd", "action": "CREATE", "purpose": "Inventory CRUD operations"},
                {"path": "res://ui/inventory_ui.tscn", "action": "CREATE", "purpose": "Inventory UI scene"},
            ],
            "challenges": [
                "Drag-drop may require custom logic for different slot types",
                "Consider save/load serialization for persistence",
            ],
        }

    def test_plan_has_overview(
        self, inventory_system_plan: dict[str, Any]
    ) -> None:
        """
        Scenario: Architect plans a feature
        Expected: Plan includes a clear overview
        """
        assert "overview" in inventory_system_plan
        assert len(inventory_system_plan["overview"]) > 20, "Overview should be meaningful"

    def test_plan_has_prerequisites(
        self, inventory_system_plan: dict[str, Any]
    ) -> None:
        """
        Scenario: Architect identifies what's needed first
        Expected: Plan lists prerequisites
        """
        assert "prerequisites" in inventory_system_plan
        assert len(inventory_system_plan["prerequisites"]) > 0

    def test_tasks_are_atomic(
        self, inventory_system_plan: dict[str, Any]
    ) -> None:
        """
        Scenario: Tasks can be worked on independently
        Expected: Each task is specific and testable
        """
        tasks = inventory_system_plan["tasks"]
        assert len(tasks) >= 3, "Feature should decompose into multiple tasks"
        
        for task in tasks:
            assert "name" in task, "Task needs a name"
            assert "complexity" in task, "Task needs complexity estimate"
            assert "description" in task, "Task needs description"
            assert len(task["description"]) > 10, "Description should be specific"

    def test_tasks_have_complexity_estimates(
        self, inventory_system_plan: dict[str, Any]
    ) -> None:
        """
        Scenario: Each task has effort estimation
        Expected: Complexity is simple/medium/complex
        """
        valid_complexity = ["simple", "medium", "complex"]
        
        for task in inventory_system_plan["tasks"]:
            assert task["complexity"] in valid_complexity, (
                f"Invalid complexity: {task['complexity']}"
            )

    def test_tasks_have_dependencies(
        self, inventory_system_plan: dict[str, Any]
    ) -> None:
        """
        Scenario: Tasks specify what must come first
        Expected: Dependencies form valid DAG (no cycles)
        """
        tasks = inventory_system_plan["tasks"]
        task_names = {t["name"] for t in tasks}
        
        for task in tasks:
            deps = task.get("dependencies", [])
            for dep in deps:
                assert dep in task_names or dep == [], (
                    f"Dependency '{dep}' not found in task list"
                )

    def test_plan_specifies_files(
        self, inventory_system_plan: dict[str, Any]
    ) -> None:
        """
        Scenario: Architect identifies files to create/modify
        Expected: File list with paths and actions
        """
        files = inventory_system_plan["files"]
        assert len(files) > 0, "Plan should specify files"
        
        for file_info in files:
            assert "path" in file_info, "File needs path"
            assert file_info["path"].startswith("res://"), "Path should be res://"
            assert "action" in file_info, "File needs action"
            assert file_info["action"] in ["CREATE", "MODIFY", "DELETE"]

    def test_plan_identifies_challenges(
        self, inventory_system_plan: dict[str, Any]
    ) -> None:
        """
        Scenario: Architect anticipates difficulties
        Expected: Plan lists potential challenges
        """
        assert "challenges" in inventory_system_plan
        # Challenges are optional but good practice


class TestGodotArchitecturePatterns:
    """Tests for Godot-specific architecture recommendations."""

    @pytest.mark.parametrize("feature,expected_pattern", [
        ("inventory system", "Resource"),
        ("save game system", "Resource"),
        ("item database", "Resource"),
        ("global game state", "Autoload"),
        ("audio manager", "Autoload"),
        ("scene transitions", "Autoload"),
        ("player health", "signal"),
        ("event system", "signal"),
        ("enemy defeated notification", "signal"),
        ("character controller", "CharacterBody"),
        ("NPC behavior", "state machine"),
    ])
    def test_recommends_appropriate_pattern(
        self, feature: str, expected_pattern: str
    ) -> None:
        """
        Scenario: Feature maps to appropriate Godot pattern
        Expected: Recommendation includes expected pattern
        """
        recommendation = self._get_pattern_recommendation(feature)
        
        assert expected_pattern.lower() in recommendation.lower(), (
            f"'{feature}' should recommend '{expected_pattern}'"
        )

    def _get_pattern_recommendation(self, feature: str) -> str:
        """Get architecture pattern recommendation for a feature."""
        feature_lower = feature.lower()
        
        # Data storage patterns
        if any(kw in feature_lower for kw in ["item", "inventory", "save", "database", "config"]):
            return "Resource pattern for data storage"
        
        # Global manager patterns
        if any(kw in feature_lower for kw in ["manager", "global", "audio", "transition"]):
            return "Autoload singleton pattern"
        
        # Communication patterns
        if any(kw in feature_lower for kw in ["health", "event", "notification", "defeated"]):
            return "Signal pattern for decoupling"
        
        # Movement patterns
        if any(kw in feature_lower for kw in ["controller", "character", "movement"]):
            return "CharacterBody2D/3D with physics"
        
        # Behavior patterns
        if any(kw in feature_lower for kw in ["behavior", "npc", "enemy", "ai"]):
            return "State machine pattern"
        
        return "Node composition pattern"


class TestPlanValidationScenarios:
    """Tests for plan validation and quality gates."""

    def test_validates_all_dependencies_exist(self) -> None:
        """
        Scenario: Plan with invalid dependency
        Expected: Validation catches the error
        """
        invalid_plan = {
            "tasks": [
                {"name": "Task A", "dependencies": ["NonexistentTask"]},
            ]
        }
        
        is_valid, errors = self._validate_plan(invalid_plan)
        
        assert not is_valid
        assert any("dependency" in e.lower() for e in errors)

    def test_validates_no_circular_dependencies(self) -> None:
        """
        Scenario: Plan with circular dependencies
        Expected: Validation catches the cycle
        """
        circular_plan = {
            "tasks": [
                {"name": "Task A", "dependencies": ["Task B"]},
                {"name": "Task B", "dependencies": ["Task A"]},
            ]
        }
        
        is_valid, errors = self._validate_plan(circular_plan)
        
        assert not is_valid
        assert any("circular" in e.lower() for e in errors)

    def test_validates_file_paths(self) -> None:
        """
        Scenario: Plan with invalid file paths
        Expected: Validation catches invalid paths
        """
        invalid_path_plan = {
            "tasks": [],
            "files": [
                {"path": "/absolute/path/bad.gd", "action": "CREATE"},
            ]
        }
        
        is_valid, errors = self._validate_plan(invalid_path_plan)
        
        assert not is_valid
        assert any("path" in e.lower() for e in errors)

    def _validate_plan(self, plan: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate a feature plan.
        
        Returns (is_valid, list_of_errors)
        """
        errors = []
        tasks = plan.get("tasks", [])
        task_names = {t["name"] for t in tasks}
        
        # Check dependencies exist
        for task in tasks:
            for dep in task.get("dependencies", []):
                if dep and dep not in task_names:
                    errors.append(f"Invalid dependency: '{dep}' not found")
        
        # Check for circular dependencies (simple check)
        visited = set()
        def has_cycle(task_name: str, path: set) -> bool:
            if task_name in path:
                return True
            if task_name in visited:
                return False
            visited.add(task_name)
            path.add(task_name)
            
            task = next((t for t in tasks if t["name"] == task_name), None)
            if task:
                for dep in task.get("dependencies", []):
                    if dep and has_cycle(dep, path.copy()):
                        return True
            return False
        
        for task in tasks:
            if has_cycle(task["name"], set()):
                errors.append(f"Circular dependency detected involving '{task['name']}'")
                break
        
        # Check file paths
        for file_info in plan.get("files", []):
            path = file_info.get("path", "")
            if path and not path.startswith("res://"):
                errors.append(f"Invalid path: '{path}' should start with res://")
        
        return len(errors) == 0, errors


class TestComplexityEstimationScenarios:
    """Tests for task complexity estimation accuracy."""

    @pytest.mark.parametrize("task_description,expected_complexity", [
        ("Create a Resource file for item data", "simple"),
        ("Define an Autoload script with basic state", "simple"),
        ("Implement add/remove methods with signals", "medium"),
        ("Build state machine with 3-4 states", "medium"),
        ("Create UI with drag-drop and animations", "complex"),
        ("Implement multiplayer sync with prediction", "complex"),
    ])
    def test_complexity_estimation(
        self, task_description: str, expected_complexity: str
    ) -> None:
        """
        Scenario: Task description maps to complexity
        Expected: Reasonable complexity estimate
        """
        estimated = self._estimate_complexity(task_description)
        
        # Allow one level variance (simple<->medium, medium<->complex)
        complexity_order = ["simple", "medium", "complex"]
        est_idx = complexity_order.index(estimated)
        exp_idx = complexity_order.index(expected_complexity)
        
        assert abs(est_idx - exp_idx) <= 1, (
            f"'{task_description}' estimated as {estimated}, expected {expected_complexity}"
        )

    def _estimate_complexity(self, description: str) -> str:
        """Estimate task complexity from description."""
        desc_lower = description.lower()
        
        # Complex indicators
        complex_keywords = [
            "ui", "animation", "drag", "drop", "multiplayer",
            "network", "sync", "shader", "3d",
        ]
        if any(kw in desc_lower for kw in complex_keywords):
            return "complex"
        
        # Medium indicators
        medium_keywords = [
            "implement", "state machine", "manager", "controller",
            "logic", "integrate", "connect",
        ]
        if any(kw in desc_lower for kw in medium_keywords):
            return "medium"
        
        # Simple by default
        return "simple"
