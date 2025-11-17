"""
Security and validation module for Godot integration.

This module provides security features, path validation, and operation
safeguards for Godot agent tools to ensure safe and controlled interactions.
"""

import os
import pathlib
import re
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from strands import tool
from ..config import AgentConfig

logger = logging.getLogger(__name__)


class OperationRisk(Enum):
    """Risk levels for Godot operations."""
    SAFE = "safe"          # Read-only operations
    LOW = "low"            # Non-destructive modifications
    MEDIUM = "medium"      # Modifications that can be undone
    HIGH = "high"          # Destructive operations
    CRITICAL = "critical"  # Potentially dangerous operations


class SecurityContext:
    """Security context for Godot operations."""

    def __init__(self, project_path: Optional[str] = None):
        """
        Initialize security context.

        Args:
            project_path: Current Godot project path for validation
        """
        self.project_path = project_path
        self.allowed_operations: Set[str] = set()
        self.denied_operations: Set[str] = set()
        self.risk_threshold = OperationRisk.MEDIUM
        self.session_id = None

    def set_project_path(self, project_path: str):
        """Set the current project path."""
        self.project_path = project_path
        logger.info(f"Security context: Project path set to {project_path}")

    def add_allowed_operation(self, operation: str):
        """Add an operation to the allowed list."""
        self.allowed_operations.add(operation)
        logger.debug(f"Security context: Allowed operation '{operation}'")

    def add_denied_operation(self, operation: str):
        """Add an operation to the denied list."""
        self.denied_operations.add(operation)
        logger.debug(f"Security context: Denied operation '{operation}'")

    def set_risk_threshold(self, threshold: OperationRisk):
        """Set maximum allowed risk level."""
        self.risk_threshold = threshold
        logger.info(f"Security context: Risk threshold set to {threshold.value}")


@dataclass
class ValidationResult:
    """Result of a security validation."""
    allowed: bool
    reason: Optional[str] = None
    risk_level: OperationRisk = OperationRisk.SAFE
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class GodotSecurityValidator:
    """
    Security validator for Godot operations.

    Provides path validation, operation risk assessment, and security checks
    to ensure safe interactions with Godot projects.
    """

    def __init__(self):
        """Initialize security validator."""
        self.security_context = SecurityContext()
        self.risky_operations = self._initialize_risk_levels()
        self.path_patterns = self._initialize_path_patterns()
        self.sensitive_extensions = self._initialize_sensitive_extensions()

    def _initialize_risk_levels(self) -> Dict[str, OperationRisk]:
        """Initialize risk levels for different operations."""
        return {
            # Read operations - SAFE
            "get_project_info": OperationRisk.SAFE,
            "get_scene_tree": OperationRisk.SAFE,
            "get_node_info": OperationRisk.SAFE,
            "search_nodes": OperationRisk.SAFE,
            "get_viewport_info": OperationRisk.SAFE,
            "capture_screenshot": OperationRisk.SAFE,
            "get_debug_output": OperationRisk.SAFE,
            "get_performance_metrics": OperationRisk.SAFE,

            # Low risk operations - LOW
            "select_nodes": OperationRisk.LOW,
            "focus_node": OperationRisk.LOW,
            "play_scene": OperationRisk.LOW,
            "stop_playing": OperationRisk.LOW,
            "inspect_scene_file": OperationRisk.LOW,

            # Medium risk operations - MEDIUM
            "create_node": OperationRisk.MEDIUM,
            "modify_node_property": OperationRisk.MEDIUM,
            "reparent_node": OperationRisk.MEDIUM,
            "create_scene": OperationRisk.MEDIUM,
            "open_scene": OperationRisk.MEDIUM,
            "save_scene": OperationRisk.MEDIUM,
            "duplicate_node": OperationRisk.MEDIUM,

            # High risk operations - HIGH
            "delete_node": OperationRisk.HIGH,
            "modify_script": OperationRisk.HIGH,
            "import_resource": OperationRisk.HIGH,
            "export_project": OperationRisk.HIGH,

            # Critical risk operations - CRITICAL
            "delete_scene": OperationRisk.CRITICAL,
            "modify_project_settings": OperationRisk.CRITICAL,
            "execute_custom_script": OperationRisk.CRITICAL,
            "modify_file_system": OperationRisk.CRITICAL,
        }

    def _initialize_path_patterns(self) -> Dict[str, re.Pattern]:
        """Initialize regex patterns for path validation."""
        return {
            "godot_path": re.compile(r'^res://([a-zA-Z0-9_\-/]+(\.[a-zA-Z0-9_\-]+)?)?$'),
            "user_path": re.compile(r'^user://([a-zA-Z0-9_\-/]+(\.[a-zA-Z0-9_\-]+)?)?$'),
            "node_path": re.compile(r'^([A-Za-z0-9_\-]+/)*[A-Za-z0-9_\-]+$'),
            "scene_name": re.compile(r'^[a-zA-Z0-9_\-\.]+$'),
            "node_name": re.compile(r'^[a-zA-Z0-9_\-]+$'),
        }

    def _initialize_sensitive_extensions(self) -> Set[str]:
        """Initialize set of sensitive file extensions."""
        return {
            ".exe", ".dll", ".so", ".dylib",  # Executables
            ".bat", ".cmd", ".sh", ".ps1",    # Scripts
            ".scr", ".vbs", ".js", ".jar",    # Script files
            ".reg", ".msi", ".deb", ".rpm",   # System files
            ".key", ".pem", ".crt", ".p12",   # Certificates/Keys
            ".wallet", ".json",  # Wallet files
        }

    def set_security_context(self, context: SecurityContext):
        """Set the security context for validation."""
        self.security_context = context

    def validate_operation(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        Validate a Godot operation for security.

        Args:
            operation: Operation name to validate
            parameters: Operation parameters to validate

        Returns:
            ValidationResult with validation outcome
        """
        parameters = parameters or {}

        # Check if operation is explicitly denied
        if operation in self.security_context.denied_operations:
            return ValidationResult(
                allowed=False,
                reason=f"Operation '{operation}' is explicitly denied by security policy"
            )

        # Check if operation is explicitly allowed
        if operation in self.security_context.allowed_operations:
            return ValidationResult(allowed=True)

        # Get risk level for operation
        risk_level = self.risky_operations.get(operation, OperationRisk.MEDIUM)

        # Check if operation exceeds risk threshold
        if not self._is_risk_allowed(risk_level):
            return ValidationResult(
                allowed=False,
                reason=f"Operation '{operation}' exceeds allowed risk level ({risk_level.value} > {self.security_context.risk_threshold.value})",
                risk_level=risk_level
            )

        # Validate operation-specific parameters
        validation_result = self._validate_operation_parameters(operation, parameters, risk_level)
        if not validation_result.allowed:
            return validation_result

        # Additional security checks
        security_warnings = self._check_operation_security(operation, parameters)
        validation_result.warnings.extend(security_warnings)

        return ValidationResult(
            allowed=True,
            risk_level=risk_level,
            warnings=validation_result.warnings
        )

    def validate_path(self, path: str, path_type: str = "godot_path") -> ValidationResult:
        """
        Validate a file path for security.

        Args:
            path: Path to validate
            path_type: Type of path ("godot_path", "user_path", "absolute")

        Returns:
            ValidationResult with validation outcome
        """
        warnings = []

        # Check path patterns
        if path_type in self.path_patterns:
            pattern = self.path_patterns[path_type]
            if not pattern.match(path):
                return ValidationResult(
                    allowed=False,
                    reason=f"Path '{path}' does not match expected pattern for {path_type}"
                )

        # Check for path traversal attempts
        if ".." in path:
            return ValidationResult(
                allowed=False,
                reason="Path contains directory traversal characters ('..')"
            )

        # Check for suspicious characters
        suspicious_chars = ["<", ">", "|", "\"", "\0"]
        if any(char in path for char in suspicious_chars):
            return ValidationResult(
                allowed=False,
                reason=f"Path contains suspicious characters: {suspicious_chars}"
            )

        # Validate against project path if set
        if self.security_context.project_path:
            if path_type == "godot_path" and path.startswith("res://"):
                # Convert to absolute path for validation
                absolute_path = self._godot_path_to_absolute(path)
                if not self._is_path_within_project(absolute_path):
                    warnings.append(f"Path '{path}' is outside the current project directory")

        # Check for sensitive file extensions
        path_lower = path.lower()
        for ext in self.sensitive_extensions:
            if path_lower.endswith(ext):
                return ValidationResult(
                    allowed=False,
                    reason=f"Path '{path}' references a sensitive file type (.{ext})"
                )

        return ValidationResult(allowed=True, warnings=warnings)

    def validate_node_name(self, node_name: str) -> ValidationResult:
        """
        Validate a node name for security.

        Args:
            node_name: Node name to validate

        Returns:
            ValidationResult with validation outcome
        """
        if not node_name:
            return ValidationResult(allowed=False, reason="Node name cannot be empty")

        # Check length
        if len(node_name) > 64:
            return ValidationResult(
                allowed=False,
                reason="Node name is too long (maximum 64 characters)"
            )

        # Check pattern
        if not self.path_patterns["node_name"].match(node_name):
            return ValidationResult(
                allowed=False,
                reason="Node name contains invalid characters"
            )

        # Check for reserved names
        reserved_names = ["root", "Godot", "Editor", "MainLoop"]
        if node_name in reserved_names:
            return ValidationResult(
                allowed=False,
                reason=f"Node name '{node_name}' is reserved"
            )

        return ValidationResult(allowed=True)

    def validate_scene_name(self, scene_name: str) -> ValidationResult:
        """
        Validate a scene name for security.

        Args:
            scene_name: Scene name to validate

        Returns:
            ValidationResult with validation outcome
        """
        if not scene_name:
            return ValidationResult(allowed=False, reason="Scene name cannot be empty")

        # Check pattern
        if not self.path_patterns["scene_name"].match(scene_name):
            return ValidationResult(
                allowed=False,
                reason="Scene name contains invalid characters"
            )

        # Check extension
        if not scene_name.endswith(".tscn"):
            scene_name += ".tscn"

        return ValidationResult(allowed=True)

    def _is_risk_allowed(self, risk_level: OperationRisk) -> bool:
        """Check if a risk level is allowed by the current threshold."""
        risk_order = [
            OperationRisk.SAFE,
            OperationRisk.LOW,
            OperationRisk.MEDIUM,
            OperationRisk.HIGH,
            OperationRisk.CRITICAL
        ]

        current_index = risk_order.index(self.security_context.risk_threshold)
        operation_index = risk_order.index(risk_level)

        return operation_index <= current_index

    def _validate_operation_parameters(
        self,
        operation: str,
        parameters: Dict[str, Any],
        risk_level: OperationRisk
    ) -> ValidationResult:
        """Validate operation-specific parameters."""
        warnings = []

        # Validate node paths
        if "node_path" in parameters:
            path_result = self.validate_node_path(parameters["node_path"])
            if not path_result.allowed:
                return path_result
            warnings.extend(path_result.warnings)

        # Validate parent paths
        if "parent_path" in parameters:
            path_result = self.validate_node_path(parameters["parent_path"])
            if not path_result.allowed:
                return path_result
            warnings.extend(path_result.warnings)

        # Validate scene paths
        if "scene_path" in parameters:
            path_result = self.validate_path(parameters["scene_path"], "godot_path")
            if not path_result.allowed:
                return path_result
            warnings.extend(path_result.warnings)

        # Validate node names
        if "node_name" in parameters:
            name_result = self.validate_node_name(parameters["node_name"])
            if not name_result.allowed:
                return name_result
            warnings.extend(name_result.warnings)

        # Validate scene names
        if "scene_name" in parameters:
            name_result = self.validate_scene_name(parameters["scene_name"])
            if not name_result.allowed:
                return name_result
            warnings.extend(name_result.warnings)

        # Additional parameter validation based on operation type
        if operation == "modify_node_property":
            property_name = parameters.get("property_name", "")
            if property_name.startswith("_"):
                warnings.append(f"Modifying private property '{property_name}' may have unexpected effects")

        return ValidationResult(allowed=True, warnings=warnings)

    def validate_node_path(self, node_path: str) -> ValidationResult:
        """
        Validate a node path for safety.

        Args:
            node_path: Node path to validate

        Returns:
            ValidationResult indicating if the path is safe
        """
        return self._validate_node_path(node_path)

    def _validate_node_path(self, node_path: str) -> ValidationResult:
        """Validate a node path."""
        if not node_path:
            return ValidationResult(allowed=False, reason="Node path cannot be empty")

        # Check for path traversal
        if ".." in node_path:
            return ValidationResult(
                allowed=False,
                reason="Node path contains directory traversal characters"
            )

        # Check pattern
        if not self.path_patterns["node_path"].match(node_path):
            return ValidationResult(
                allowed=False,
                reason="Node path contains invalid characters"
            )

        return ValidationResult(allowed=True)

    def _check_operation_security(self, operation: str, parameters: Dict[str, Any]) -> List[str]:
        """Check for additional security concerns."""
        warnings = []

        # Check for potentially dangerous operations
        if operation == "delete_node":
            warnings.append("Deleting nodes cannot be undone through the interface")

        if operation == "modify_node_property":
            property_name = parameters.get("property_name", "")
            if property_name in ["script", "owner", "filename"]:
                warnings.append(f"Modifying '{property_name}' property may affect node behavior significantly")

        if operation == "create_node":
            node_type = parameters.get("node_type", "")
            if node_type in ["GDScript", "CSharpScript", "EditorScript"]:
                warnings.append("Creating script nodes requires careful implementation")

        return warnings

    def _godot_path_to_absolute(self, godot_path: str) -> str:
        """Convert a Godot path to absolute path."""
        if not godot_path.startswith("res://") or not self.security_context.project_path:
            return godot_path

        relative_path = godot_path[5:]  # Remove "res://"
        return os.path.join(self.security_context.project_path, relative_path)

    def _is_path_within_project(self, absolute_path: str) -> bool:
        """Check if an absolute path is within the project directory."""
        if not self.security_context.project_path:
            return True

        try:
            project_dir = pathlib.Path(self.security_context.project_path).resolve()
            target_path = pathlib.Path(absolute_path).resolve()
            return target_path.is_relative_to(project_dir)
        except Exception:
            return False


# Global security validator instance
_security_validator: Optional[GodotSecurityValidator] = None


def get_security_validator() -> GodotSecurityValidator:
    """Get or create global security validator instance."""
    global _security_validator
    if _security_validator is None:
        _security_validator = GodotSecurityValidator()
    return _security_validator


def set_security_context(context: SecurityContext):
    """Set the global security context."""
    validator = get_security_validator()
    validator.set_security_context(context)


def create_default_security_context(project_path: Optional[str] = None) -> SecurityContext:
    """Create a default security context with sensible settings."""
    context = SecurityContext(project_path)

    # Set medium risk threshold for general use
    context.set_risk_threshold(OperationRisk.MEDIUM)

    # Allow common safe operations
    safe_operations = [
        "get_project_info", "get_scene_tree", "get_node_info",
        "search_nodes", "get_viewport_info", "capture_screenshot"
    ]
    for op in safe_operations:
        context.add_allowed_operation(op)

    return context


# Convenience functions for common validations
@tool
def validate_operation(operation: str, parameters: Optional[Dict[str, Any]] = None) -> ValidationResult:
    """Validate an operation using the global security validator.

    Args:
        operation: Name of the operation to validate
        parameters: Optional parameters for the operation

    Returns:
        ValidationResult indicating whether the operation is safe to perform
    """
    validator = get_security_validator()
    return validator.validate_operation(operation, parameters)


@tool
def validate_path(path: str, path_type: str = "godot_path") -> ValidationResult:
    """Validate a path using the global security validator.

    Args:
        path: Path to validate
        path_type: Type of path ('godot_path', 'file_path', 'node_path')

    Returns:
        ValidationResult indicating whether the path is safe
    """
    validator = get_security_validator()
    return validator.validate_path(path, path_type)


@tool
def validate_node_name(node_name: str) -> ValidationResult:
    """Validate a node name using the global security validator.

    Args:
        node_name: Name of the node to validate

    Returns:
        ValidationResult indicating whether the node name is safe
    """
    validator = get_security_validator()
    return validator.validate_node_name(node_name)