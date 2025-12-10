"""
Godot Agno Toolkits.

This module provides Agno-compatible Toolkits for Godot development,
organized by capability and access level:

- GodotReadToolkit: Read-only tools for planning/analysis
- GodotWriteToolkit: File modification tools (with HITL confirmation)
- GodotDebugToolkit: Debug and analysis tools
- GodotDocToolkit: Documentation and web search tools
- GodotExecutorToolkit: Scene/node modification tools (with HITL confirmation)
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import httpx
from bs4 import BeautifulSoup

from agno.tools import Toolkit
from agno.run import RunContext

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions (shared across toolkits)
# =============================================================================

def _get_godot_bridge():
    """Get the Godot bridge instance."""
    from agents.tools.godot_bridge import get_godot_bridge
    return get_godot_bridge()


async def _ensure_godot_connection() -> bool:
    """Ensure Godot connection is active."""
    from agents.tools.godot_bridge import ensure_godot_connection
    return await ensure_godot_connection()


def _resolve_to_project(path_str: str) -> Path:
    """Resolve a path string to an absolute path within the project."""
    if path_str.startswith("res://"):
        path_str = path_str[6:]
    
    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()
    
    bridge = _get_godot_bridge()
    if bridge.project_info and bridge.project_info.project_path:
        return (Path(bridge.project_info.project_path) / path).resolve()
    
    # Fallback: detect project.godot
    current = Path.cwd()
    while current != current.parent:
        if (current / "project.godot").exists():
            return (current / path).resolve()
        current = current.parent
    
    return path.resolve()


def _create_success_response(message: str, data: Optional[Dict] = None) -> str:
    """Create a success response string."""
    if data:
        return f"✅ {message}\n\nData: {data}"
    return f"✅ {message}"


def _create_error_response(message: str, error_type: str = "Error") -> str:
    """Create an error response string."""
    return f"❌ [{error_type}] {message}"


# =============================================================================
# GodotReadToolkit - Read-only tools for planning/analysis
# =============================================================================

class GodotReadToolkit(Toolkit):
    """
    Read-only tools for Godot project analysis and planning.
    
    These tools do not modify any files and are safe for planning mode.
    """
    
    def __init__(self, **kwargs):
        tools = [
            self.read_file,
            self.list_files,
            self.search_codebase,
            self.get_project_overview,
            self.analyze_scene_tree,
        ]
        
        instructions = """Use these tools to read and analyze Godot project files.
        - read_file: Read contents of GDScript, scene, or resource files
        - list_files: List directory contents with pattern filtering
        - search_codebase: Search for patterns in the codebase
        - get_project_overview: Get project structure and current scene info
        - analyze_scene_tree: Analyze the scene tree structure"""
        
        super().__init__(
            name="godot_read_tools",
            tools=tools,
            instructions=instructions,
            **kwargs
        )
    
    async def read_file(self, file_path: str) -> str:
        """
        Read the contents of a file in the Godot project.
        
        Args:
            file_path: Path to the file to read (relative or absolute, supports res:// paths)
        
        Returns:
            File contents or error message
        """
        try:
            resolved_path = _resolve_to_project(file_path)
            
            if not resolved_path.exists():
                return _create_error_response(f"File not found: {file_path}", "FileNotFoundError")
            
            if not resolved_path.is_file():
                return _create_error_response(f"Path is not a file: {file_path}", "PathError")
            
            # Check path safety
            bridge = _get_godot_bridge()
            if not bridge.is_path_safe(resolved_path):
                return _create_error_response(
                    f"Access denied: Path '{file_path}' is outside the project directory",
                    "SecurityError"
                )
            
            async with aiofiles.open(resolved_path, mode='r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
            
            return f"📄 File: {file_path}\n\n{content}"
            
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return _create_error_response(f"Error reading file: {str(e)}", "FileReadError")
    
    async def list_files(self, directory: str = ".", pattern: str = "*") -> str:
        """
        List files and directories with optional pattern filtering.
        
        Args:
            directory: Directory path to list (default: project root)
            pattern: Glob pattern to filter files (e.g., "*.gd", "*.tscn")
        
        Returns:
            Formatted directory listing
        """
        try:
            resolved_path = _resolve_to_project(directory)
            
            if not resolved_path.exists():
                return _create_error_response(f"Directory not found: {directory}", "DirectoryNotFoundError")
            
            if not resolved_path.is_dir():
                return _create_error_response(f"Path is not a directory: {directory}", "PathError")
            
            # List files matching pattern
            files = []
            dirs = []
            
            for item in resolved_path.glob(pattern):
                if item.is_dir():
                    dirs.append(f"📁 {item.name}/")
                else:
                    files.append(f"📄 {item.name}")
            
            dirs.sort()
            files.sort()
            
            result = f"📂 Directory: {directory}\n"
            result += f"Pattern: {pattern}\n\n"
            
            if dirs:
                result += "Directories:\n" + "\n".join(dirs) + "\n\n"
            if files:
                result += "Files:\n" + "\n".join(files)
            
            if not dirs and not files:
                result += "(No matching items found)"
            
            return result
            
        except Exception as e:
            logger.error(f"Error listing directory {directory}: {e}")
            return _create_error_response(f"Error listing directory: {str(e)}", "DirectoryListError")
    
    async def search_codebase(
        self,
        pattern: str,
        file_pattern: str = "*.gd",
        max_results: int = 20
    ) -> str:
        """
        Search for a pattern in the codebase using regex.
        
        Args:
            pattern: Regex pattern to search for
            file_pattern: Glob pattern for files to search (default: "*.gd")
            max_results: Maximum number of results to return
        
        Returns:
            Search results with file paths and matching lines
        """
        try:
            bridge = _get_godot_bridge()
            if bridge.project_info and bridge.project_info.project_path:
                project_root = Path(bridge.project_info.project_path)
            else:
                project_root = Path.cwd()
            
            regex = re.compile(pattern, re.IGNORECASE)
            results = []
            
            for file_path in project_root.rglob(file_pattern):
                if any(part.startswith('.') for part in file_path.parts):
                    continue
                
                try:
                    async with aiofiles.open(file_path, mode='r', encoding='utf-8', errors='ignore') as f:
                        content = await f.read()
                    
                    for i, line in enumerate(content.splitlines(), 1):
                        if regex.search(line):
                            rel_path = file_path.relative_to(project_root)
                            results.append(f"{rel_path}:{i}: {line.strip()}")
                            
                            if len(results) >= max_results:
                                break
                    
                    if len(results) >= max_results:
                        break
                        
                except Exception as e:
                    logger.debug(f"Error reading {file_path}: {e}")
            
            if not results:
                return f"🔍 No matches found for pattern '{pattern}' in {file_pattern} files"
            
            result = f"🔍 Search results for '{pattern}' in {file_pattern}:\n\n"
            result += "\n".join(results)
            
            if len(results) >= max_results:
                result += f"\n\n(Limited to {max_results} results)"
            
            return result
            
        except re.error as e:
            return _create_error_response(f"Invalid regex pattern: {str(e)}", "RegexError")
        except Exception as e:
            logger.error(f"Error searching codebase: {e}")
            return _create_error_response(f"Error searching codebase: {str(e)}", "SearchError")
    
    async def get_project_overview(self) -> str:
        """
        Get an overview of the Godot project structure and current state.
        
        Returns:
            Project information including current scene and file counts
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response(
                    "Failed to connect to Godot. Ensure the editor is running with Godoty plugin active.",
                    "ConnectionError"
                )
            
            bridge = _get_godot_bridge()
            project_info = await bridge.get_project_info()
            
            # Get current scene
            response = await bridge.send_command("get_current_scene_detailed")
            current_scene = response.data if response.success else None
            
            result = "📊 Project Overview\n\n"
            
            if project_info:
                result += f"Project Name: {project_info.project_name or 'Unknown'}\n"
                result += f"Godot Version: {project_info.godot_version or 'Unknown'}\n"
                result += f"Project Path: {project_info.project_path or 'Unknown'}\n\n"
            
            if current_scene:
                result += f"Current Scene: {current_scene.get('scene_path', 'Unknown')}\n"
                root = current_scene.get('root', {})
                result += f"Root Node: {root.get('name', 'Unknown')} ({root.get('type', 'Unknown')})\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting project overview: {e}")
            return _create_error_response(f"Error getting project overview: {str(e)}", "ProjectOverviewError")
    
    async def analyze_scene_tree(self, detailed: bool = False) -> str:
        """
        Analyze the current scene tree structure.
        
        Args:
            detailed: Include detailed node information
        
        Returns:
            Scene tree analysis with node hierarchy
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response(
                    "Failed to connect to Godot",
                    "ConnectionError"
                )
            
            bridge = _get_godot_bridge()
            response = await bridge.send_command("get_current_scene_detailed")
            
            if not response.success:
                return _create_error_response(
                    f"Failed to get scene tree: {response.error}",
                    "SceneTreeError"
                )
            
            scene_data = response.data
            if not scene_data:
                return "No scene currently open in the editor."
            
            def format_node(node: Dict, indent: int = 0) -> str:
                prefix = "  " * indent
                name = node.get("name", "Unknown")
                node_type = node.get("type", "Unknown")
                has_script = "📜" if node.get("script_path") else ""
                
                line = f"{prefix}├─ {name} ({node_type}) {has_script}\n"
                
                for child in node.get("children", []):
                    line += format_node(child, indent + 1)
                
                return line
            
            result = f"🌳 Scene Tree: {scene_data.get('scene_path', 'Unknown')}\n\n"
            root = scene_data.get("root", {})
            result += format_node(root)
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing scene tree: {e}")
            return _create_error_response(f"Error analyzing scene tree: {str(e)}", "SceneTreeError")


# =============================================================================
# GodotWriteToolkit - File modification tools (with HITL confirmation)
# =============================================================================

class GodotWriteToolkit(Toolkit):
    """
    File modification tools for Godot projects.
    
    These tools modify files and require user confirmation via HITL.
    """
    
    def __init__(self, **kwargs):
        tools = [
            self.write_file,
            self.delete_file,
            self.modify_gdscript_method,
            self.add_gdscript_method,
        ]
        
        instructions = """Use these tools to modify Godot project files.
        All file modifications create backups automatically.
        - write_file: Write content to a file
        - delete_file: Delete a file (with backup)
        - modify_gdscript_method: Edit an existing method in a GDScript file
        - add_gdscript_method: Add a new method to a GDScript file"""
        
        super().__init__(
            name="godot_write_tools",
            tools=tools,
            instructions=instructions,
            requires_confirmation_tools=["write_file", "delete_file", "modify_gdscript_method", "add_gdscript_method"],
            **kwargs
        )
        
        self._backup_dir = Path(".godoty_backups")
        self._backup_dir.mkdir(exist_ok=True)
    
    async def _create_backup(self, file_path: Path) -> Optional[Path]:
        """Create a backup of the file before modification."""
        try:
            if not file_path.exists():
                return None
            
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            backup_path = self._backup_dir / backup_name
            
            import shutil
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Failed to create backup for {file_path}: {e}")
            return None
    
    async def write_file(self, file_path: str, content: str, create_dirs: bool = True) -> str:
        """
        Write content to a file in the Godot project.
        
        Args:
            file_path: Path to the file to write
            content: Content to write to the file
            create_dirs: Create parent directories if they don't exist
        
        Returns:
            Success message or error
        """
        try:
            resolved_path = _resolve_to_project(file_path)
            
            # Check path safety
            bridge = _get_godot_bridge()
            if not bridge.is_path_safe(resolved_path):
                return _create_error_response(
                    f"Access denied: Path '{file_path}' is outside the project directory",
                    "SecurityError"
                )
            
            # Create backup if file exists
            backup_path = None
            if resolved_path.exists():
                backup_path = await self._create_backup(resolved_path)
            
            # Create directories if needed
            if create_dirs:
                resolved_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            async with aiofiles.open(resolved_path, mode='w', encoding='utf-8') as f:
                await f.write(content)
            
            result = f"Successfully wrote {len(content)} characters to {file_path}"
            if backup_path:
                result += f"\nBackup created: {backup_path}"
            
            return _create_success_response(result)
            
        except Exception as e:
            logger.error(f"Error writing file {file_path}: {e}")
            return _create_error_response(f"Error writing file: {str(e)}", "FileWriteError")
    
    async def delete_file(self, file_path: str) -> str:
        """
        Delete a file from the Godot project (creates backup first).
        
        Args:
            file_path: Path to the file to delete
        
        Returns:
            Success message or error
        """
        try:
            resolved_path = _resolve_to_project(file_path)
            
            if not resolved_path.exists():
                return _create_error_response(f"File not found: {file_path}", "FileNotFoundError")
            
            # Check path safety
            bridge = _get_godot_bridge()
            if not bridge.is_path_safe(resolved_path):
                return _create_error_response(
                    f"Access denied: Path '{file_path}' is outside the project directory",
                    "SecurityError"
                )
            
            # Create backup before deletion
            backup_path = await self._create_backup(resolved_path)
            
            # Delete file
            resolved_path.unlink()
            
            result = f"Successfully deleted {file_path}"
            if backup_path:
                result += f"\nBackup saved: {backup_path}"
            
            return _create_success_response(result)
            
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return _create_error_response(f"Error deleting file: {str(e)}", "FileDeleteError")
    
    async def modify_gdscript_method(
        self,
        file_path: str,
        method_name: str,
        new_body: str
    ) -> str:
        """
        Modify an existing method in a GDScript file.
        
        Args:
            file_path: Path to the GDScript file
            method_name: Name of the method to modify
            new_body: New method body (indented code)
        
        Returns:
            Success message or error
        """
        try:
            resolved_path = _resolve_to_project(file_path)
            
            if not resolved_path.exists():
                return _create_error_response(f"File not found: {file_path}", "FileNotFoundError")
            
            # Read current content
            async with aiofiles.open(resolved_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
            
            # Find and replace method
            # Pattern matches: func method_name(args): ... until next func or end
            pattern = rf'(func\s+{re.escape(method_name)}\s*\([^)]*\)[^:]*:)(.*?)(?=\nfunc\s|\n(?:class|signal|var|const)\s|\Z)'
            
            match = re.search(pattern, content, re.DOTALL)
            if not match:
                return _create_error_response(
                    f"Method '{method_name}' not found in {file_path}",
                    "MethodNotFoundError"
                )
            
            # Create backup
            await self._create_backup(resolved_path)
            
            # Build new method
            func_signature = match.group(1)
            new_content = content[:match.start()] + func_signature + "\n" + new_body + content[match.end():]
            
            # Write modified content
            async with aiofiles.open(resolved_path, mode='w', encoding='utf-8') as f:
                await f.write(new_content)
            
            return _create_success_response(f"Modified method '{method_name}' in {file_path}")
            
        except Exception as e:
            logger.error(f"Error modifying method {method_name} in {file_path}: {e}")
            return _create_error_response(f"Error modifying method: {str(e)}", "MethodModifyError")
    
    async def add_gdscript_method(
        self,
        file_path: str,
        method_code: str,
        after_method: Optional[str] = None
    ) -> str:
        """
        Add a new method to a GDScript file.
        
        Args:
            file_path: Path to the GDScript file
            method_code: Complete method code including 'func' declaration
            after_method: Insert after this method (if None, appends to end)
        
        Returns:
            Success message or error
        """
        try:
            resolved_path = _resolve_to_project(file_path)
            
            if not resolved_path.exists():
                return _create_error_response(f"File not found: {file_path}", "FileNotFoundError")
            
            # Read current content
            async with aiofiles.open(resolved_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
            
            # Create backup
            await self._create_backup(resolved_path)
            
            if after_method:
                # Find the method and insert after it
                pattern = rf'(func\s+{re.escape(after_method)}\s*\([^)]*\)[^:]*:.*?)(?=\nfunc\s|\n(?:class|signal|var|const)\s|\Z)'
                match = re.search(pattern, content, re.DOTALL)
                
                if match:
                    insert_pos = match.end()
                    new_content = content[:insert_pos] + "\n\n" + method_code + content[insert_pos:]
                else:
                    # Method not found, append to end
                    new_content = content.rstrip() + "\n\n" + method_code + "\n"
            else:
                # Append to end
                new_content = content.rstrip() + "\n\n" + method_code + "\n"
            
            # Write modified content
            async with aiofiles.open(resolved_path, mode='w', encoding='utf-8') as f:
                await f.write(new_content)
            
            # Extract method name for message
            method_match = re.search(r'func\s+(\w+)', method_code)
            method_name = method_match.group(1) if method_match else "new method"
            
            return _create_success_response(f"Added method '{method_name}' to {file_path}")
            
        except Exception as e:
            logger.error(f"Error adding method to {file_path}: {e}")
            return _create_error_response(f"Error adding method: {str(e)}", "MethodAddError")


# =============================================================================
# GodotDebugToolkit - Debug and analysis tools
# =============================================================================

class GodotDebugToolkit(Toolkit):
    """
    Debug and analysis tools for Godot projects.
    
    These tools provide debugging information and performance metrics.
    """
    
    def __init__(self, **kwargs):
        tools = [
            self.get_debug_output,
            self.get_debug_logs,
            self.get_performance_metrics,
            self.capture_editor_viewport,
            self.inspect_scene_file,
        ]
        
        instructions = """Use these tools for debugging and analysis.
        - get_debug_output: Get recent debug output from Godot
        - get_debug_logs: Get and search debug logs
        - get_performance_metrics: Get performance metrics from the running game
        - capture_editor_viewport: Capture viewport for visual analysis
        - inspect_scene_file: Inspect a scene file structure"""
        
        super().__init__(
            name="godot_debug_tools",
            tools=tools,
            instructions=instructions,
            **kwargs
        )
    
    async def get_debug_output(self, lines: int = 100, severity_filter: Optional[str] = None) -> str:
        """
        Get recent debug output from Godot.
        
        Args:
            lines: Number of lines to retrieve
            severity_filter: Filter by severity ("error", "warning", "info")
        
        Returns:
            Debug output messages
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response("Failed to connect to Godot", "ConnectionError")
            
            bridge = _get_godot_bridge()
            response = await bridge.send_command("get_debug_output", limit=lines)
            
            if not response.success:
                return _create_error_response(f"Failed to get debug output: {response.error}", "DebugOutputError")
            
            data = response.data or {}
            messages = data.get("messages", [])
            
            # Filter by severity if specified
            if severity_filter:
                filtered = []
                for msg in messages:
                    if severity_filter.lower() == "error" and ("ERROR" in msg or "[ERROR]" in msg):
                        filtered.append(msg)
                    elif severity_filter.lower() == "warning" and ("WARNING" in msg or "[WARNING]" in msg):
                        filtered.append(msg)
                    elif severity_filter.lower() == "info":
                        filtered.append(msg)
                messages = filtered
            
            if not messages:
                return "📋 No debug messages found"
            
            result = f"📋 Debug Output (last {len(messages)} messages):\n\n"
            result += "\n".join(messages[-lines:])
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting debug output: {e}")
            return _create_error_response(f"Error getting debug output: {str(e)}", "DebugOutputError")
    
    async def get_debug_logs(self, search_pattern: Optional[str] = None) -> str:
        """
        Get debug logs, optionally filtering by search pattern.
        
        Args:
            search_pattern: Regex pattern to filter logs
        
        Returns:
            Filtered debug logs
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response("Failed to connect to Godot", "ConnectionError")
            
            bridge = _get_godot_bridge()
            response = await bridge.send_command("get_debug_output", limit=500)
            
            if not response.success:
                return _create_error_response(f"Failed to get debug logs: {response.error}", "DebugLogError")
            
            data = response.data or {}
            messages = data.get("messages", [])
            
            if search_pattern:
                try:
                    regex = re.compile(search_pattern, re.IGNORECASE)
                    messages = [msg for msg in messages if regex.search(msg)]
                except re.error as e:
                    return _create_error_response(f"Invalid regex pattern: {str(e)}", "RegexError")
            
            if not messages:
                return "📋 No matching debug logs found"
            
            result = f"📋 Debug Logs"
            if search_pattern:
                result += f" (filtered by '{search_pattern}')"
            result += f":\n\n"
            result += "\n".join(messages[-100:])
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting debug logs: {e}")
            return _create_error_response(f"Error getting debug logs: {str(e)}", "DebugLogError")
    
    async def get_performance_metrics(self) -> str:
        """
        Get performance metrics from Godot (FPS, memory usage, etc.).
        
        Returns:
            Performance metrics summary
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response("Failed to connect to Godot", "ConnectionError")
            
            bridge = _get_godot_bridge()
            response = await bridge.send_command("get_performance_metrics")
            
            if not response.success:
                return _create_error_response(
                    f"Failed to get performance metrics: {response.error}",
                    "PerformanceMetricsError"
                )
            
            data = response.data or {}
            
            result = "📊 Performance Metrics:\n\n"
            
            if "fps" in data:
                result += f"FPS: {data['fps']:.1f}\n"
            if "frame_time" in data:
                result += f"Frame Time: {data['frame_time']:.2f}ms\n"
            if "physics_fps" in data:
                result += f"Physics FPS: {data['physics_fps']}\n"
            if "memory" in data:
                mem = data['memory']
                if isinstance(mem, dict):
                    result += f"Memory Static: {mem.get('static', 0) / 1024 / 1024:.1f} MB\n"
                    result += f"Memory Dynamic: {mem.get('dynamic', 0) / 1024 / 1024:.1f} MB\n"
            if "objects" in data:
                result += f"Object Count: {data['objects']}\n"
            if "nodes" in data:
                result += f"Node Count: {data['nodes']}\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return _create_error_response(f"Error getting performance metrics: {str(e)}", "PerformanceMetricsError")
    
    async def capture_editor_viewport(self, include_3d: bool = True) -> str:
        """
        Capture the editor viewport for visual analysis.
        
        Args:
            include_3d: Include 3D viewport if available
        
        Returns:
            Viewport information and state
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response("Failed to connect to Godot", "ConnectionError")
            
            bridge = _get_godot_bridge()
            response = await bridge.send_command("capture_visual_context", include_3d=include_3d)
            
            if not response.success:
                return _create_error_response(
                    f"Failed to capture viewport: {response.error}",
                    "ViewportCaptureError"
                )
            
            data = response.data or {}
            viewport_info = data.get("viewport_info", {})
            editor_state = data.get("editor_state", {})
            
            result = "🖼️ Editor Viewport Capture:\n\n"
            
            if viewport_info:
                size = viewport_info.get("size", {})
                result += f"Viewport Size: {size.get('x', 0)}x{size.get('y', 0)}\n"
            
            if editor_state:
                selected = editor_state.get("selected_nodes", [])
                result += f"Selected Nodes: {len(selected)}\n"
                if selected:
                    result += "  " + "\n  ".join(selected[:5])
                    if len(selected) > 5:
                        result += f"\n  ... and {len(selected) - 5} more"
            
            return result
            
        except Exception as e:
            logger.error(f"Error capturing viewport: {e}")
            return _create_error_response(f"Error capturing viewport: {str(e)}", "ViewportCaptureError")
    
    async def inspect_scene_file(self, scene_path: str) -> str:
        """
        Inspect a scene file structure without opening it.
        
        Args:
            scene_path: Path to the .tscn file to inspect
        
        Returns:
            Scene file structure analysis
        """
        try:
            resolved_path = _resolve_to_project(scene_path)
            
            if not resolved_path.exists():
                return _create_error_response(f"Scene file not found: {scene_path}", "FileNotFoundError")
            
            if not resolved_path.suffix == ".tscn":
                return _create_error_response(f"Not a scene file: {scene_path}", "FileTypeError")
            
            async with aiofiles.open(resolved_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
            
            # Parse basic scene info
            result = f"🎬 Scene File: {scene_path}\n\n"
            
            # Count nodes
            node_matches = re.findall(r'\[node name="([^"]+)" type="([^"]+)"', content)
            result += f"Node Count: {len(node_matches)}\n\n"
            
            if node_matches:
                result += "Nodes:\n"
                for name, node_type in node_matches[:20]:
                    result += f"  - {name} ({node_type})\n"
                if len(node_matches) > 20:
                    result += f"  ... and {len(node_matches) - 20} more nodes\n"
            
            # Find external resources
            ext_resources = re.findall(r'\[ext_resource.*?path="([^"]+)".*?type="([^"]+)"', content)
            if ext_resources:
                result += f"\nExternal Resources ({len(ext_resources)}):\n"
                for path, res_type in ext_resources[:10]:
                    result += f"  - {path} ({res_type})\n"
                if len(ext_resources) > 10:
                    result += f"  ... and {len(ext_resources) - 10} more resources\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error inspecting scene file {scene_path}: {e}")
            return _create_error_response(f"Error inspecting scene file: {str(e)}", "SceneInspectError")


# =============================================================================
# GodotDocToolkit - Documentation and web search tools
# =============================================================================

class GodotDocToolkit(Toolkit):
    """
    Documentation and web search tools.
    
    These tools help find documentation and reference material.
    """
    
    def __init__(self, **kwargs):
        tools = [
            self.search_documentation,
            self.fetch_webpage,
            self.get_godot_api_reference,
        ]
        
        instructions = """Use these tools to find documentation and reference material.
        - search_documentation: Search for documentation on a topic
        - fetch_webpage: Fetch and extract content from a webpage
        - get_godot_api_reference: Get Godot API reference for a class"""
        
        super().__init__(
            name="godot_doc_tools",
            tools=tools,
            instructions=instructions,
            **kwargs
        )
    
    async def search_documentation(self, query: str, source: str = "godot") -> str:
        """
        Search for documentation on a specific topic.
        
        Args:
            query: Search query
            source: Documentation source ("godot", "python", "general")
        
        Returns:
            Search guidance and relevant links
        """
        source_urls = {
            "godot": "https://docs.godotengine.org",
            "python": "https://docs.python.org",
            "fastapi": "https://fastapi.tiangolo.com",
        }
        
        result = f"🔍 Documentation Search: {query}\n\n"
        
        if source in source_urls:
            result += f"Primary source: {source_urls[source]}\n"
            result += f"Search URL: {source_urls[source]}/en/stable/search.html?q={query.replace(' ', '+')}\n\n"
        
        result += "Recommended resources:\n"
        result += "- Godot Docs: https://docs.godotengine.org\n"
        result += "- Godot Q&A: https://godotengine.org/qa/\n"
        result += "- GDScript Reference: https://docs.godotengine.org/en/stable/classes/\n"
        
        return result
    
    async def fetch_webpage(self, url: str, extract_text: bool = True) -> str:
        """
        Fetch and extract content from a webpage.
        
        Args:
            url: URL to fetch
            extract_text: Extract clean text (True) or raw HTML (False)
        
        Returns:
            Webpage content
        """
        try:
            if not url.startswith(('http://', 'https://')):
                return _create_error_response("Invalid URL: must start with http:// or https://", "URLError")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
            
            content_type = response.headers.get('content-type', '')
            
            if 'text/html' not in content_type:
                return f"📄 URL: {url}\n\n{response.text[:2000]}..."
            
            if extract_text:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for script in soup(["script", "style", "meta", "link"]):
                    script.decompose()
                
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)
                
                if len(text) > 5000:
                    text = text[:5000] + "\n\n... (content truncated)"
                
                title = soup.title.string if soup.title else "No title"
                return f"📄 {title}\n\nURL: {url}\n\n{text}"
            else:
                html = response.text
                if len(html) > 5000:
                    html = html[:5000] + "\n\n... (HTML truncated)"
                return f"📄 URL: {url}\n\n{html}"
            
        except httpx.HTTPError as e:
            return _create_error_response(f"HTTP error fetching {url}: {str(e)}", "HTTPError")
        except Exception as e:
            logger.error(f"Error fetching webpage {url}: {e}")
            return _create_error_response(f"Error fetching webpage: {str(e)}", "WebFetchError")
    
    async def get_godot_api_reference(self, class_name: str) -> str:
        """
        Get Godot API reference for a class.
        
        Args:
            class_name: Name of the Godot class (e.g., "Node2D", "Control")
        
        Returns:
            API reference URL and basic info
        """
        docs_url = f"https://docs.godotengine.org/en/stable/classes/class_{class_name.lower()}.html"
        
        result = f"📚 Godot API Reference: {class_name}\n\n"
        result += f"Documentation: {docs_url}\n\n"
        
        # Try to fetch basic info from local docs if available
        try:
            if await _ensure_godot_connection():
                bridge = _get_godot_bridge()
                response = await bridge.send_command("get_class_info", class_name=class_name)
                
                if response.success and response.data:
                    data = response.data
                    if "inherits" in data:
                        result += f"Inherits: {data['inherits']}\n"
                    if "description" in data:
                        result += f"\nDescription:\n{data['description'][:500]}...\n"
        except Exception:
            pass
        
        return result


# =============================================================================
# GodotExecutorToolkit - Scene/node modification tools (with HITL confirmation)
# =============================================================================

class GodotExecutorToolkit(Toolkit):
    """
    Scene and node modification tools for Godot.
    
    These tools modify the scene tree and require user confirmation via HITL.
    """
    
    def __init__(self, **kwargs):
        tools = [
            self.create_node,
            self.modify_node_property,
            self.delete_node,
            self.play_scene,
            self.stop_playing,
        ]
        
        instructions = """Use these tools to modify the Godot scene tree.
        - create_node: Create a new node in the scene tree
        - modify_node_property: Modify a property on an existing node
        - delete_node: Delete a node from the scene tree
        - play_scene: Start playing the current scene
        - stop_playing: Stop the running scene"""
        
        super().__init__(
            name="godot_executor_tools",
            tools=tools,
            instructions=instructions,
            requires_confirmation_tools=["create_node", "modify_node_property", "delete_node"],
            **kwargs
        )
    
    async def create_node(
        self,
        node_type: str,
        parent_path: str,
        node_name: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new node in the Godot scene tree.
        
        Args:
            node_type: Type of node to create (e.g., "Node2D", "Sprite2D")
            parent_path: Path to the parent node (e.g., "/root/Main")
            node_name: Name for the new node (optional)
            properties: Initial properties to set (optional)
        
        Returns:
            Success message with node path or error
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response(
                    "Failed to connect to Godot. Ensure the editor is running.",
                    "ConnectionError"
                )
            
            bridge = _get_godot_bridge()
            
            params = {
                "type": node_type,
                "parent": parent_path
            }
            if node_name:
                params["name"] = node_name
            if properties:
                params["properties"] = properties
            
            response = await bridge.send_command("create_node", **params)
            
            if response.success:
                created_path = response.data.get("path", "unknown")
                return _create_success_response(
                    f"Created {node_type} node at {created_path}",
                    {"path": created_path, "type": node_type}
                )
            else:
                return _create_error_response(
                    f"Failed to create node: {response.error}",
                    "NodeCreationError"
                )
            
        except Exception as e:
            logger.error(f"Error creating node: {e}")
            return _create_error_response(f"Error creating node: {str(e)}", "NodeCreationError")
    
    async def modify_node_property(
        self,
        node_path: str,
        property_name: str,
        property_value: Any
    ) -> str:
        """
        Modify a property on an existing node.
        
        Args:
            node_path: Path to the node (e.g., "/root/Main/Player")
            property_name: Name of the property to modify
            property_value: New value for the property
        
        Returns:
            Success message or error
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response("Failed to connect to Godot", "ConnectionError")
            
            bridge = _get_godot_bridge()
            response = await bridge.send_command(
                "modify_node_property",
                node_path=node_path,
                property_name=property_name,
                property_value=property_value
            )
            
            if response.success:
                return _create_success_response(
                    f"Modified {property_name} on {node_path} to {property_value}"
                )
            else:
                return _create_error_response(
                    f"Failed to modify property: {response.error}",
                    "PropertyModifyError"
                )
            
        except Exception as e:
            logger.error(f"Error modifying node property: {e}")
            return _create_error_response(f"Error modifying property: {str(e)}", "PropertyModifyError")
    
    async def delete_node(self, node_path: str) -> str:
        """
        Delete a node from the scene tree.
        
        Args:
            node_path: Path to the node to delete
        
        Returns:
            Success message or error
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response("Failed to connect to Godot", "ConnectionError")
            
            bridge = _get_godot_bridge()
            response = await bridge.send_command("delete_node", node_path=node_path)
            
            if response.success:
                return _create_success_response(f"Deleted node at {node_path}")
            else:
                return _create_error_response(
                    f"Failed to delete node: {response.error}",
                    "NodeDeletionError"
                )
            
        except Exception as e:
            logger.error(f"Error deleting node: {e}")
            return _create_error_response(f"Error deleting node: {str(e)}", "NodeDeletionError")
    
    async def play_scene(self, scene_path: Optional[str] = None) -> str:
        """
        Start playing the current or specified scene.
        
        Args:
            scene_path: Path to the scene to play (optional, uses current if not specified)
        
        Returns:
            Success message or error
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response("Failed to connect to Godot", "ConnectionError")
            
            bridge = _get_godot_bridge()
            
            params = {}
            if scene_path:
                params["scene_path"] = scene_path
            
            response = await bridge.send_command("play_scene", **params)
            
            if response.success:
                return _create_success_response(
                    f"Started playing scene: {scene_path or 'current scene'}"
                )
            else:
                return _create_error_response(
                    f"Failed to play scene: {response.error}",
                    "PlaySceneError"
                )
            
        except Exception as e:
            logger.error(f"Error playing scene: {e}")
            return _create_error_response(f"Error playing scene: {str(e)}", "PlaySceneError")
    
    async def stop_playing(self) -> str:
        """
        Stop the currently running scene.
        
        Returns:
            Success message or error
        """
        try:
            if not await _ensure_godot_connection():
                return _create_error_response("Failed to connect to Godot", "ConnectionError")
            
            bridge = _get_godot_bridge()
            response = await bridge.send_command("stop_playing")
            
            if response.success:
                return _create_success_response("Stopped playing scene")
            else:
                return _create_error_response(
                    f"Failed to stop scene: {response.error}",
                    "StopSceneError"
                )
            
        except Exception as e:
            logger.error(f"Error stopping scene: {e}")
            return _create_error_response(f"Error stopping scene: {str(e)}", "StopSceneError")
