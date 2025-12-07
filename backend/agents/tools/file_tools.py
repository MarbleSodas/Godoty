"""
File WRITE/MODIFY Tools for Godot Assistant (Execution Mode).

This module provides FILE MODIFICATION tools used by the executor agent.
For READ-ONLY file operations, see file_system_tools.py.

Tools in this module:
- write_file: Write content to files with backup
- delete_file: Delete files with backup
- modify_gdscript_method: Edit existing GDScript methods
- add_gdscript_method: Add new methods to GDScript files
- remove_gdscript_method: Remove methods from GDScript files
- modify_project_setting: Edit project.godot settings

Note: There is a read_file_safe() helper method in FileTools class for
internal use, but the primary read_file TOOL is in file_system_tools.py.
"""

import asyncio
import aiofiles
import json
import os
import shutil
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass
from datetime import datetime

from strands import tool
from .godot_bridge import get_godot_bridge

logger = logging.getLogger(__name__)


@dataclass
class FileOperationResult:
    """Result of a file operation."""
    success: bool
    file_path: Optional[str] = None
    backup_path: Optional[str] = None
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    error: Optional[str] = None
    operation_type: str = ""


@dataclass
class GDScriptEditResult:
    """Result of a GDScript editing operation."""
    success: bool
    file_path: Optional[str] = None
    modified_methods: List[str] = None
    added_methods: List[str] = None
    removed_methods: List[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.modified_methods is None:
            self.modified_methods = []
        if self.added_methods is None:
            self.added_methods = []
        if self.removed_methods is None:
            self.removed_methods = []


class FileTools:
    """
    Comprehensive file management tools for the executor agent.

    These tools handle direct file operations that complement Godot's API,
    including GDScript editing, project file modification, and backup/restore.
    """

    def __init__(self):
        """Initialize file tools with operation history."""
        self._operation_history: List[Dict[str, Any]] = []
        self._backup_dir = Path(".godoty_backups")
        self._backup_dir.mkdir(exist_ok=True)

    def _record_operation(self, operation_type: str, file_path: str, result: bool, details: Dict[str, Any] = None):
        """Record a file operation in the history."""
        operation = {
            "type": operation_type,
            "file_path": file_path,
            "result": result,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self._operation_history.append(operation)

        # Keep history manageable
        if len(self._operation_history) > 100:
            self._operation_history = self._operation_history[-50:]

    async def _create_backup(self, file_path: Path) -> Optional[Path]:
        """Create a backup of the specified file."""
        try:
            if not file_path.exists():
                return None

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            backup_path = self._backup_dir / backup_name

            # Copy file to backup directory
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return backup_path

        except Exception as e:
            logger.error(f"Failed to create backup for {file_path}: {e}")
            return None

    async def _is_safe_path(self, file_path: Path, project_root: Optional[Path] = None) -> bool:
        """Check if a file path is safe for modification."""
        # First check with bridge if available
        bridge = get_godot_bridge()
        if bridge.is_path_safe(file_path):
            return True

        if project_root is None:
            # Try to detect project root
            current = Path.cwd()
            while current != current.parent:
                if (current / "project.godot").exists():
                    project_root = current
                    break
                current = current.parent

        if project_root is None:
            # If no project root found, only allow current directory
            project_root = Path.cwd()

        try:
            file_path.resolve().relative_to(project_root.resolve())
            return True
        except ValueError:
            logger.warning(f"Path {file_path} is outside project root {project_root}")
            return False

    async def _get_project_root(self) -> Path:
        """Get the project root path."""
        # Check with bridge first
        bridge = get_godot_bridge()
        if bridge.project_info and bridge.project_info.project_path:
             return Path(bridge.project_info.project_path)
        
        # Fallback to detecting project.godot
        current = Path.cwd()
        while current != current.parent:
            if (current / "project.godot").exists():
                return current
            current = current.parent
            
        # If no project root found, default to CWD
        return Path.cwd()

    async def _resolve_path(self, file_path: str) -> Path:
        """
        Resolve file path relative to project root if not absolute.
        Handles res:// format by stripping the prefix.
        
        Args:
            file_path: The file path to resolve
            
        Returns:
            Resolved Path object (absolute)
        """
        # Handle Godot resource paths
        if file_path.startswith("res://"):
            project_root = await self._get_project_root()
            relative_path = file_path[6:] # Strip res://
            return project_root / relative_path

        path = Path(file_path)
        if path.is_absolute():
            return path
            
        project_root = await self._get_project_root()
        return project_root / path

    # Basic File Operations
    async def read_file_safe(self, file_path: str, encoding: str = "utf-8") -> FileOperationResult:
        """
        Safely read a file with error handling.

        Args:
            file_path: Path to the file to read
            encoding: File encoding (default: utf-8)

        Returns:
            FileOperationResult with file content
        """
        try:
            path = await self._resolve_path(file_path)

            if not path.exists():
                return FileOperationResult(
                    success=False,
                    file_path=file_path,
                    error=f"File not found: {file_path}"
                )

            async with aiofiles.open(path, 'r', encoding=encoding) as f:
                content = await f.read()

            self._record_operation("read_file", file_path, True, {"encoding": encoding})
            logger.info(f"Successfully read file: {file_path} (resolved: {path})")

            return FileOperationResult(
                success=True,
                file_path=file_path,
                new_content=content,
                operation_type="read"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error reading file {file_path}: {error_msg}")
            self._record_operation("read_file", file_path, False, {"error": error_msg})
            return FileOperationResult(
                success=False,
                file_path=file_path,
                error=error_msg,
                operation_type="read"
            )

    async def write_file_safe(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_backup: bool = True,
        project_root: Optional[str] = None
    ) -> FileOperationResult:
        """
        Safely write a file with backup and validation.

        Args:
            file_path: Path to the file to write
            content: Content to write to the file
            encoding: File encoding (default: utf-8)
            create_backup: Whether to create a backup before writing (default: True)
            project_root: Project root for path validation (optional)

        Returns:
            FileOperationResult with operation details
        """
        root = Path(project_root) if project_root else None

        try:
            # Resolve path
            path = await self._resolve_path(file_path)

            # Safety check
            if not await self._is_safe_path(path, root):
                return FileOperationResult(
                    success=False,
                    file_path=file_path,
                    error="File path is outside project root"
                )

            # Read old content if file exists
            old_content = None
            if path.exists():
                # Direct read since we already resolved the path
                try:
                    async with aiofiles.open(path, 'r', encoding=encoding) as f:
                        old_content = await f.read()
                except Exception:
                    pass # Ignore read errors for backup/old_content purposes

            # Create backup if requested and file exists
            backup_path = None
            if create_backup and path.exists():
                backup_path = await self._create_backup(path)

            # Create directory if it doesn't exist
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            async with aiofiles.open(path, 'w', encoding=encoding) as f:
                await f.write(content)

            details = {
                "encoding": encoding,
                "backup_created": backup_path is not None,
                "backup_path": str(backup_path) if backup_path else None,
                "resolved_path": str(path)
            }

            self._record_operation("write_file", file_path, True, details)
            logger.info(f"Successfully wrote file: {file_path} (resolved: {path})")

            return FileOperationResult(
                success=True,
                file_path=file_path,
                backup_path=str(backup_path) if backup_path else None,
                old_content=old_content,
                new_content=content,
                operation_type="write"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error writing file {file_path}: {error_msg}")
            self._record_operation("write_file", file_path, False, {"error": error_msg})
            return FileOperationResult(
                success=False,
                file_path=file_path,
                error=error_msg,
                operation_type="write"
            )

    async def delete_file_safe(
        self,
        file_path: str,
        create_backup: bool = True,
        project_root: Optional[str] = None
    ) -> FileOperationResult:
        """
        Safely delete a file with backup.

        Args:
            file_path: Path to the file to delete
            create_backup: Whether to create a backup before deletion (default: True)
            project_root: Project root for path validation (optional)

        Returns:
            FileOperationResult with operation details
        """
        root = Path(project_root) if project_root else None

        try:
            # Resolve path
            path = await self._resolve_path(file_path)

            # Safety check
            if not await self._is_safe_path(path, root):
                return FileOperationResult(
                    success=False,
                    file_path=file_path,
                    error="File path is outside project root"
                )

            if not path.exists():
                return FileOperationResult(
                    success=False,
                    file_path=file_path,
                    error=f"File not found: {file_path}"
                )

            # Read content before deletion for backup
            old_content = None
            if create_backup:
                # read_file_safe handles resolution internally, so we can pass file_path
                # OR we can just read 'path' directly since we have it.
                # Let's use direct read to be safe and efficient
                try:
                    async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                        old_content = await f.read()
                except Exception:
                    pass

            # Create backup if requested
            backup_path = None
            if create_backup:
                backup_path = await self._create_backup(path)

            # Delete file
            path.unlink()

            details = {
                "backup_created": backup_path is not None,
                "backup_path": str(backup_path) if backup_path else None,
                "resolved_path": str(path)
            }

            self._record_operation("delete_file", file_path, True, details)
            logger.info(f"Successfully deleted file: {file_path} (resolved: {path})")

            return FileOperationResult(
                success=True,
                file_path=file_path,
                backup_path=str(backup_path) if backup_path else None,
                old_content=old_content,
                operation_type="delete"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error deleting file {file_path}: {error_msg}")
            self._record_operation("delete_file", file_path, False, {"error": error_msg})
            return FileOperationResult(
                success=False,
                file_path=file_path,
                error=error_msg,
                operation_type="delete"
            )

    # GDScript Specific Operations
    async def modify_gdscript_method(
        self,
        file_path: str,
        method_name: str,
        new_method_code: str,
        create_backup: bool = True
    ) -> GDScriptEditResult:
        """
        Safely modify a specific method in a GDScript file.

        Args:
            file_path: Path to the GDScript file
            method_name: Name of the method to modify
            new_method_code: New code for the method
            create_backup: Whether to create a backup (default: True)

        Returns:
            GDScriptEditResult with operation details
        """
        try:
            # Read the file
            file_result = await self.read_file_safe(file_path)
            if not file_result.success:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=file_result.error
                )

            content = file_result.new_content
            old_method = None

            # Find the method to replace
            method_pattern = rf'(func\s+{method_name}\s*\([^)]*\)\s*(?:->\s*\w+\s*)?)'
            method_match = re.search(method_pattern, content)

            if not method_match:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=f"Method '{method_name}' not found in file"
                )

            # Find the full method (including body)
            start_pos = method_match.start()
            method_indent = len(re.match(r'^\s*', content[start_pos:]).group())

            # Find the end of the method by counting indentation
            lines = content[start_pos:].split('\n')
            method_lines = [lines[0]]  # Start with method signature
            brace_count = 0
            in_method = False

            for i, line in enumerate(lines[1:], 1):
                line_stripped = line.strip()
                if not line_stripped:
                    method_lines.append(line)
                    continue

                current_indent = len(re.match(r'^\s*', line).group())

                if not in_method:
                    in_method = True
                    method_lines.append(line)
                elif current_indent <= method_indent and line_stripped:
                    # End of method
                    break
                else:
                    method_lines.append(line)

            old_method = '\n'.join(method_lines)

            # Replace the method
            new_content = content[:start_pos] + new_method_code + content[start_pos + len(old_method):]

            # Write the modified file
            write_result = await self.write_file_safe(
                file_path,
                new_content,
                create_backup=create_backup
            )

            if not write_result.success:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=write_result.error
                )

            logger.info(f"Successfully modified method '{method_name}' in {file_path}")
            return GDScriptEditResult(
                success=True,
                file_path=file_path,
                modified_methods=[method_name]
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error modifying GDScript method: {error_msg}")
            return GDScriptEditResult(
                success=False,
                file_path=file_path,
                error=error_msg
            )

    async def add_gdscript_method(
        self,
        file_path: str,
        method_code: str,
        insert_position: str = "end",  # "end", "start", or after a specific method
        after_method: Optional[str] = None,
        create_backup: bool = True
    ) -> GDScriptEditResult:
        """
        Add a new method to a GDScript file.

        Args:
            file_path: Path to the GDScript file
            method_code: Code for the new method
            insert_position: Where to insert the method ("end", "start", "after")
            after_method: Method name to insert after (if insert_position="after")
            create_backup: Whether to create a backup (default: True)

        Returns:
            GDScriptEditResult with operation details
        """
        try:
            # Read the file
            file_result = await self.read_file_safe(file_path)
            if not file_result.success:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=file_result.error
                )

            content = file_result.new_content

            # Extract method name from the code
            method_match = re.search(r'func\s+(\w+)', method_code)
            if not method_match:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error="Could not extract method name from provided code"
                )

            method_name = method_match.group(1)

            # Check if method already exists
            if re.search(rf'func\s+{method_name}\s*\(', content):
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=f"Method '{method_name}' already exists in file"
                )

            # Determine insertion position
            if insert_position == "end":
                new_content = content.rstrip() + "\n\n" + method_code + "\n"
            elif insert_position == "start":
                # Find the end of class/extends declarations
                lines = content.split('\n')
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith(('extends ', 'class_name ')):
                        insert_idx = i + 1
                    elif insert_idx > 0 and line.strip() and not line.strip().startswith('#'):
                        break
                new_content = '\n'.join(lines[:insert_idx]) + "\n\n" + method_code + "\n" + '\n'.join(lines[insert_idx:])
            elif insert_position == "after" and after_method:
                # Find the specified method
                method_pattern = r'(func\s+' + after_method + r'\s*\([^)]*\)[^}]*)'
                method_match = re.search(method_pattern, content, re.DOTALL)
                if not method_match:
                    return GDScriptEditResult(
                        success=False,
                        file_path=file_path,
                        error=f"Method '{after_method}' not found for insertion point"
                    )
                # Insert after the method (find the end of the method)
                end_pos = method_match.end()
                new_content = content[:end_pos] + "\n\n" + method_code + content[end_pos:]
            else:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error="Invalid insert_position or missing after_method"
                )

            # Write the modified file
            write_result = await self.write_file_safe(
                file_path,
                new_content,
                create_backup=create_backup
            )

            if not write_result.success:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=write_result.error
                )

            logger.info(f"Successfully added method '{method_name}' to {file_path}")
            return GDScriptEditResult(
                success=True,
                file_path=file_path,
                added_methods=[method_name]
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error adding GDScript method: {error_msg}")
            return GDScriptEditResult(
                success=False,
                file_path=file_path,
                error=error_msg
            )

    async def remove_gdscript_method(
        self,
        file_path: str,
        method_name: str,
        create_backup: bool = True
    ) -> GDScriptEditResult:
        """
        Remove a method from a GDScript file.

        Args:
            file_path: Path to the GDScript file
            method_name: Name of the method to remove
            create_backup: Whether to create a backup (default: True)

        Returns:
            GDScriptEditResult with operation details
        """
        try:
            # Read the file
            file_result = await self.read_file_safe(file_path)
            if not file_result.success:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=file_result.error
                )

            content = file_result.new_content

            # Find the method to remove
            method_pattern = rf'(\n?func\s+{method_name}\s*\([^)]*\)(?:\s*->\s*\w+)?\s*.*?)(?=\n\s*(func|class)|\Z)'
            method_match = re.search(method_pattern, content, re.DOTALL)

            if not method_match:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=f"Method '{method_name}' not found in file"
                )

            # Remove the method
            method_text = method_match.group(1)
            new_content = content.replace(method_text, "")

            # Clean up extra whitespace
            new_content = re.sub(r'\n\s*\n\s*\n', '\n\n', new_content)

            # Write the modified file
            write_result = await self.write_file_safe(
                file_path,
                new_content,
                create_backup=create_backup
            )

            if not write_result.success:
                return GDScriptEditResult(
                    success=False,
                    file_path=file_path,
                    error=write_result.error
                )

            logger.info(f"Successfully removed method '{method_name}' from {file_path}")
            return GDScriptEditResult(
                success=True,
                file_path=file_path,
                removed_methods=[method_name]
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error removing GDScript method: {error_msg}")
            return GDScriptEditResult(
                success=False,
                file_path=file_path,
                error=error_msg
            )

    # Project File Operations
    async def modify_project_setting(
        self,
        project_path: str,
        section: str,
        key: str,
        value: Any,
        create_backup: bool = True
    ) -> FileOperationResult:
        """
        Modify a setting in the Godot project file.

        Args:
            project_path: Path to project.godot file
            section: Configuration section (e.g., "application", "rendering")
            key: Setting key
            value: New value for the setting
            create_backup: Whether to create a backup (default: True)

        Returns:
            FileOperationResult with operation details
        """
        try:
            # Read project file
            file_result = await self.read_file_safe(project_path)
            if not file_result.success:
                return FileOperationResult(
                    success=False,
                    file_path=project_path,
                    error=file_result.error
                )

            content = file_result.new_content

            # Parse and modify the configuration
            lines = content.split('\n')
            in_section = False
            section_indent = 0
            key_found = False
            modified_lines = []

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Check for section header
                if stripped.startswith('[') and stripped.endswith(']'):
                    current_section = stripped[1:-1]
                    in_section = (current_section == section)
                    if in_section:
                        section_indent = len(line) - len(line.lstrip())
                    modified_lines.append(line)
                    continue

                # If we're in the target section
                if in_section and stripped.startswith(f'{key} ='):
                    # Replace the key value
                    indent = len(line) - len(line.lstrip())
                    new_line = ' ' * indent + f'{key} = {self._format_config_value(value)}'
                    modified_lines.append(new_line)
                    key_found = True
                else:
                    modified_lines.append(line)

            # If key wasn't found, add it to the section
            if not key_found:
                # Find the end of the section
                section_end = len(modified_lines)
                for i in range(len(modified_lines)):
                    if modified_lines[i].strip().startswith('[') and i > 0:
                        section_end = i
                        break

                # Insert the key at the end of the section
                insert_line = ' ' * (section_indent + 4) + f'{key} = {self._format_config_value(value)}'
                modified_lines.insert(section_end, insert_line)

            # Write the modified file
            new_content = '\n'.join(modified_lines)
            write_result = await self.write_file_safe(
                project_path,
                new_content,
                create_backup=create_backup
            )

            if not write_result.success:
                return FileOperationResult(
                    success=False,
                    file_path=project_path,
                    error=write_result.error
                )

            logger.info(f"Successfully modified project setting {section}.{key}")
            return FileOperationResult(
                success=True,
                file_path=project_path,
                old_content=content,
                new_content=new_content,
                operation_type="project_setting"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error modifying project setting: {error_msg}")
            return FileOperationResult(
                success=False,
                file_path=project_path,
                error=error_msg,
                operation_type="project_setting"
            )

    def _format_config_value(self, value: Any) -> str:
        """Format a value for Godot configuration file."""
        if isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, bool):
            return str(value).lower()
        elif isinstance(value, (list, tuple)):
            return '[' + ', '.join(self._format_config_item(item) for item in value) + ']'
        elif isinstance(value, dict):
            items = [f'{k}: {self._format_config_item(v)}' for k, v in value.items()]
            return '{' + ', '.join(items) + '}'
        else:
            return str(value)

    def _format_config_item(self, item: Any) -> str:
        """Format a single item for configuration."""
        if isinstance(item, str):
            return f'"{item}"'
        return str(item)

    # Utility Methods
    async def get_operation_history(self) -> List[Dict[str, Any]]:
        """Get the history of file operations."""
        return self._operation_history.copy()

    async def clear_operation_history(self):
        """Clear the operation history."""
        self._operation_history.clear()

    async def restore_from_backup(self, file_path: str, backup_timestamp: Optional[str] = None) -> FileOperationResult:
        """
        Restore a file from backup.

        Args:
            file_path: Original file path to restore
            backup_timestamp: Specific backup timestamp (optional, uses latest if not provided)

        Returns:
            FileOperationResult with operation details
        """
        try:
            path = Path(file_path)
            backup_name = path.stem

            if backup_timestamp:
                backup_file = self._backup_dir / f"{backup_name}_{backup_timestamp}{path.suffix}"
            else:
                # Find the latest backup
                backup_pattern = f"{backup_name}_*{path.suffix}"
                backup_files = list(self._backup_dir.glob(backup_pattern))
                if not backup_files:
                    return FileOperationResult(
                        success=False,
                        file_path=file_path,
                        error="No backup found for file"
                    )
                backup_file = max(backup_files, key=lambda f: f.stat().st_mtime)

            if not backup_file.exists():
                return FileOperationResult(
                    success=False,
                    file_path=file_path,
                    error=f"Backup file not found: {backup_file}"
                )

            # Read backup content
            async with aiofiles.open(backup_file, 'r', encoding="utf-8") as f:
                content = await f.read()

            # Write to original location
            write_result = await self.write_file_safe(
                file_path,
                content,
                create_backup=True  # Backup current state before restore
            )

            if not write_result.success:
                return FileOperationResult(
                    success=False,
                    file_path=file_path,
                    error=write_result.error
                )

            logger.info(f"Successfully restored {file_path} from backup {backup_file}")
            return FileOperationResult(
                success=True,
                file_path=file_path,
                backup_path=str(backup_file),
                new_content=content,
                operation_type="restore"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error restoring from backup: {error_msg}")
            return FileOperationResult(
                success=False,
                file_path=file_path,
                error=error_msg,
                operation_type="restore"
            )


@tool
async def write_file(file_path: str, content: str, **kwargs) -> FileOperationResult:
    """Write content to a file safely with backup.

    Args:
        file_path: Path to the file to write
        content: Content to write to the file
        **kwargs: Additional options (encoding, backup, etc.)

    Returns:
        FileOperationResult containing success status and operation details
    """
    # Handle case where LLM passes 'kwargs' as a string parameter
    if 'kwargs' in kwargs:
        extra_args = kwargs.pop('kwargs')
        if isinstance(extra_args, str):
            try:
                extra_args = json.loads(extra_args)
                if isinstance(extra_args, dict):
                    kwargs.update(extra_args)
            except json.JSONDecodeError:
                pass
        elif isinstance(extra_args, dict):
            kwargs.update(extra_args)

    tools = FileTools()
    # Filter kwargs to only allow valid arguments for write_file_safe
    valid_args = ['encoding', 'create_backup', 'project_root']
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_args}
    
    return await tools.write_file_safe(file_path, content, **filtered_kwargs)


# NOTE: read_file tool is defined in file_system_tools.py, not here.
# FileTools.read_file_safe() exists as an INTERNAL helper method only.


@tool
async def delete_file(file_path: str, **kwargs) -> FileOperationResult:
    """Delete a file safely with backup.

    Args:
        file_path: Path to the file to delete
        **kwargs: Additional options (backup, etc.)

    Returns:
        FileOperationResult containing success status
    """
    tools = FileTools()
    return await tools.delete_file_safe(file_path, **kwargs)


@tool
async def modify_gdscript_method(
    file_path: str,
    method_name: str,
    new_method_code: str,
    **kwargs
) -> GDScriptEditResult:
    """Modify a specific method in a GDScript file.

    Args:
        file_path: Path to the GDScript file
        method_name: Name of the method to modify
        new_method_code: New code for the method
        **kwargs: Additional options (backup, etc.)

    Returns:
        GDScriptEditResult containing operation details
    """
    tools = FileTools()
    return await tools.modify_gdscript_method(file_path, method_name, new_method_code, **kwargs)


@tool
async def add_gdscript_method(
    file_path: str,
    method_code: str,
    **kwargs
) -> GDScriptEditResult:
    """Add a new method to a GDScript file.

    Args:
        file_path: Path to the GDScript file
        method_code: Code for the new method
        **kwargs: Additional options (position, backup, etc.)

    Returns:
        GDScriptEditResult containing operation details
    """
    tools = FileTools()
    return await tools.add_gdscript_method(file_path, method_code, **kwargs)


@tool
async def remove_gdscript_method(file_path: str, method_name: str, **kwargs) -> GDScriptEditResult:
    """Remove a method from a GDScript file.

    Args:
        file_path: Path to the GDScript file
        method_name: Name of the method to remove
        **kwargs: Additional options (backup, etc.)

    Returns:
        GDScriptEditResult containing operation details
    """
    tools = FileTools()
    return await tools.remove_gdscript_method(file_path, method_name, **kwargs)


@tool
async def modify_project_setting(
    project_path: str,
    section: str,
    key: str,
    value: Any,
    **kwargs
) -> FileOperationResult:
    """Modify a setting in the Godot project file.

    Args:
        project_path: Path to project.godot file
        section: Configuration section (e.g., "application", "rendering")
        key: Setting key
        value: New value for the setting
        **kwargs: Additional options (backup, etc.)

    Returns:
        FileOperationResult containing operation details
    """
    tools = FileTools()
    return await tools.modify_project_setting(project_path, section, key, value, **kwargs)