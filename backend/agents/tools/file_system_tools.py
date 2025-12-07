"""
File READ-ONLY Tools for Godot Assistant (Planning/Learning Mode).

This module provides READ-ONLY file system tools for the planning agent.
For FILE MODIFICATION tools, see file_tools.py.

Tools in this module:
- read_file: Read file contents safely
- list_files: List directory contents with pattern filtering
- search_codebase: Search for patterns with regex support

All tools use consistent error handling and return standardized responses.
"""


import logging
import os
import re
from pathlib import Path
from typing import Optional

import aiofiles

from strands import tool
from .godot_bridge import get_godot_bridge

from ..types.tool_types import (
    ToolResponse,
    FilePath,
    DirectoryName,
    SearchPattern,
    FilePattern,
    MaxResults,
    DirectoryListing
)
from ..utils.error_handlers import (
    handle_file_errors,
    validate_path,
    create_success_response,
    create_error_response
)

# Configure module logger
logger = logging.getLogger(__name__)


def _resolve_to_project(path_str: str) -> Path:
    """Resolve a path string to an absolute path within the project."""
    # Handle Godot resource paths
    if path_str.startswith("res://"):
        path_str = path_str[6:]
        
    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()

    bridge = get_godot_bridge()
    if bridge.project_info and bridge.project_info.project_path:
        return (Path(bridge.project_info.project_path) / path).resolve()
    
    # Fallback: detect project.godot
    current = Path.cwd()
    while current != current.parent:
        if (current / "project.godot").exists():
            return (current / path).resolve()
        current = current.parent
        
    return path.resolve()


@tool
@handle_file_errors("file reading")
async def read_file(file_path: FilePath) -> ToolResponse:
    """
    Read the contents of a file with comprehensive error handling and encoding support.

    This tool safely reads file contents while handling various edge cases including:
    - File not found errors
    - Permission issues
    - Encoding problems
    - Binary files (with appropriate handling)

    Args:
        file_path: Path to the file to read (relative or absolute).
                  Supports both relative and absolute paths.

    Returns:
        ToolResponse: Standardized response containing either:
            - Success: File content formatted with path information
            - Error: Detailed error message with error categorization

    Example:
        >>> result = await read_file("src/main.py")
        >>> print(result["status"])  # "success" or "error"
        >>> print(result["content"][0]["text"])  # File content or error message

    Note:
        - Files are read with UTF-8 encoding, falling back to 'ignore' for invalid characters
        - Large files are handled efficiently with async I/O
        - Binary files are read but may contain unreadable characters
    """
    try:
        # Resolve path relative to project
        resolved_path = _resolve_to_project(file_path)

        # Validate and resolve path with security checks
        path = validate_path(
            str(resolved_path),
            operation_name="file reading",
            must_exist=True,
            must_be_file=True
        )

        # Check path safety with GodotBridge
        bridge = get_godot_bridge()
        if not bridge.is_path_safe(path):
            return create_error_response(
                f"Access denied: Path '{path}' is outside the project directory",
                "PathValidationError"
            )

        # Read file content asynchronously with proper encoding handling
        async with aiofiles.open(
            path,
            mode='r',
            encoding='utf-8',
            errors='ignore'  # Handle invalid characters gracefully
        ) as file:
            content = await file.read()

        # Format response with path information for context
        formatted_content = f"📄 File: {file_path}\n\n{content}"

        logger.info(f"Successfully read file: {file_path} ({len(content)} characters)")

        return create_success_response(
            formatted_content,
            metadata={
                "file_path": str(path),
                "file_size": len(content),
                "encoding": "utf-8"
            }
        )

    except Exception as e:
        # This should not happen due to the decorator, but added as safety net
        logger.error(f"Unexpected error reading file {file_path}: {e}")
        return create_error_response(
            f"Unexpected error reading file: {str(e)}",
            "FileReadUnexpectedError"
        )


@tool
@handle_file_errors("directory listing")
async def list_files(
    directory: DirectoryName = ".",
    pattern: str = "*"
) -> ToolResponse:
    """
    List files and directories in a specified directory with pattern filtering.

    This tool provides comprehensive directory listing capabilities including:
    - Glob pattern filtering for selective file listing
    - Organized output separating files and directories
    - Permission and access error handling
    - Relative path resolution for cleaner output

    Args:
        directory: Directory path to list (default: current directory).
                   Supports both relative and absolute paths.
        pattern: Glob pattern to filter files and directories
                (default: "*" for all files and directories).
                Common patterns:
                - "*.py" - Python files only
                - "test_*" - Files/directories starting with "test_"
                - "**/*.js" - All JavaScript files recursively

    Returns:
        ToolResponse: Standardized response containing either:
            - Success: Formatted listing with files and directories separated
            - Error: Detailed error message with error categorization

    Example:
        >>> result = await list_files("src", "*.py")
        >>> print(result["status"])  # "success" or "error"
        >>> print(result["content"][0]["text"])  # Formatted directory listing

    Note:
        - Uses glob patterns for flexible file matching
        - Results are sorted alphabetically for better readability
        - Shows directories first, then files
        - Uses emoji indicators for visual clarity
    """
    # Validate and resolve directory path
    resolved_path = _resolve_to_project(directory)
    dir_path = validate_path(
        str(resolved_path),
        operation_name="directory listing",
        must_exist=True,
        must_be_file=False
    )

    # Check path safety with GodotBridge
    bridge = get_godot_bridge()
    if not bridge.is_path_safe(dir_path):
        return create_error_response(
            f"Access denied: Path '{dir_path}' is outside the project directory",
            "PathValidationError"
        )

    # Initialize collections for organized output
    files: list[str] = []
    directories: list[str] = []

    try:
        # Use glob pattern to find matching items
        for item in dir_path.glob(pattern):
            try:
                relative_path = str(item.relative_to(dir_path))

                if item.is_file():
                    files.append(relative_path)
                elif item.is_dir():
                    directories.append(relative_path)

            except ValueError as e:
                # Handle cases where relative_to fails (e.g., different drives on Windows)
                logger.warning(f"Could not get relative path for {item}: {e}")
                continue

        # Sort results for consistent output
        files.sort()
        directories.sort()

        # Format organized output with visual indicators
        formatted_output = _format_directory_listing(directory, directories, files)

        total_items = len(directories) + len(files)
        logger.info(
            f"Listed directory '{directory}': "
            f"{len(directories)} directories, {len(files)} files "
            f"(pattern: '{pattern}')"
        )

        return create_success_response(
            formatted_output,
            metadata={
                "directory_path": str(dir_path),
                "pattern": pattern,
                "directories_count": len(directories),
                "files_count": len(files),
                "total_items": total_items,
                "directories": directories,
                "files": files
            }
        )

    except Exception as e:
        # This should not happen due to the decorator, but added as safety net
        logger.error(f"Unexpected error listing directory {directory}: {e}")
        return create_error_response(
            f"Unexpected error listing directory: {str(e)}",
            "DirectoryListUnexpectedError"
        )


def _format_directory_listing(
    directory: str,
    directories: list[str],
    files: list[str]
) -> str:
    """
    Format directory listing output with visual organization.

    Args:
        directory: The directory path that was listed
        directories: List of directory names found
        files: List of file names found

    Returns:
        Formatted string with organized directory and file listing
    """
    # Start with header
    output = f"📁 Directory: {directory}\n\n"

    # Add directories section
    if directories:
        output += "📂 Directories:\n"
        for dir_name in directories:
            output += f"   📁 {dir_name}/\n"
        output += "\n"

    # Add files section
    if files:
        output += "📄 Files:\n"
        for file_name in files:
            output += f"   📄 {file_name}\n"
        output += "\n"

    # Handle empty results
    if not directories and not files:
        output += "   No files or directories found matching the pattern.\n"

    return output


@tool
@handle_file_errors("codebase searching")
async def search_codebase(
    pattern: SearchPattern,
    directory: DirectoryName = ".",
    file_pattern: FilePattern = "*.py",
    max_results: MaxResults = 50
) -> ToolResponse:
    """
    Search for a pattern in the codebase using regular expressions with comprehensive filtering.

    This tool provides powerful codebase search capabilities including:
    - Regular expression pattern matching with case-insensitive option
    - File type filtering using glob patterns
    - Result limiting to prevent overwhelming output
    - Recursive directory search
    - Context preservation with line numbers and file paths

    Args:
        pattern: Regular expression pattern to search for.
                Supports standard regex syntax with flags applied automatically.
        directory: Directory to search in (default: current directory).
                   Supports both relative and absolute paths.
        file_pattern: Glob pattern for files to search (default: "*.py").
                      Examples: "*.js", "test_*.py", "**/*.json", "*.md"
        max_results: Maximum number of results to return (default: 50).
                    Prevents excessive output for large codebases.

    Returns:
        ToolResponse: Standardized response containing either:
            - Success: Formatted search results with file paths and line numbers
            - Error: Detailed error message with error categorization

    Example:
        >>> result = await search_codebase(
        ...     pattern="class.*Agent",
        ...     directory="src",
        ...     file_pattern="*.py",
        ...     max_results=10
        ... )
        >>> print(result["status"])  # "success" or "error"
        >>> print(result["content"][0]["text"])  # Formatted search results

    Note:
        - Search is case-insensitive by default
        - Uses multiline mode for pattern matching
        - Skips files that cannot be read (binary files, permission issues)
        - Results are numbered and sorted by discovery order
        - Shows search statistics (files searched, matches found)

    Raises:
        ValueError: If the regex pattern is invalid
    """
    # Validate and resolve search directory
    resolved_path = _resolve_to_project(directory)
    dir_path = validate_path(
        str(resolved_path),
        operation_name="codebase searching",
        must_exist=True,
        must_be_file=False
    )

    # Check path safety with GodotBridge
    bridge = get_godot_bridge()
    if not bridge.is_path_safe(dir_path):
        return create_error_response(
            f"Access denied: Path '{dir_path}' is outside the project directory",
            "PathValidationError"
        )

    # Compile and validate regex pattern
    try:
        regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        logger.debug(f"Compiled regex pattern: {pattern}")
    except re.error as e:
        error_msg = f"Invalid regular expression pattern: {pattern}"
        logger.warning(f"Regex compilation failed: {error_msg} - {str(e)}")
        return create_error_response(
            f"{error_msg}. Details: {str(e)}",
            "InvalidRegexPattern",
            f"Pattern: {pattern}, Error: {str(e)}"
        )

    # Initialize search state
    results: list[dict] = []
    files_searched = 0
    files_skipped = 0

    try:
        # Search through files matching the file pattern
        for file_path in dir_path.rglob(file_pattern):
            # Skip directories and non-files
            if not file_path.is_file():
                continue

            files_searched += 1

            try:
                # Read file content asynchronously with encoding fallback
                async with aiofiles.open(
                    file_path,
                    mode='r',
                    encoding='utf-8',
                    errors='ignore'
                ) as file:
                    content = await file.read()

                # Search for pattern matches in the file
                file_matches = _search_file_content(
                    content, regex, file_path, dir_path, max_results - len(results)
                )

                # Add matches to results (if any)
                if file_matches:
                    results.extend(file_matches)

                # Stop if we've reached the maximum number of results
                if len(results) >= max_results:
                    logger.info(
                        f"Search stopped: reached max_results={max_results} "
                        f"after searching {files_searched} files"
                    )
                    break

            except PermissionError:
                files_skipped += 1
                logger.debug(f"Skipped file due to permissions: {file_path}")
                continue
            except Exception as e:
                files_skipped += 1
                logger.debug(f"Skipped file due to read error: {file_path} - {e}")
                continue

        # Format and return search results
        formatted_output = _format_search_results(
            pattern, directory, file_pattern, results, files_searched, files_skipped, max_results
        )

        logger.info(
            f"Codebase search completed: pattern='{pattern}', "
            f"directory='{directory}', file_pattern='{file_pattern}', "
            f"matches={len(results)}, files_searched={files_searched}"
        )

        return create_success_response(
            formatted_output,
            metadata={
                "search_pattern": pattern,
                "search_directory": str(dir_path),
                "file_pattern": file_pattern,
                "matches_found": len(results),
                "files_searched": files_searched,
                "files_skipped": files_skipped,
                "max_results_reached": len(results) >= max_results,
                "results": results
            }
        )

    except Exception as e:
        # This should not happen due to the decorator, but added as safety net
        logger.error(f"Unexpected error during codebase search: {e}")
        return create_error_response(
            f"Unexpected error during codebase search: {str(e)}",
            "CodebaseSearchUnexpectedError"
        )


def _search_file_content(
    content: str,
    regex: re.Pattern,
    file_path: Path,
    base_dir: Path,
    remaining_results: int
) -> list[dict]:
    """
    Search for pattern matches in file content.

    Args:
        content: File content to search through
        regex: Compiled regex pattern
        file_path: Path to the file being searched
        base_dir: Base directory for relative path calculation
        remaining_results: Maximum additional results to collect

    Returns:
        List of search result dictionaries
    """
    matches = []

    try:
        relative_path = str(file_path.relative_to(base_dir))
    except ValueError:
        # Fallback to absolute path if relative calculation fails
        relative_path = str(file_path)

    # Search line by line to preserve line numbers
    for line_num, line in enumerate(content.split('\n'), 1):
        if regex.search(line):
            match_info = {
                "file": relative_path,
                "line": line_num,
                "content": line.strip(),
                "match_length": len(line.strip())
            }
            matches.append(match_info)

            # Stop if we've collected enough results
            if len(matches) >= remaining_results:
                break

    return matches


def _format_search_results(
    pattern: str,
    directory: str,
    file_pattern: str,
    results: list[dict],
    files_searched: int,
    files_skipped: int,
    max_results: int
) -> str:
    """
    Format search results into a readable output.

    Args:
        pattern: Search pattern used
        directory: Directory searched
        file_pattern: File pattern used
        results: List of search results
        files_searched: Number of files successfully searched
        files_skipped: Number of files skipped due to errors
        max_results: Maximum results limit

    Returns:
        Formatted search results string
    """
    if not results:
        return (
            f"🔍 Search Results\n\n"
            f"❌ No matches found for pattern: '{pattern}'\n"
            f"📁 Directory: {directory}\n"
            f"📄 File pattern: {file_pattern}\n"
            f"📊 Files searched: {files_searched}\n"
        )

    output = (
        f"🔍 Search Results\n\n"
        f"✅ Found {len(results)} matches for pattern: '{pattern}'\n"
        f"📁 Directory: {directory}\n"
        f"📄 File pattern: {file_pattern}\n"
        f"📊 Files searched: {files_searched}"
    )

    if files_skipped > 0:
        output += f" (skipped {files_skipped} files)"

    output += "\n\n"

    # Format individual results
    for i, result in enumerate(results, 1):
        output += f"{i}. 📄 {result['file']}:{result['line']}\n"
        output += f"   💡 {result['content']}\n\n"

    # Add note if results were limited
    if len(results) >= max_results:
        output += f"⚠️  Note: Results limited to {max_results} matches.\n"

    return output
