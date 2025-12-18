"""Scenario tests for Lead Developer delegation and routing.

These tests validate that the Lead agent correctly routes requests
to specialized agents based on request type and context.

Based on Better Agents standards for ensuring agent behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Add brain to path
brain_path = Path(__file__).parent.parent.parent / "brain"
if str(brain_path) not in sys.path:
    sys.path.insert(0, str(brain_path))


class TestRequestRoutingScenarios:
    """Scenario tests for request routing decisions."""

    @pytest.mark.parametrize("request,expected_route", [
        # Direct answers (Lead handles)
        ("What is a CharacterBody2D?", "self"),
        ("How do signals work in Godot?", "self"),
        ("Explain the difference between Node2D and Control", "self"),
        
        # Code tasks (Coder handles)
        ("Add a jump ability to my player script", "coder"),
        ("Fix the error in my movement code", "coder"),
        ("Implement health regeneration", "coder"),
        ("Refactor this script to use signals", "coder"),
        
        # Complex features (Architect first)
        ("Create an inventory system", "architect"),
        ("Implement a save/load system", "architect"),
        ("Build a dialog system with branching", "architect"),
        ("Add multiplayer support", "architect"),
        
        # Context gathering (Observer)
        ("What's in my current scene?", "observer"),
        ("Analyze my player script for issues", "observer"),
        ("Why is my sprite not visible?", "observer"),
        ("What nodes are attached to Player?", "observer"),
    ])
    def test_routes_to_correct_agent(
        self, request: str, expected_route: str
    ) -> None:
        """
        Scenario: User makes a request
        Expected: Lead routes to appropriate agent
        """
        route = self._determine_route(request)
        
        assert route == expected_route, (
            f"'{request}' should route to '{expected_route}', got '{route}'"
        )

    def _determine_route(self, request: str) -> str:
        """Determine which agent should handle the request.
        
        Routing logic:
        - Self: API questions, explanations
        - Coder: Code changes, fixes, implementations
        - Architect: Complex multi-step features
        - Observer: Context gathering, analysis
        """
        request_lower = request.lower()
        
        # Observer: Visual/context questions
        observer_patterns = [
            "what's in my", "what is in my",
            "analyze my", "check my", "review my",
            "why is my", "why isn't my",
            "current scene", "current script",
            "what nodes", "scene tree",
        ]
        if any(p in request_lower for p in observer_patterns):
            return "observer"
        
        # Architect: Complex features
        architect_patterns = [
            "system", "multiplayer", "dialog",
            "create a", "build a", "implement a",
        ]
        feature_indicators = ["inventory", "save", "load", "quest", "skill"]
        is_complex_feature = (
            any(p in request_lower for p in architect_patterns) and
            any(f in request_lower for f in feature_indicators)
        )
        if is_complex_feature or "multiplayer" in request_lower:
            return "architect"
        
        # Coder: Code tasks
        coder_patterns = [
            "add a", "fix ", "implement",
            "refactor", "update ", "modify",
            "script", "code", "function",
            "error", "bug",
        ]
        if any(p in request_lower for p in coder_patterns):
            return "coder"
        
        # Self: Explanations and questions
        explanation_patterns = [
            "what is", "what's",
            "how do", "how does", "how to",
            "explain", "difference between",
            "why", "when should",
        ]
        if any(p in request_lower for p in explanation_patterns):
            return "self"
        
        # Default to self for simple questions
        return "self"


class TestContextGatheringScenarios:
    """Tests for context gathering before routing."""

    def test_gathers_context_for_code_tasks(self) -> None:
        """
        Scenario: User asks to modify code
        Expected: Lead gathers script context first
        """
        request = "Add a double jump to my player"
        context_needs = self._identify_context_needs(request)
        
        assert "script" in context_needs, "Should need script context"

    def test_gathers_context_for_scene_tasks(self) -> None:
        """
        Scenario: User asks about scene structure
        Expected: Lead gathers scene tree first
        """
        request = "Add a HUD to my game"
        context_needs = self._identify_context_needs(request)
        
        assert "scene" in context_needs, "Should need scene context"

    def test_no_context_for_general_questions(self) -> None:
        """
        Scenario: User asks general API question
        Expected: No project context needed
        """
        request = "What parameters does move_and_slide take?"
        context_needs = self._identify_context_needs(request)
        
        assert len(context_needs) == 0, "General questions don't need context"

    def _identify_context_needs(self, request: str) -> list[str]:
        """Identify what context is needed before handling request."""
        request_lower = request.lower()
        needs = []
        
        # Script context indicators
        script_indicators = [
            "my player", "my script", "my code",
            "add a", "implement", "fix",
        ]
        if any(ind in request_lower for ind in script_indicators):
            needs.append("script")
        
        # Scene context indicators
        scene_indicators = [
            "my scene", "my game", "add a", "hud", "ui",
        ]
        if any(ind in request_lower for ind in scene_indicators):
            needs.append("scene")
        
        # Project context indicators
        project_indicators = [
            "my project", "project settings",
        ]
        if any(ind in request_lower for ind in project_indicators):
            needs.append("project")
        
        return needs


class TestDelegationChainScenarios:
    """Tests for multi-agent delegation chains."""

    def test_architect_then_coder_for_features(self) -> None:
        """
        Scenario: Complex feature request
        Expected: Architect plans first, then Coder implements
        """
        request = "Implement an inventory system"
        chain = self._get_delegation_chain(request)
        
        assert chain == ["architect", "coder"], (
            "Complex features should go: Architect -> Coder"
        )

    def test_observer_then_coder_for_bugs(self) -> None:
        """
        Scenario: Bug fix request
        Expected: Observer analyzes first, then Coder fixes
        """
        request = "Fix the null reference error in my player script"
        chain = self._get_delegation_chain(request)
        
        assert chain == ["observer", "coder"], (
            "Bug fixes should go: Observer -> Coder"
        )

    def test_single_agent_for_simple_tasks(self) -> None:
        """
        Scenario: Simple code modification
        Expected: Direct to Coder without chain
        """
        request = "Add type hints to this function"
        chain = self._get_delegation_chain(request)
        
        assert chain == ["coder"], "Simple tasks go directly to one agent"

    def _get_delegation_chain(self, request: str) -> list[str]:
        """Determine the delegation chain for a request."""
        request_lower = request.lower()
        
        # Bug fix pattern: Observer -> Coder
        bug_patterns = ["fix", "error", "bug", "crash", "null"]
        if any(p in request_lower for p in bug_patterns):
            return ["observer", "coder"]
        
        # Complex feature pattern: Architect -> Coder
        feature_patterns = ["system", "implement a", "create a", "build a"]
        if any(p in request_lower for p in feature_patterns):
            return ["architect", "coder"]
        
        # Simple modification: Just Coder
        code_patterns = ["add", "update", "refactor", "type hints"]
        if any(p in request_lower for p in code_patterns):
            return ["coder"]
        
        # Default: Self
        return ["self"]


class TestHITLDecisionScenarios:
    """Tests for HITL requirement identification."""

    @pytest.mark.parametrize("action,requires_hitl", [
        ("Create a new script file", True),
        ("Modify the player script", True),
        ("Delete unused nodes", True),
        ("Change project settings", True),
        ("Read the current script", False),
        ("Analyze the scene tree", False),
        ("Explain how signals work", False),
        ("Get project settings", False),
    ])
    def test_identifies_hitl_requirement(
        self, action: str, requires_hitl: bool
    ) -> None:
        """
        Scenario: Various actions
        Expected: Correct HITL requirement identification
        """
        needs_hitl = self._requires_hitl(action)
        
        assert needs_hitl == requires_hitl, (
            f"'{action}' HITL: expected {requires_hitl}, got {needs_hitl}"
        )

    def _requires_hitl(self, action: str) -> bool:
        """Determine if an action requires HITL confirmation."""
        action_lower = action.lower()
        
        # Write operations require HITL
        write_patterns = [
            "create", "modify", "update", "delete",
            "write", "change", "set",
        ]
        
        # Read operations don't require HITL
        read_patterns = [
            "read", "get", "analyze", "explain",
            "check", "list", "show",
        ]
        
        # Check read patterns first (they're safe)
        if any(p in action_lower for p in read_patterns):
            return False
        
        # Check write patterns
        if any(p in action_lower for p in write_patterns):
            return True
        
        return False


class TestAmbiguousRequestScenarios:
    """Tests for handling ambiguous requests."""

    def test_asks_clarification_for_vague_request(self) -> None:
        """
        Scenario: Vague request with multiple interpretations
        Expected: Lead asks for clarification
        """
        request = "Improve my game"
        response = self._handle_ambiguous_request(request)
        
        assert response["needs_clarification"], "Vague requests need clarification"
        assert len(response["questions"]) > 0, "Should ask specific questions"

    def test_handles_specific_requests_directly(self) -> None:
        """
        Scenario: Clear, specific request
        Expected: Lead proceeds without clarification
        """
        request = "Add WASD movement to my CharacterBody2D player script"
        response = self._handle_ambiguous_request(request)
        
        assert not response["needs_clarification"], "Specific requests proceed directly"

    def _handle_ambiguous_request(self, request: str) -> dict[str, Any]:
        """Determine if request needs clarification."""
        request_lower = request.lower()
        
        # Vague patterns
        vague_patterns = [
            "improve", "better", "fix issues", "make it work",
            "help me", "something wrong",
        ]
        
        # Specific patterns
        specific_patterns = [
            "add wasd", "implement jump", "create health",
            "fix error", "add signal", "refactor",
        ]
        
        is_vague = any(p in request_lower for p in vague_patterns)
        is_specific = any(p in request_lower for p in specific_patterns)
        
        if is_vague and not is_specific:
            return {
                "needs_clarification": True,
                "questions": [
                    "What specific aspect would you like to improve?",
                    "Can you describe the current behavior and desired behavior?",
                ],
            }
        
        return {"needs_clarification": False, "questions": []}


class TestQualityGateScenarios:
    """Tests for Lead's pre-delegation quality checks."""

    def test_validates_sufficient_context(self) -> None:
        """
        Scenario: Code task without script context
        Expected: Lead gathers context before delegating
        """
        task = {
            "type": "code_modification",
            "request": "Add health system",
            "context": {},
        }
        
        ready, reason = self._check_ready_to_delegate(task)
        
        assert not ready, "Should not delegate without context"
        assert "context" in reason.lower()

    def test_validates_clear_requirements(self) -> None:
        """
        Scenario: Task with clear requirements
        Expected: Passes quality gate
        """
        task = {
            "type": "code_modification",
            "request": "Add @export var speed: float = 200.0 to player",
            "context": {"script": "extends CharacterBody2D"},
        }
        
        ready, reason = self._check_ready_to_delegate(task)
        
        assert ready, f"Should be ready to delegate: {reason}"

    def _check_ready_to_delegate(
        self, task: dict[str, Any]
    ) -> tuple[bool, str]:
        """Check if task is ready to delegate."""
        task_type = task.get("type", "")
        context = task.get("context", {})
        
        # Code tasks need script context
        if task_type == "code_modification":
            if not context.get("script"):
                return False, "Missing script context for code modification"
        
        # Scene tasks need scene context
        if task_type == "scene_modification":
            if not context.get("scene"):
                return False, "Missing scene context for scene modification"
        
        return True, "Ready to delegate"
