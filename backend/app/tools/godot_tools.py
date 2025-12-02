"""
Godot-specific tools for the Godoty agent.

Provides tools for working with Godot projects including file operations,
scene analysis, and documentation access.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import xml.etree.ElementTree as ET

from app.config import settings

logger = logging.getLogger(__name__)


class GodotTools:
    """Collection of tools for Godot project analysis and manipulation."""

    def __init__(self, project_path: str):
        """
        Initialize Godot tools with project path.

        Args:
            project_path: Root path of the Godot project
        """
        self.project_path = Path(project_path).resolve()
        self._validate_project_path()

    def _validate_project_path(self) -> None:
        """Validate that the path contains a valid Godot project."""
        project_file = self.project_path / "project.godot"
        if not project_file.exists():
            raise ValueError(f"No project.godot found in {self.project_path}")

        if not project_file.is_file():
            raise ValueError(f"project.godot is not a file in {self.project_path}")

        logger.info(f"Validated Godot project at: {self.project_path}")

    def list_project_files(self, extensions: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """
        List files in the Godot project by category.

        Args:
            extensions: List of file extensions to include (defaults to allowed extensions)

        Returns:
            Dictionary categorizing files by type
        """
        if extensions is None:
            extensions = settings.allowed_file_extensions

        files_by_type = {
            "scripts": [],
            "scenes": [],
            "resources": [],
            "documentation": [],
            "config": [],
            "other": []
        }

        try:
            for file_path in self.project_path.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in extensions:
                    relative_path = file_path.relative_to(self.project_path)
                    path_str = str(relative_path)

                    # Categorize files
                    if file_path.suffix.lower() == ".gd":
                        files_by_type["scripts"].append(path_str)
                    elif file_path.suffix.lower() == ".tscn":
                        files_by_type["scenes"].append(path_str)
                    elif file_path.suffix.lower() == ".tres":
                        files_by_type["resources"].append(path_str)
                    elif file_path.suffix.lower() in [".md", ".txt"]:
                        files_by_type["documentation"].append(path_str)
                    elif file_path.name == "project.godot":
                        files_by_type["config"].append(path_str)
                    else:
                        files_by_type["other"].append(path_str)

            logger.info(f"Found {sum(len(files) for files in files_by_type.values())} project files")
            return files_by_type

        except Exception as e:
            logger.error(f"Error listing project files: {e}")
            raise

    def read_script(self, file_path: str, max_lines: int = 1000) -> Dict[str, Any]:
        """
        Read a Godot script file with security validation.

        Args:
            file_path: Relative path to the script file
            max_lines: Maximum number of lines to read

        Returns:
            Dictionary with file content and metadata
        """
        try:
            # Validate file path
            full_path = self._validate_file_path(file_path)

            # Check file size
            if full_path.stat().st_size > settings.max_file_size:
                raise ValueError(f"File too large: {full_path}")

            # Read file content
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines(max_lines)

            content = ''.join(lines)
            truncated = len(lines) == max_lines and len(lines) == max_lines

            # Extract basic metadata
            metadata = {
                "path": file_path,
                "size_bytes": full_path.stat().st_size,
                "line_count": len(content.splitlines()),
                "language": "gdscript",
                "truncated": truncated
            }

            # Extract class and function names
            metadata.update(self._extract_script_metadata(content))

            logger.info(f"Read script: {file_path} ({metadata['line_count']} lines)")
            return {
                "content": content,
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"Error reading script {file_path}: {e}")
            raise

    def get_scene_tree(self, scene_path: str) -> Dict[str, Any]:
        """
        Parse a .tscn scene file and extract node hierarchy.

        Args:
            scene_path: Relative path to the scene file

        Returns:
            Dictionary with scene structure and node information
        """
        try:
            # Validate file path
            full_path = self._validate_file_path(scene_path)

            if not scene_path.endswith('.tscn'):
                raise ValueError("File must be a .tscn scene file")

            # Parse scene file
            with open(full_path, 'r', encoding='utf-8') as f:
                scene_content = f.read()

            # Extract nodes using regex (simplified parsing)
            nodes = self._parse_scene_nodes(scene_content)

            # Build hierarchy
            root_nodes = [node for node in nodes if node.get("parent") is None]

            scene_info = {
                "path": scene_path,
                "root_nodes": root_nodes,
                "all_nodes": nodes,
                "node_count": len(nodes),
                "scene_content": scene_content if len(scene_content) < 10000 else scene_content[:10000] + "..."
            }

            logger.info(f"Parsed scene: {scene_path} ({len(nodes)} nodes)")
            return scene_info

        except Exception as e:
            logger.error(f"Error parsing scene {scene_path}: {e}")
            raise

    def search_godot_docs(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search through project documentation for relevant information.

        Args:
            query: Search query
            max_results: Maximum number of results to return

        Returns:
            List of search results with content snippets
        """
        try:
            results = []
            search_terms = query.lower().split()

            # Search in documentation files
            for doc_file in self.project_path.rglob("*.md"):
                if doc_file.is_file():
                    try:
                        with open(doc_file, 'r', encoding='utf-8') as f:
                            content = f.read()

                        # Simple keyword matching
                        content_lower = content.lower()
                        relevance_score = sum(1 for term in search_terms if term in content_lower)

                        if relevance_score > 0:
                            # Find relevant snippet
                            snippet = self._extract_search_snippet(content_lower, search_terms)

                            results.append({
                                "file": str(doc_file.relative_to(self.project_path)),
                                "relevance_score": relevance_score,
                                "snippet": snippet,
                                "file_type": "documentation"
                            })

                    except Exception as e:
                        logger.warning(f"Error reading documentation file {doc_file}: {e}")

            # Sort by relevance and limit results
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            return results[:max_results]

        except Exception as e:
            logger.error(f"Error searching documentation: {e}")
            raise

    def _validate_file_path(self, file_path: str) -> Path:
        """
        Validate that a file path is within the project directory.

        Args:
            file_path: File path to validate

        Returns:
            Resolved absolute Path object
        """
        # Normalize and resolve path
        full_path = (self.project_path / file_path).resolve()

        # Ensure path is within project directory
        try:
            full_path.relative_to(self.project_path)
        except ValueError:
            raise ValueError(f"Path outside project directory: {file_path}")

        # Check file extension
        if full_path.suffix.lower() not in settings.allowed_file_extensions:
            raise ValueError(f"File extension not allowed: {full_path.suffix}")

        return full_path

    def _extract_script_metadata(self, content: str) -> Dict[str, Any]:
        """Extract metadata from GDScript content."""
        metadata = {
            "classes": [],
            "functions": [],
            "variables": [],
            "extends": None,
            "tool_script": False
        }

        lines = content.split('\n')

        for line in lines:
            line = line.strip()

            # Check for tool script
            if line == "@tool":
                metadata["tool_script"] = True

            # Extract extends
            elif line.startswith("extends "):
                metadata["extends"] = line[8:].strip()

            # Extract class definitions
            elif line.startswith("class_name "):
                class_name = line[11:].strip()
                if class_name:
                    metadata["classes"].append(class_name)

            # Extract function definitions
            elif line.startswith("func "):
                func_match = re.match(r'func\s+(\w+)\s*\(', line)
                if func_match:
                    metadata["functions"].append(func_match.group(1))

            # Extract variable declarations
            elif line.startswith("var "):
                var_match = re.match(r'var\s+(\w+)', line)
                if var_match:
                    metadata["variables"].append(var_match.group(1))

        return metadata

    def _parse_scene_nodes(self, scene_content: str) -> List[Dict[str, Any]]:
        """Parse nodes from scene file content."""
        nodes = []
        current_node = None
        in_node_section = False

        for line in scene_content.split('\n'):
            line = line.strip()

            if line.startswith('[node name='):
                # Start of new node
                if current_node:
                    nodes.append(current_node)

                # Extract node name and type
                name_match = re.search(r'name="([^"]+)"', line)
                type_match = re.search(r'type="([^"]+)"', line)
                parent_match = re.search(r'parent="([^"]+)"', line)

                current_node = {
                    "name": name_match.group(1) if name_match else "unknown",
                    "type": type_match.group(1) if type_match else "Node",
                    "parent": parent_match.group(1) if parent_match else None,
                    "properties": {}
                }
                in_node_section = True

            elif in_node_section and line and not line.startswith('['):
                # Parse node properties
                if '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        prop_name = parts[0].strip()
                        prop_value = parts[1].strip()
                        current_node["properties"][prop_name] = prop_value

            elif line.startswith('[') and not line.startswith('[node name='):
                # End of node section
                if current_node:
                    nodes.append(current_node)
                    current_node = None
                in_node_section = False

        # Add last node if exists
        if current_node:
            nodes.append(current_node)

        return nodes

    def _extract_search_snippet(self, content: str, search_terms: List[str]) -> str:
        """Extract a relevant snippet from content based on search terms."""
        lines = content.split('\n')

        best_line_idx = -1
        best_score = 0

        for i, line in enumerate(lines):
            score = sum(1 for term in search_terms if term in line.lower())
            if score > best_score:
                best_score = score
                best_line_idx = i

        if best_line_idx >= 0:
            # Return snippet around the best matching line
            start = max(0, best_line_idx - 2)
            end = min(len(lines), best_line_idx + 3)
            return '\n'.join(lines[start:end])

        return ""