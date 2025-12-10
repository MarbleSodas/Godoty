"""
Error handling utilities for agent tools.

This module provides reusable error handling decorators and utilities to ensure
consistent error handling patterns across all tools while avoiding code duplication.
"""

import logging
from functools import wraps
from pathlib import Path
from typing import Callable, TypeVar, Union, Any, Optional, Dict, List

from ..types.tool_types import (
    ToolResponse,
    ToolStatus,
    ContentBlock,
    ErrorResponse,
    SuccessResponse
)

# Type variables for better type inference
F = TypeVar('F', bound=Callable[..., Any])
T = TypeVar('T')

# Configure logger for error handling
logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Base exception for tool-related errors."""

    def __init__(self, message: str, error_type: str = "ToolError", details: Optional[str] = None):
        self.message = message
        self.error_type = error_type
        self.details = details
        super().__init__(message)


class FileOperationError(ToolError):
    """Exception raised for file operation errors."""

    def __init__(self, message: str, operation: str = "file operation", details: Optional[str] = None):
        super().__init__(message, f"{operation.title()}Error", details)


class PathValidationError(ToolError):
    """Exception raised for path validation errors."""

    def __init__(self, path: str, reason: str = "invalid path"):
        message = f"Path validation failed: {path} ({reason})"
        super().__init__(message, "PathValidationError", reason)


def create_error_response(
    message: str,
    error_type: str = "ToolError",
    details: Optional[str] = None
) -> ErrorResponse:
    """
    Create a standardized error response.

    Args:
        message: Human-readable error message
        error_type: Machine-readable error type for categorization
        details: Additional error details for debugging

    Returns:
        Formatted error response dictionary
    """
    error_response: ErrorResponse = {
        "status": ToolStatus.ERROR,
        "content": [{"text": message}],
        "error_type": error_type,
        "error_details": details
    }

    # Log the error for debugging
    logger.error(f"Tool error [{error_type}]: {message}")
    if details:
        logger.debug(f"Error details: {details}")

    return error_response


def create_success_response(
    content: Union[str, list],
    metadata: Optional[Dict[str, Any]] = None
) -> SuccessResponse:
    """
    Create a standardized success response.

    Args:
        content: Response content (string or list of content blocks)
        metadata: Optional metadata for the response

    Returns:
        Formatted success response dictionary
    """
    # Convert string content to proper content block format
    if isinstance(content, str):
        content_blocks = [{"text": content}]
    else:
        content_blocks = content

    success_response: SuccessResponse = {
        "status": ToolStatus.SUCCESS,
        "content": content_blocks,
        "metadata": metadata
    }

    return success_response


def handle_file_errors(operation_name: str):
    """
    Decorator for consistent file operation error handling.

    This decorator handles common file system errors and converts them
    to standardized error responses, reducing code duplication.

    Args:
        operation_name: Human-readable name of the operation for error messages

    Returns:
        Decorated function that handles file operation errors
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> ToolResponse:
            try:
                result = await func(*args, **kwargs)
                return result
            except FileNotFoundError as e:
                return create_error_response(
                    f"File not found during {operation_name}: {e}",
                    f"{operation_name.title()}FileNotFoundError",
                    str(e)
                )
            except PermissionError as e:
                return create_error_response(
                    f"Permission denied during {operation_name}: {e}",
                    f"{operation_name.title()}PermissionError",
                    str(e)
                )
            except IsADirectoryError as e:
                return create_error_response(
                    f"Expected file but got directory during {operation_name}: {e}",
                    f"{operation_name.title()}DirectoryError",
                    str(e)
                )
            except NotADirectoryError as e:
                return create_error_response(
                    f"Expected directory but got file during {operation_name}: {e}",
                    f"{operation_name.title()}NotDirectoryError",
                    str(e)
                )
            except OSError as e:
                return create_error_response(
                    f"System error during {operation_name}: {e}",
                    f"{operation_name.title()}SystemError",
                    str(e)
                )
            except UnicodeDecodeError as e:
                return create_error_response(
                    f"Text encoding error during {operation_name}: {e}",
                    f"{operation_name.title()}EncodingError",
                    f"File encoding issue: {str(e)}"
                )
            except ToolError as e:
                # Handle custom tool errors
                return create_error_response(e.message, e.error_type, e.details)
            except Exception as e:
                logger.exception(f"Unexpected error in {operation_name}")
                return create_error_response(
                    f"Unexpected error during {operation_name}: {str(e)}",
                    f"{operation_name.title()}UnexpectedError",
                    str(e)
                )

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> ToolResponse:
            try:
                result = func(*args, **kwargs)
                return result
            except FileNotFoundError as e:
                return create_error_response(
                    f"File not found during {operation_name}: {e}",
                    f"{operation_name.title()}FileNotFoundError",
                    str(e)
                )
            except PermissionError as e:
                return create_error_response(
                    f"Permission denied during {operation_name}: {e}",
                    f"{operation_name.title()}PermissionError",
                    str(e)
                )
            except IsADirectoryError as e:
                return create_error_response(
                    f"Expected file but got directory during {operation_name}: {e}",
                    f"{operation_name.title()}DirectoryError",
                    str(e)
                )
            except NotADirectoryError as e:
                return create_error_response(
                    f"Expected directory but got file during {operation_name}: {e}",
                    f"{operation_name.title()}NotDirectoryError",
                    str(e)
                )
            except OSError as e:
                return create_error_response(
                    f"System error during {operation_name}: {e}",
                    f"{operation_name.title()}SystemError",
                    str(e)
                )
            except UnicodeDecodeError as e:
                return create_error_response(
                    f"Text encoding error during {operation_name}: {e}",
                    f"{operation_name.title()}EncodingError",
                    f"File encoding issue: {str(e)}"
                )
            except ToolError as e:
                return create_error_response(e.message, e.error_type, e.details)
            except Exception as e:
                logger.exception(f"Unexpected error in {operation_name}")
                return create_error_response(
                    f"Unexpected error during {operation_name}: {str(e)}",
                    f"{operation_name.title()}UnexpectedError",
                    str(e)
                )

        # Return the appropriate wrapper based on whether the function is async
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

    return decorator


def validate_path(
    path_str: str,
    operation_name: str = "file operation",
    must_exist: bool = True,
    must_be_file: Optional[bool] = None,
    allowed_extensions: Optional[list[str]] = None
) -> Path:
    """
    Validate and normalize a file path with comprehensive checks.

    Args:
        path_str: The path string to validate
        operation_name: Name of the operation for error messages
        must_exist: Whether the path must exist
        must_be_file: If True, path must be a file; if False, must be directory; if None, no check
        allowed_extensions: List of allowed file extensions (e.g., ['.py', '.txt'])

    Returns:
        Resolved Path object

    Raises:
        PathValidationError: If path validation fails
    """
    try:
        path = Path(path_str).resolve()

        # Check if path exists
        if must_exist and not path.exists():
            raise PathValidationError(str(path_str), "path does not exist")

        # Check file/directory constraints
        if path.exists():
            if must_be_file is True and not path.is_file():
                raise PathValidationError(str(path_str), "path is not a file")
            if must_be_file is False and not path.is_dir():
                raise PathValidationError(str(path_str), "path is not a directory")

        # Check file extensions
        if allowed_extensions and path.suffix not in allowed_extensions:
            allowed_str = ", ".join(allowed_extensions)
            raise PathValidationError(
                str(path_str),
                f"file extension '{path.suffix}' not allowed (allowed: {allowed_str})"
            )

        return path

    except Exception as e:
        if isinstance(e, PathValidationError):
            raise
        raise PathValidationError(str(path_str), f"validation failed: {str(e)}")


def safe_path_join(base_path: Union[str, Path], *paths: Union[str, Path]) -> Path:
    """
    Safely join paths with security validation.

    This function prevents path traversal attacks by ensuring the joined path
    stays within the base path.

    Args:
        base_path: Base directory path
        *paths: Additional path components to join

    Returns:
        Safely joined Path object

    Raises:
        PathValidationError: If path traversal is detected
    """
    try:
        base = Path(base_path).resolve()
        result = base

        for path_part in paths:
            result = result / path_part

        # Resolve and ensure we're still within base path
        result = result.resolve()

        # Check for path traversal
        try:
            result.relative_to(base)
        except ValueError as e:
            raise PathValidationError(str(result), "path traversal detected")

        return result

    except Exception as e:
        if isinstance(e, PathValidationError):
            raise
        raise PathValidationError(str(paths), f"safe path join failed: {str(e)}")


def handle_tool_errors(operation_name: str):
    """
    Decorator for consistent tool operation error handling.

    This decorator handles common tool errors and converts them
    to standardized error responses, reducing code duplication.

    Args:
        operation_name: Human-readable name of the operation for error messages

    Returns:
        Decorated function that handles tool operation errors
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                logger.exception(f"Unexpected error in {operation_name}")
                return create_error_response(
                    f"Error during {operation_name}: {str(e)}",
                    f"{operation_name.title()}Error",
                    str(e)
                )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                logger.exception(f"Unexpected error in {operation_name}")
                return create_error_response(
                    f"Error during {operation_name}: {str(e)}",
                    f"{operation_name.title()}Error",
                    str(e)
                )

        # Return the appropriate wrapper based on whether the function is async
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator