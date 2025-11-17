"""
Tests for Godot Security module.

This module tests the security validation, path checking, operation
risk assessment, and safeguard functionalities.
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from agents.tools.godot_security import (
    GodotSecurityValidator,
    SecurityContext,
    OperationRisk,
    ValidationResult,
    get_security_validator,
    set_security_context,
    create_default_security_context,
    validate_operation,
    validate_path,
    validate_node_name
)


class TestSecurityContext:
    """Test cases for SecurityContext class."""

    def test_security_context_initialization(self):
        """Test SecurityContext initialization."""
        context = SecurityContext("/test/project/path")

        assert context.project_path == "/test/project/path"
        assert context.allowed_operations == set()
        assert context.denied_operations == set()
        assert context.risk_threshold == OperationRisk.MEDIUM
        assert context.session_id is None

    def test_security_context_initialization_no_project(self):
        """Test SecurityContext initialization without project path."""
        context = SecurityContext()

        assert context.project_path is None

    def test_set_project_path(self):
        """Test setting project path."""
        context = SecurityContext()
        context.set_project_path("/new/project/path")

        assert context.project_path == "/new/project/path"

    def test_add_allowed_operation(self):
        """Test adding allowed operations."""
        context = SecurityContext()
        context.add_allowed_operation("create_node")
        context.add_allowed_operation("modify_node_property")

        assert "create_node" in context.allowed_operations
        assert "modify_node_property" in context.allowed_operations
        assert len(context.allowed_operations) == 2

    def test_add_denied_operation(self):
        """Test adding denied operations."""
        context = SecurityContext()
        context.add_denied_operation("delete_node")
        context.add_denied_operation("execute_custom_script")

        assert "delete_node" in context.denied_operations
        assert "execute_custom_script" in context.denied_operations
        assert len(context.denied_operations) == 2

    def test_set_risk_threshold(self):
        """Test setting risk threshold."""
        context = SecurityContext()
        context.set_risk_threshold(OperationRisk.LOW)

        assert context.risk_threshold == OperationRisk.LOW

    def test_set_risk_threshold_invalid(self):
        """Test setting invalid risk threshold."""
        context = SecurityContext()
        # Should accept any OperationRisk value
        context.set_risk_threshold(OperationRisk.CRITICAL)
        assert context.risk_threshold == OperationRisk.CRITICAL


class TestGodotSecurityValidator:
    """Test cases for GodotSecurityValidator class."""

    def test_validator_initialization(self):
        """Test GodotSecurityValidator initialization."""
        validator = GodotSecurityValidator()

        assert isinstance(validator.security_context, SecurityContext)
        assert len(validator.risky_operations) > 0
        assert len(validator.path_patterns) > 0
        assert len(validator.sensitive_extensions) > 0

    def test_set_security_context(self, mock_security_context):
        """Test setting security context."""
        validator = GodotSecurityValidator()
        validator.set_security_context(mock_security_context)

        assert validator.security_context is mock_security_context

    def test_validate_operation_allowed_explicitly(self, mock_security_context):
        """Test validating explicitly allowed operation."""
        validator = GodotSecurityValidator()
        mock_security_context.add_allowed_operation("create_node")
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation("create_node", {"node_type": "Node2D"})

        assert result.allowed is True
        assert result.reason is None

    def test_validate_operation_denied_explicitly(self, mock_security_context):
        """Test validating explicitly denied operation."""
        validator = GodotSecurityValidator()
        mock_security_context.add_denied_operation("delete_node")
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation("delete_node", {"node_path": "Root/Node"})

        assert result.allowed is False
        assert "explicitly denied" in result.reason
        assert result.risk_level == OperationRisk.HIGH

    def test_validate_operation_risk_allowed(self, mock_security_context):
        """Test validating operation within risk threshold."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.HIGH)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation("delete_node", {"node_path": "Root/Node"})

        assert result.allowed is True
        assert result.risk_level == OperationRisk.HIGH

    def test_validate_operation_risk_exceeds_threshold(self, mock_security_context):
        """Test validating operation exceeding risk threshold."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.LOW)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation("delete_node", {"node_path": "Root/Node"})

        assert result.allowed is False
        assert "exceeds allowed risk level" in result.reason
        assert result.risk_level == OperationRisk.HIGH

    def test_validate_operation_unknown_operation(self, mock_security_context):
        """Test validating unknown operation."""
        validator = GodotSecurityValidator()
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation("unknown_operation", {})

        assert result.allowed is True  # Unknown operations default to MEDIUM risk
        assert result.risk_level == OperationRisk.MEDIUM

    def test_validate_operation_with_warnings(self, mock_security_context):
        """Test operation validation with warnings."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation(
            "modify_node_property",
            {"node_path": "Root/Node", "property_name": "_private_property"}
        )

        assert result.allowed is True
        assert len(result.warnings) > 0
        assert any("private property" in warning for warning in result.warnings)

    def test_validate_path_valid_godot_path(self):
        """Test validating valid Godot path."""
        validator = GodotSecurityValidator()

        result = validator.validate_path("res://scenes/main.tscn", "godot_path")

        assert result.allowed is True
        assert len(result.warnings) == 0

    def test_validate_path_valid_user_path(self):
        """Test validating valid user path."""
        validator = GodotSecurityValidator()

        result = validator.validate_path("user://save_data.json", "user_path")

        assert result.allowed is True
        assert len(result.warnings) == 0

    def test_validate_path_invalid_pattern(self):
        """Test validating path with invalid pattern."""
        validator = GodotSecurityValidator()

        result = validator.validate_path("invalid|path", "godot_path")

        assert result.allowed is False
        assert "does not match expected pattern" in result.reason

    def test_validate_path_traversal_attempt(self):
        """Test validating path with directory traversal attempt."""
        validator = GodotSecurityValidator()

        result = validator.validate_path("res://../../../etc/passwd", "godot_path")

        assert result.allowed is False
        assert "directory traversal" in result.reason

    def test_validate_path_suspicious_characters(self):
        """Test validating path with suspicious characters."""
        validator = GodotSecurityValidator()

        result = validator.validate_path("res://scenes/scene<tscn", "godot_path")

        assert result.allowed is False
        assert "suspicious characters" in result.reason

    def test_validate_path_outside_project(self, mock_security_context):
        """Test validating path outside project directory."""
        validator = GodotSecurityValidator()
        mock_security_context.project_path = "/test/project"
        validator.set_security_context(mock_security_context)

        result = validator.validate_path("res://../../../outside/path/file.txt", "godot_path")

        assert result.allowed is True  # Path validation passes
        assert len(result.warnings) > 0
        assert any("outside the current project" in warning for warning in result.warnings)

    def test_validate_path_sensitive_extension(self):
        """Test validating path with sensitive file extension."""
        validator = GodotSecurityValidator()

        result = validator.validate_path("res://scripts/malware.exe", "godot_path")

        assert result.allowed is False
        assert "sensitive file type" in result.reason

    def test_validate_node_name_valid(self):
        """Test validating valid node name."""
        validator = GodotSecurityValidator()

        result = validator.validate_node_name("PlayerNode")

        assert result.allowed is True
        assert len(result.warnings) == 0

    def test_validate_node_name_empty(self):
        """Test validating empty node name."""
        validator = GodotSecurityValidator()

        result = validator.validate_node_name("")

        assert result.allowed is False
        assert "cannot be empty" in result.reason

    def test_validate_node_name_too_long(self):
        """Test validating node name that's too long."""
        validator = GodotSecurityValidator()

        long_name = "A" * 65  # Over 64 character limit
        result = validator.validate_node_name(long_name)

        assert result.allowed is False
        assert "too long" in result.reason

    def test_validate_node_name_invalid_characters(self):
        """Test validating node name with invalid characters."""
        validator = GodotSecurityValidator()

        result = validator.validate_node_name("Node/With/Slashes")

        assert result.allowed is False
        assert "invalid characters" in result.reason

    def test_validate_node_name_reserved(self):
        """Test validating reserved node name."""
        validator = GodotSecurityValidator()

        result = validator.validate_node_name("root")

        assert result.allowed is False
        assert "reserved" in result.reason

    def test_validate_scene_name_valid(self):
        """Test validating valid scene name."""
        validator = GodotSecurityValidator()

        result = validator.validate_scene_name("MainScene")

        assert result.allowed is True
        assert len(result.warnings) == 0

    def test_validate_scene_name_with_extension(self):
        """Test validating scene name with .tscn extension."""
        validator = GodotSecurityValidator()

        result = validator.validate_scene_name("Level1.tscn")

        assert result.allowed is True

    def test_validate_scene_name_empty(self):
        """Test validating empty scene name."""
        validator = GodotSecurityValidator()

        result = validator.validate_scene_name("")

        assert result.allowed is False
        assert "cannot be empty" in result.reason

    def test_validate_scene_name_invalid_characters(self):
        """Test validating scene name with invalid characters."""
        validator = GodotSecurityValidator()

        result = validator.validate_scene_name("Scene<With>Brackets")

        assert result.allowed is False
        assert "invalid characters" in result.reason

    def test_validate_operation_parameters_node_path(self, mock_security_context):
        """Test validating operation with node path parameter."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation(
            "create_node",
            {"node_path": "Root/Invalid/Path/With/../Traversal"}
        )

        assert result.allowed is False
        assert "directory traversal" in result.reason

    def test_validate_operation_parameters_scene_path(self, mock_security_context):
        """Test validating operation with scene path parameter."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation(
            "open_scene",
            {"scene_path": "res://invalid<path"}
        )

        assert result.allowed is False
        assert "invalid characters" in result.reason

    def test_validate_operation_parameters_node_name(self, mock_security_context):
        """Test validating operation with node name parameter."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation(
            "create_node",
            {"node_name": "Invalid/Name/With/Slashes"}
        )

        assert result.allowed is False
        assert "invalid characters" in result.reason

    def test_validate_operation_parameters_scene_name(self, mock_security_context):
        """Test validating operation with scene name parameter."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation(
            "create_scene",
            {"scene_name": "Invalid<Name>"}
        )

        assert result.allowed is False
        assert "invalid characters" in result.reason

    def test_check_operation_security_delete_warning(self, mock_security_context):
        """Test security warning for delete operation."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation("delete_node", {"node_path": "Root/Node"})

        assert result.allowed is True
        assert any("cannot be undone" in warning for warning in result.warnings)

    def test_check_operation_security_private_property_warning(self, mock_security_context):
        """Test security warning for private property modification."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation(
            "modify_node_property",
            {"node_path": "Root/Node", "property_name": "_private_var"}
        )

        assert result.allowed is True
        assert any("private property" in warning for warning in result.warnings)

    def test_check_operation_security_script_node_warning(self, mock_security_context):
        """Test security warning for script node creation."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)
        validator.set_security_context(mock_security_context)

        result = validator.validate_operation(
            "create_node",
            {"node_type": "GDScript"}
        )

        assert result.allowed is True
        assert any("script nodes" in warning for warning in result.warnings)

    def test_is_risk_allowed_true(self, mock_security_context):
        """Test risk checking when risk is allowed."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.HIGH)
        validator.set_security_context(mock_security_context)

        result = validator._is_risk_allowed(OperationRisk.MEDIUM)

        assert result is True

    def test_is_risk_allowed_false(self, mock_security_context):
        """Test risk checking when risk exceeds threshold."""
        validator = GodotSecurityValidator()
        mock_security_context.set_risk_threshold(OperationRisk.LOW)
        validator.set_security_context(mock_security_context)

        result = validator._is_risk_allowed(OperationRisk.HIGH)

        assert result is False

    def test_validate_node_path_valid(self):
        """Test validating valid node path."""
        validator = GodotSecurityValidator()

        result = validator._validate_node_path("Root/Player/Sprite")

        assert result.allowed is True

    def test_validate_node_path_empty(self):
        """Test validating empty node path."""
        validator = GodotSecurityValidator()

        result = validator._validate_node_path("")

        assert result.allowed is False
        assert "cannot be empty" in result.reason

    def test_validate_node_path_traversal(self):
        """Test validating node path with traversal."""
        validator = GodotSecurityValidator()

        result = validator._validate_node_path("Root/../Outside")

        assert result.allowed is False
        assert "directory traversal" in result.reason

    def test_validate_node_path_invalid_characters(self):
        """Test validating node path with invalid characters."""
        validator = GodotSecurityValidator()

        result = validator._validate_node_path("Root<Node>")

        assert result.allowed is False
        assert "invalid characters" in result.reason

    def test_godot_path_to_absolute_valid(self):
        """Test converting Godot path to absolute path."""
        validator = GodotSecurityValidator()
        validator.security_context.project_path = "/test/project"

        result = validator._godot_path_to_absolute("res://scenes/main.tscn")

        assert result == "/test/project/scenes/main.tscn"

    def test_godot_path_to_absolute_no_project(self):
        """Test converting Godot path without project set."""
        validator = GodotSecurityValidator()

        result = validator._godot_path_to_absolute("res://scenes/main.tscn")

        assert result == "res://scenes/main.tscn"

    def test_godot_path_to_absolute_not_godot_path(self):
        """Test converting non-Godot path."""
        validator = GodotSecurityValidator()

        result = validator._godot_path_to_absolute("/absolute/path/file.txt")

        assert result == "/absolute/path/file.txt"

    def test_is_path_within_project_true(self):
        """Test checking if path is within project directory."""
        validator = GodotSecurityValidator()
        validator.security_context.project_path = "/test/project"

        result = validator._is_path_within_project("/test/project/scenes/level1.tscn")

        assert result is True

    def test_is_path_within_project_false(self):
        """Test checking if path is outside project directory."""
        validator = GodotSecurityValidator()
        validator.security_context.project_path = "/test/project"

        result = validator._is_path_within_project("/other/project/file.txt")

        assert result is False

    def test_is_path_within_project_no_project(self):
        """Test path within project check when no project set."""
        validator = GodotSecurityValidator()
        validator.security_context.project_path = None

        result = validator._is_path_within_project("/any/path/file.txt")

        assert result is True


class TestGlobalFunctions:
    """Test cases for global security functions."""

    def test_get_security_validator_singleton(self):
        """Test that get_security_validator returns singleton."""
        validator1 = get_security_validator()
        validator2 = get_security_validator()

        assert validator1 is validator2

    def test_set_security_context(self, mock_security_context):
        """Test setting global security context."""
        validator = get_security_validator()
        original_context = validator.security_context

        set_security_context(mock_security_context)

        assert validator.security_context is mock_security_context

        # Restore original context
        validator.security_context = original_context

    def test_create_default_security_context(self):
        """Test creating default security context."""
        context = create_default_security_context("/test/project")

        assert context.project_path == "/test/project"
        assert context.risk_threshold == OperationRisk.MEDIUM

        # Should have safe operations allowed
        assert "get_project_info" in context.allowed_operations
        assert "get_scene_tree" in context.allowed_operations
        assert "capture_screenshot" in context.allowed_operations

    def test_create_default_security_context_no_project(self):
        """Test creating default security context without project."""
        context = create_default_security_context()

        assert context.project_path is None
        assert context.risk_threshold == OperationRisk.MEDIUM

    def test_validate_operation_function(self, mock_security_context):
        """Test validate_operation convenience function."""
        mock_security_context.set_risk_threshold(OperationRisk.CRITICAL)

        with patch('agents.tools.godot_security.get_security_validator') as mock_get_validator:
            mock_validator = MagicMock()
            mock_validator.validate_operation.return_value = ValidationResult(allowed=True)
            mock_get_validator.return_value = mock_validator

            set_security_context(mock_security_context)

            result = validate_operation("create_node", {"node_type": "Node2D"})

            assert result.allowed is True
            mock_validator.validate_operation.assert_called_once_with(
                "create_node",
                {"node_type": "Node2D"}
            )

    def test_validate_path_function(self):
        """Test validate_path convenience function."""
        with patch('agents.tools.godot_security.get_security_validator') as mock_get_validator:
            mock_validator = MagicMock()
            mock_validator.validate_path.return_value = ValidationResult(allowed=True)
            mock_get_validator.return_value = mock_validator

            result = validate_path("res://scenes/main.tscn", "godot_path")

            assert result.allowed is True
            mock_validator.validate_path.assert_called_once_with(
                "res://scenes/main.tscn",
                "godot_path"
            )

    def test_validate_node_name_function(self):
        """Test validate_node_name convenience function."""
        with patch('agents.tools.godot_security.get_security_validator') as mock_get_validator:
            mock_validator = MagicMock()
            mock_validator.validate_node_name.return_value = ValidationResult(allowed=True)
            mock_get_validator.return_value = mock_validator

            result = validate_node_name("PlayerNode")

            assert result.allowed is True
            mock_validator.validate_node_name.assert_called_once_with("PlayerNode")


class TestOperationRisk:
    """Test cases for OperationRisk enum."""

    def test_operation_risk_values(self):
        """Test OperationRisk enum values."""
        assert OperationRisk.SAFE.value == "safe"
        assert OperationRisk.LOW.value == "low"
        assert OperationRisk.MEDIUM.value == "medium"
        assert OperationRisk.HIGH.value == "high"
        assert OperationRisk.CRITICAL.value == "critical"

    def test_operation_risk_comparison(self):
        """Test OperationRisk comparison."""
        assert OperationRisk.SAFE == OperationRisk.SAFE
        assert OperationRisk.LOW != OperationRisk.MEDIUM

    def test_operation_risk_ordering(self):
        """Test that risk levels have logical ordering."""
        risks = [OperationRisk.SAFE, OperationRisk.LOW, OperationRisk.MEDIUM,
                 OperationRisk.HIGH, OperationRisk.CRITICAL]

        # All risk levels should be unique
        assert len(set(risks)) == len(risks)

        # Should be able to compare them in some logical way
        assert OperationRisk.SAFE != OperationRisk.CRITICAL


class TestValidationResult:
    """Test cases for ValidationResult class."""

    def test_validation_result_success(self):
        """Test ValidationResult for successful validation."""
        result = ValidationResult(allowed=True)

        assert result.allowed is True
        assert result.reason is None
        assert result.risk_level == OperationRisk.SAFE
        assert result.warnings == []

    def test_validation_result_failure(self):
        """Test ValidationResult for failed validation."""
        result = ValidationResult(
            allowed=False,
            reason="Path validation failed",
            risk_level=OperationRisk.HIGH,
            warnings=["Warning 1", "Warning 2"]
        )

        assert result.allowed is False
        assert result.reason == "Path validation failed"
        assert result.risk_level == OperationRisk.HIGH
        assert result.warnings == ["Warning 1", "Warning 2"]

    def test_validation_result_warnings_post_init(self):
        """Test ValidationResult warnings post-init."""
        result = ValidationResult(allowed=True, warnings=None)

        assert result.warnings == []

    def test_validation_result_with_warnings(self):
        """Test ValidationResult with warnings provided."""
        warnings = ["Warning 1", "Warning 2"]
        result = ValidationResult(allowed=True, warnings=warnings)

        assert result.warnings == warnings


class TestRiskLevels:
    """Test cases for risk level classifications."""

    def test_safe_operations(self):
        """Test that safe operations are properly classified."""
        validator = GodotSecurityValidator()

        safe_ops = [
            "get_project_info",
            "get_scene_tree",
            "get_node_info",
            "search_nodes",
            "get_viewport_info",
            "capture_screenshot",
            "get_debug_output",
            "get_performance_metrics"
        ]

        for op in safe_ops:
            assert validator.risky_operations.get(op) == OperationRisk.SAFE

    def test_low_risk_operations(self):
        """Test that low risk operations are properly classified."""
        validator = GodotSecurityValidator()

        low_risk_ops = [
            "select_nodes",
            "focus_node",
            "play_scene",
            "stop_playing",
            "inspect_scene_file"
        ]

        for op in low_risk_ops:
            assert validator.risky_operations.get(op) == OperationRisk.LOW

    def test_medium_risk_operations(self):
        """Test that medium risk operations are properly classified."""
        validator = GodotSecurityValidator()

        medium_risk_ops = [
            "create_node",
            "modify_node_property",
            "reparent_node",
            "create_scene",
            "open_scene",
            "save_scene",
            "duplicate_node"
        ]

        for op in medium_risk_ops:
            assert validator.risky_operations.get(op) == OperationRisk.MEDIUM

    def test_high_risk_operations(self):
        """Test that high risk operations are properly classified."""
        validator = GodotSecurityValidator()

        high_risk_ops = [
            "delete_node",
            "modify_script",
            "import_resource",
            "export_project"
        ]

        for op in high_risk_ops:
            assert validator.risky_operations.get(op) == OperationRisk.HIGH

    def test_critical_risk_operations(self):
        """Test that critical risk operations are properly classified."""
        validator = GodotSecurityValidator()

        critical_risk_ops = [
            "delete_scene",
            "modify_project_settings",
            "execute_custom_script",
            "modify_file_system"
        ]

        for op in critical_risk_ops:
            assert validator.risky_operations.get(op) == OperationRisk.CRITICAL


class TestPathPatterns:
    """Test cases for path validation patterns."""

    def test_godot_path_pattern_valid(self):
        """Test Godot path pattern validation."""
        validator = GodotSecurityValidator()
        pattern = validator.path_patterns["godot_path"]

        # Valid paths
        assert pattern.match("res://scenes/main.tscn")
        assert pattern.match("res://scripts/player.gd")
        assert pattern.match("res://")
        assert pattern.match("res://assets/textures/player.png")

        # Invalid paths
        assert not pattern.match("res://scenes/invalid<name>.tscn")
        assert not pattern.match("res://scenes/invalid|name.tscn")
        assert not pattern.match("res://scenes/invalid name.tscn")

    def test_user_path_pattern_valid(self):
        """Test user path pattern validation."""
        validator = GodotSecurityValidator()
        pattern = validator.path_patterns["user_path"]

        # Valid paths
        assert pattern.match("user://save_data.json")
        assert pattern.match("user://screenshots/screenshot.png")
        assert pattern.match("user://")

        # Invalid paths
        assert not pattern.match("user://invalid<name>.json")

    def test_node_path_pattern_valid(self):
        """Test node path pattern validation."""
        validator = GodotSecurityValidator()
        pattern = validator.path_patterns["node_path"]

        # Valid paths
        assert pattern.match("Root")
        assert pattern.match("Root/Player")
        assert pattern.match("Root/Player/Sprite2D")
        assert pattern.match("NodeWith_123_Numbers")

        # Invalid paths
        assert not pattern.match("Root/Invalid/Path")
        assert not pattern.match("Root<Invalid>Node")
        assert not pattern.match("Root/Invalid Node")

    def test_scene_name_pattern_valid(self):
        """Test scene name pattern validation."""
        validator = GodotSecurityValidator()
        pattern = validator.path_patterns["scene_name"]

        # Valid names
        assert pattern.match("MainScene")
        assert pattern.match("Level1")
        assert pattern.match("scene_with_underscores")
        assert pattern.match("scene-with-dashes")
        assert pattern.match("Scene123")

        # Invalid names
        assert not pattern.match("Scene<Invalid>")
        assert not pattern.match("Scene|Invalid")
        assert not pattern.match("Scene With Spaces")

    def test_node_name_pattern_valid(self):
        """Test node name pattern validation."""
        validator = GodotSecurityValidator()
        pattern = validator.path_patterns["node_name"]

        # Valid names
        assert pattern.match("Player")
        assert pattern.match("Node2D")
        assert pattern.match("Camera_2D")
        assert pattern.match("Node123")

        # Invalid names
        assert not pattern.match("Node<Invalid>")
        assert not pattern.match("Node|Invalid")
        assert not pattern.match("Node With Spaces")


class TestSensitiveExtensions:
    """Test cases for sensitive file extension detection."""

    def test_sensitive_extensions_executables(self):
        """Test detection of executable file extensions."""
        validator = GodotSecurityValidator()

        assert ".exe" in validator.sensitive_extensions
        assert ".dll" in validator.sensitive_extensions
        assert ".so" in validator.sensitive_extensions
        assert ".dylib" in validator.sensitive_extensions

    def test_sensitive_extensions_scripts(self):
        """Test detection of script file extensions."""
        validator = GodotSecurityValidator()

        assert ".bat" in validator.sensitive_extensions
        assert ".cmd" in validator.sensitive_extensions
        assert ".sh" in validator.sensitive_extensions
        assert ".ps1" in validator.sensitive_extensions
        assert ".vbs" in validator.sensitive_extensions
        assert ".js" in validator.sensitive_extensions

    def test_sensitive_extensions_system(self):
        """Test detection of system file extensions."""
        validator = GodotSecurityValidator()

        assert ".reg" in validator.sensitive_extensions
        assert ".msi" in validator.sensitive_extensions
        assert ".deb" in validator.sensitive_extensions
        assert ".rpm" in validator.sensitive_extensions

    def test_sensitive_extensions_certificates(self):
        """Test detection of certificate file extensions."""
        validator = GodotSecurityValidator()

        assert ".key" in validator.sensitive_extensions
        assert ".pem" in validator.sensitive_extensions
        assert ".crt" in validator.sensitive_extensions
        assert ".p12" in validator.sensitive_extensions