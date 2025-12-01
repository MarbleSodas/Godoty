"""
Multi-language Code Parser for Enhanced RAG

This module provides advanced parsing capabilities for multiple programming languages
used in Godot projects, enabling semantic chunking and dependency extraction.
"""

import re
import ast
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ParsedElement:
    """Represents a parsed code element with metadata."""
    name: str
    type: str  # 'function', 'class', 'method', 'property', 'variable', 'import'
    content: str
    start_line: int
    end_line: int
    language: str
    dependencies: List[str]
    metadata: Dict[str, Any]


class CodeParser:
    """
    Multi-language code parser for semantic understanding and chunking.

    Supports:
    - GDScript: Functions, classes, methods, properties, signals
    - C#: Classes, methods, properties, fields, namespaces
    - TypeScript/JavaScript: Classes, functions, interfaces, types
    - Python: Functions, classes, methods, imports, decorators
    - JSON/Configuration: Structured data parsing
    - Godot Scenes/Resources: Node hierarchy and properties
    """

    def __init__(self):
        self.parsers = {
            'gdscript': self._parse_gdscript,
            'csharp': self._parse_csharp,
            'python': self._parse_python,
            'typescript': self._parse_typescript,
            'javascript': self._parse_javascript,
            'json': self._parse_json,
            'godot_scene': self._parse_godot_scene,
            'godot_resource': self._parse_godot_resource,
        }

    def parse_file(self, file_path: str, content: str) -> List[ParsedElement]:
        """
        Parse a file and extract semantic elements.

        Args:
            file_path: Path to the file
            content: File content

        Returns:
            List of parsed elements
        """
        file_ext = Path(file_path).suffix.lower()
        language = self._detect_language(file_ext, content)

        if language in self.parsers:
            try:
                return self.parsers[language](content)
            except Exception as e:
                logger.error(f"Error parsing {file_path} as {language}: {e}")
                return self._parse_generic(content, language)
        else:
            return self._parse_generic(content, language)

    def _detect_language(self, file_ext: str, content: str) -> str:
        """Detect the programming language from file extension and content."""
        ext_to_lang = {
            '.gd': 'gdscript',
            '.cs': 'csharp',
            '.py': 'python',
            '.ts': 'typescript',
            '.js': 'javascript',
            '.json': 'json',
            '.tscn': 'godot_scene',
            '.tres': 'godot_resource',
            '.cfg': 'json',
            '.import': 'godot_resource',
            '.remap': 'godot_resource',
        }

        language = ext_to_lang.get(file_ext, 'text')

        # Additional content-based detection
        if language == 'text':
            if 'extends Resource' in content or 'extends Node' in content:
                language = 'gdscript'
            elif 'using Godot;' in content or 'using UnityEngine;' in content:
                language = 'csharp'
            elif 'import ' in content and 'def ' in content:
                language = 'python'

        return language

    def _parse_gdscript(self, content: str) -> List[ParsedElement]:
        """Parse GDScript code."""
        elements = []
        lines = content.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                i += 1
                continue

            # Class definition
            if line.startswith('class '):
                element = self._parse_gdscript_class(lines, i)
                if element:
                    elements.append(element)
                i = element.end_line
                continue

            # Function/method definition
            elif line.startswith('func '):
                element = self._parse_gdscript_function(lines, i)
                if element:
                    elements.append(element)
                i = element.end_line
                continue

            # Variable declaration
            elif line.startswith('var '):
                element = self._parse_gdscript_variable(lines, i)
                if element:
                    elements.append(element)
                i += 1
                continue

            # Signal declaration
            elif line.startswith('signal '):
                element = self._parse_gdscript_signal(lines, i)
                if element:
                    elements.append(element)
                i += 1
                continue

            # Enum declaration
            elif line.startswith('enum '):
                element = self._parse_gdscript_enum(lines, i)
                if element:
                    elements.append(element)
                i = element.end_line
                continue

            # Export variable
            elif line.startswith('@export'):
                element = self._parse_gdscript_export(lines, i)
                if element:
                    elements.append(element)
                    i = element.end_line
                    continue

            i += 1

        return elements

    def _parse_gdscript_class(self, lines: List[str], start_idx: int) -> Optional[ParsedElement]:
        """Parse GDScript class definition."""
        line = lines[start_idx].strip()

        # Extract class name and inheritance
        class_match = re.match(r'class\s+(\w+)(?:\s*:\s*([^\n]+))?', line)
        if not class_match:
            return None

        class_name = class_match.group(1)
        inheritance = class_match.group(2) if class_match.group(2) else ""

        # Find end of class
        end_line = start_idx + 1
        indent_level = len(lines[start_idx]) - len(lines[start_idx].lstrip())

        while end_line < len(lines):
            current_line = lines[end_line]
            if current_line.strip() and len(current_line) - len(current_line.lstrip()) <= indent_level:
                if not current_line.strip().startswith('#'):
                    break
            end_line += 1

        class_content = '\n'.join(lines[start_idx:end_line])
        dependencies = [inheritance.strip()] if inheritance else []

        # Add extends dependencies
        if 'extends ' in class_content:
            extends_match = re.search(r'extends\s+(\w+)', class_content)
            if extends_match:
                dependencies.append(extends_match.group(1))

        return ParsedElement(
            name=class_name,
            type='class',
            content=class_content,
            start_line=start_idx + 1,
            end_line=end_line,
            language='gdscript',
            dependencies=dependencies,
            metadata={
                'inheritance': inheritance,
                'functions': self._extract_functions_from_content(class_content),
                'properties': self._extract_properties_from_content(class_content)
            }
        )

    def _parse_gdscript_function(self, lines: List[str], start_idx: int) -> Optional[ParsedElement]:
        """Parse GDScript function/method definition."""
        line = lines[start_idx].strip()

        # Extract function name and parameters
        func_match = re.match(r'func\s+(\w+)\s*\(([^)]*)\)', line)
        if not func_match:
            return None

        func_name = func_match.group(1)
        params = func_match.group(2)

        # Find end of function
        end_line = start_idx + 1
        indent_level = len(lines[start_idx]) - len(lines[start_idx].lstrip())

        while end_line < len(lines):
            current_line = lines[end_line]
            if current_line.strip() and len(current_line) - len(current_line.lstrip()) <= indent_level:
                if not current_line.strip().startswith('#'):
                    break
            end_line += 1

        func_content = '\n'.join(lines[start_idx:end_line])
        dependencies = self._extract_function_dependencies(func_content)

        return ParsedElement(
            name=func_name,
            type='function',
            content=func_content,
            start_line=start_idx + 1,
            end_line=end_line,
            language='gdscript',
            dependencies=dependencies,
            metadata={
                'parameters': params,
                'return_type': self._extract_return_type(func_content),
                'is_private': func_name.startswith('_'),
                'is_static': 'static' in line
            }
        )

    def _parse_gdscript_variable(self, lines: List[str], start_idx: int) -> Optional[ParsedElement]:
        """Parse GDScript variable declaration."""
        line = lines[start_idx].strip()

        # Extract variable name and type
        var_match = re.match(r'var\s+(\w+)(?:\s*:\s*([^\n=]+))?', line)
        if not var_match:
            return None

        var_name = var_match.group(1)
        var_type = var_match.group(2).strip() if var_match.group(2) else "dynamic"

        # Check for export
        is_exported = '@export' in lines[max(0, start_idx-1):start_idx]

        return ParsedElement(
            name=var_name,
            type='variable',
            content=line,
            start_line=start_idx + 1,
            end_line=start_idx + 1,
            language='gdscript',
            dependencies=[],
            metadata={
                'variable_type': var_type,
                'is_exported': is_exported,
                'is_private': var_name.startswith('_'),
                'has_default_value': '=' in line
            }
        )

    def _parse_gdscript_signal(self, lines: List[str], start_idx: int) -> Optional[ParsedElement]:
        """Parse GDScript signal declaration."""
        line = lines[start_idx].strip()

        signal_match = re.match(r'signal\s+(\w+)\s*\(([^)]*)\)', line)
        if not signal_match:
            return None

        signal_name = signal_match.group(1)
        params = signal_match.group(2)

        return ParsedElement(
            name=signal_name,
            type='signal',
            content=line,
            start_line=start_idx + 1,
            end_line=start_idx + 1,
            language='gdscript',
            dependencies=[],
            metadata={
                'parameters': params,
                'parameter_count': len([p.strip() for p in params.split(',') if p.strip()]) if params else 0
            }
        )

    def _parse_gdscript_enum(self, lines: List[str], start_idx: int) -> Optional[ParsedElement]:
        """Parse GDScript enum declaration."""
        line = lines[start_idx].strip()

        enum_match = re.match(r'enum\s+(\w+)', line)
        if not enum_match:
            return None

        enum_name = enum_match.group(1)

        # Find end of enum
        end_line = start_idx + 1
        while end_line < len(lines) and not lines[end_line].strip() == '}':
            end_line += 1

        enum_content = '\n'.join(lines[start_idx:end_line + 1])
        values = self._extract_enum_values(enum_content)

        return ParsedElement(
            name=enum_name,
            type='enum',
            content=enum_content,
            start_line=start_idx + 1,
            end_line=end_line + 1,
            language='gdscript',
            dependencies=[],
            metadata={
                'values': values,
                'value_count': len(values)
            }
        )

    def _parse_gdscript_export(self, lines: List[str], start_idx: int) -> Optional[ParsedElement]:
        """Parse GDScript exported variable."""
        # Handle @export decorator
        decorator_line = lines[start_idx].strip()
        if not decorator_line.startswith('@export'):
            return None

        # Next line should be the variable
        if start_idx + 1 >= len(lines):
            return None

        var_element = self._parse_gdscript_variable(lines, start_idx + 1)
        if var_element:
            var_element.metadata['is_exported'] = True
            var_element.metadata['export_decorator'] = decorator_line
            var_element.start_line = start_idx + 1
            var_element.content = decorator_line + '\n' + var_element.content

        return var_element

    def _parse_csharp(self, content: str) -> List[ParsedElement]:
        """Parse C# code."""
        elements = []

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    element = self._parse_csharp_class_from_ast(node, content)
                    if element:
                        elements.append(element)
                elif isinstance(node, ast.FunctionDef):
                    element = self._parse_csharp_function_from_ast(node, content)
                    if element:
                        elements.append(element)

        except Exception as e:
            logger.debug(f"AST parsing failed for C#, falling back to regex: {e}")
            elements.extend(self._parse_csharp_regex(content))

        return elements

    def _parse_csharp_regex(self, content: str) -> List[ParsedElement]:
        """Parse C# code using regex patterns."""
        elements = []
        lines = content.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip comments and empty lines
            if not line or line.startswith('//') or line.startswith('/*'):
                i += 1
                continue

            # Class definition
            class_match = re.match(r'(?:public\s+|private\s+|protected\s+|internal\s+)*class\s+(\w+)', line)
            if class_match:
                element = self._parse_csharp_class_regex(lines, i, class_match.group(1))
                if element:
                    elements.append(element)
                i = element.end_line
                continue

            # Method definition
            method_match = re.match(r'(?:public\s+|private\s+|protected\s+|internal\s+|static\s+|virtual\s+|override\s+)*(?:\w+\s+)*(\w+)\s*\(', line)
            if method_match:
                element = self._parse_csharp_method_regex(lines, i, method_match.group(1))
                if element:
                    elements.append(element)
                i = element.end_line
                continue

            i += 1

        return elements

    def _parse_csharp_class_regex(self, lines: List[str], start_idx: int, class_name: str) -> ParsedElement:
        """Parse C# class using regex."""
        # Find class content
        end_line = start_idx + 1
        brace_count = 0

        for i in range(start_idx, len(lines)):
            line = lines[i]
            brace_count += line.count('{') - line.count('}')
            if brace_count > 0 and i > start_idx:
                end_line = i + 1
                if brace_count == 0:
                    break

        class_content = '\n'.join(lines[start_idx:end_line])

        return ParsedElement(
            name=class_name,
            type='class',
            content=class_content,
            start_line=start_idx + 1,
            end_line=end_line,
            language='csharp',
            dependencies=[],
            metadata={
                'methods': self._extract_csharp_methods(class_content),
                'properties': self._extract_csharp_properties(class_content)
            }
        )

    def _parse_csharp_method_regex(self, lines: List[str], start_idx: int, method_name: str) -> ParsedElement:
        """Parse C# method using regex."""
        # Find method content (simple approach)
        end_line = start_idx + 1
        brace_count = 0
        found_opening = False

        for i in range(start_idx, len(lines)):
            line = lines[i]
            if '{' in line:
                found_opening = True
            if found_opening:
                brace_count += line.count('{') - line.count('}')
                if brace_count > 0 and i > start_idx:
                    end_line = i + 1
                    if brace_count == 0:
                        break

        method_content = '\n'.join(lines[start_idx:end_line])

        return ParsedElement(
            name=method_name,
            type='method',
            content=method_content,
            start_line=start_idx + 1,
            end_line=end_line,
            language='csharp',
            dependencies=self._extract_csharp_dependencies(method_content),
            metadata={}
        )

    def _parse_python(self, content: str) -> List[ParsedElement]:
        """Parse Python code."""
        elements = []

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    element = self._parse_python_class(node, content)
                    if element:
                        elements.append(element)
                elif isinstance(node, ast.FunctionDef):
                    element = self._parse_python_function(node, content)
                    if element:
                        elements.append(element)
                elif isinstance(node, ast.Import):
                    element = self._parse_python_import(node, content)
                    if element:
                        elements.append(element)
                elif isinstance(node, ast.ImportFrom):
                    element = self._parse_python_import_from(node, content)
                    if element:
                        elements.append(element)

        except Exception as e:
            logger.error(f"Python AST parsing failed: {e}")
            # Fall back to regex parsing
            elements.extend(self._parse_python_regex(content))

        return elements

    def _parse_python_class(self, node: ast.ClassDef, content: str) -> ParsedElement:
        """Parse Python class from AST node."""
        class_content = ast.get_source_segment(content, node) or ""

        return ParsedElement(
            name=node.name,
            type='class',
            content=class_content,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            language='python',
            dependencies=[base.id for base in node.bases if isinstance(base, ast.Name)],
            metadata={
                'bases': [ast.dump(base) for base in node.bases],
                'methods': [method.name for method in node.body if isinstance(method, ast.FunctionDef)],
                'docstring': ast.get_docstring(node)
            }
        )

    def _parse_python_function(self, node: ast.FunctionDef, content: str) -> ParsedElement:
        """Parse Python function from AST node."""
        func_content = ast.get_source_segment(content, node) or ""

        return ParsedElement(
            name=node.name,
            type='function',
            content=func_content,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            language='python',
            dependencies=[],
            metadata={
                'args': [arg.arg for arg in node.args.args],
                'defaults': len(node.args.defaults),
                'returns': ast.dump(node.returns) if node.returns else None,
                'docstring': ast.get_docstring(node),
                'is_async': isinstance(node, ast.AsyncFunctionDef)
            }
        )

    def _parse_python_import(self, node: ast.Import, content: str) -> ParsedElement:
        """Parse Python import statement."""
        import_names = [alias.name for alias in node.names]
        import_content = ast.get_source_segment(content, node) or ""

        return ParsedElement(
            name=', '.join(import_names),
            type='import',
            content=import_content,
            start_line=node.lineno,
            end_line=node.lineno,
            language='python',
            dependencies=import_names,
            metadata={'modules': import_names}
        )

    def _parse_python_import_from(self, node: ast.ImportFrom, content: str) -> ParsedElement:
        """Parse Python from import statement."""
        import_names = [alias.name for alias in node.names]
        module = node.module or ""
        import_content = ast.get_source_segment(content, node) or ""

        return ParsedElement(
            name=f"{module}.{', '.join(import_names)}" if module else ', '.join(import_names),
            type='import',
            content=import_content,
            start_line=node.lineno,
            end_line=node.lineno,
            language='python',
            dependencies=[module] if module else [],
            metadata={
                'module': module,
                'imports': import_names
            }
        )

    def _parse_python_regex(self, content: str) -> List[ParsedElement]:
        """Parse Python code using regex patterns."""
        elements = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line = line.strip()

            # Import statements
            if line.startswith('import '):
                elements.append(ParsedElement(
                    name=line[7:],
                    type='import',
                    content=line,
                    start_line=i + 1,
                    end_line=i + 1,
                    language='python',
                    dependencies=[],
                    metadata={}
                ))
            elif line.startswith('from '):
                elements.append(ParsedElement(
                    name=line,
                    type='import',
                    content=line,
                    start_line=i + 1,
                    end_line=i + 1,
                    language='python',
                    dependencies=[],
                    metadata={}
                ))

        return elements

    def _parse_typescript(self, content: str) -> List[ParsedElement]:
        """Parse TypeScript code."""
        # For now, delegate to JavaScript parsing with TypeScript awareness
        return self._parse_javascript(content, language='typescript')

    def _parse_javascript(self, content: str, language: str = 'javascript') -> List[ParsedElement]:
        """Parse JavaScript/TypeScript code."""
        elements = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line = line.strip()

            # Function declaration
            if line.startswith('function ') or line.startswith('async function '):
                func_match = re.match(r'(?:async\s+)?function\s+(\w+)\s*\(', line)
                if func_match:
                    elements.append(ParsedElement(
                        name=func_match.group(1),
                        type='function',
                        content=line,
                        start_line=i + 1,
                        end_line=i + 1,
                        language=language,
                        dependencies=[],
                        metadata={'is_async': 'async' in line}
                    ))

            # Class declaration
            elif line.startswith('class '):
                class_match = re.match(r'class\s+(\w+)', line)
                if class_match:
                    elements.append(ParsedElement(
                        name=class_match.group(1),
                        type='class',
                        content=line,
                        start_line=i + 1,
                        end_line=i + 1,
                        language=language,
                        dependencies=[],
                        metadata={}
                    ))

            # Export statement
            elif line.startswith('export '):
                elements.append(ParsedElement(
                    name=line[7:],
                    type='export',
                    content=line,
                    start_line=i + 1,
                    end_line=i + 1,
                    language=language,
                    dependencies=[],
                    metadata={}
                ))

            # Import statement
            elif line.startswith('import '):
                elements.append(ParsedElement(
                    name=line[7:],
                    type='import',
                    content=line,
                    start_line=i + 1,
                    end_line=i + 1,
                    language=language,
                    dependencies=[],
                    metadata={}
                ))

        return elements

    def _parse_json(self, content: str) -> List[ParsedElement]:
        """Parse JSON configuration files."""
        elements = []

        try:
            data = json.loads(content)

            # Create element for the entire JSON structure
            elements.append(ParsedElement(
                name="configuration",
                type='config',
                content=content,
                start_line=1,
                end_line=len(content.split('\n')),
                language='json',
                dependencies=[],
                metadata={
                    'keys': list(data.keys()) if isinstance(data, dict) else 'root_object',
                    'type': type(data).__name__
                }
            ))

        except json.JSONDecodeError as e:
            # Try to parse partially or create generic element
            elements.append(ParsedElement(
                name="invalid_json",
                type='config',
                content=content,
                start_line=1,
                end_line=len(content.split('\n')),
                language='json',
                dependencies=[],
                metadata={'parse_error': str(e)}
            ))

        return elements

    def _parse_godot_scene(self, content: str) -> List[ParsedElement]:
        """Parse Godot scene files (.tscn)."""
        elements = []
        lines = content.split('\n')

        # Find the scene type
        scene_type = ""
        for line in lines:
            if line.startswith('[gd_scene ') or line.startswith('[gd_resource '):
                scene_type = line
                break

        # Parse node hierarchy
        current_node_path = []
        for i, line in enumerate(lines):
            if line.startswith('[') and line.endswith(']'):
                element_type = line[1:-1]

                if element_type.startswith('node ') or element_type.startswith('resource '):
                    # Extract node/resource name
                    parts = element_type.split('"')
                    if len(parts) >= 2:
                        name = parts[1]

                        elements.append(ParsedElement(
                            name=name,
                            type='node' if 'node' in element_type else 'resource',
                            content=line,
                            start_line=i + 1,
                            end_line=i + 1,
                            language='godot_scene',
                            dependencies=current_node_path.copy(),
                            metadata={
                                'node_type': element_type,
                                'depth': len(current_node_path),
                                'scene_type': scene_type
                            }
                        ))

                        if 'node' in element_type:
                            current_node_path.append(name)

            elif line.startswith('}') and current_node_path:
                current_node_path.pop()

        # Add scene metadata element
        if scene_type:
            elements.append(ParsedElement(
                name="scene_metadata",
                type='metadata',
                content=scene_type,
                start_line=1,
                end_line=1,
                language='godot_scene',
                dependencies=[],
                metadata={'scene_header': scene_type}
            ))

        return elements

    def _parse_godot_resource(self, content: str) -> List[ParsedElement]:
        """Parse Godot resource files (.tres)."""
        elements = []
        lines = content.split('\n')

        # Find the resource type
        resource_type = ""
        for line in lines:
            if line.startswith('[gd_resource ') or line.startswith('[ext_resource ') or line.startswith('[sub_resource '):
                resource_type = line
                break

        # Parse resource properties
        for i, line in enumerate(lines):
            if '=' in line and not line.strip().startswith('['):
                # Property assignment
                parts = line.split('=', 1)
                if len(parts) == 2:
                    prop_name = parts[0].strip()
                    prop_value = parts[1].strip()

                    elements.append(ParsedElement(
                        name=prop_name,
                        type='property',
                        content=line,
                        start_line=i + 1,
                        end_line=i + 1,
                        language='godot_resource',
                        dependencies=[],
                        metadata={
                            'value': prop_value,
                            'resource_type': resource_type
                        }
                    ))

        # Add resource metadata element
        if resource_type:
            elements.append(ParsedElement(
                name="resource_metadata",
                type='metadata',
                content=resource_type,
                start_line=1,
                end_line=1,
                language='godot_resource',
                dependencies=[],
                metadata={'resource_header': resource_type}
            ))

        return elements

    def _parse_generic(self, content: str, language: str) -> List[ParsedElement]:
        """Parse generic text content."""
        elements = []
        lines = content.split('\n')

        # Create chunks for meaningful content
        chunk_size = 20
        for i in range(0, len(lines), chunk_size):
            chunk_lines = lines[i:i + chunk_size]
            chunk_content = '\n'.join(chunk_lines)

            # Skip empty chunks
            if not chunk_content.strip():
                continue

            elements.append(ParsedElement(
                name=f"chunk_{i // chunk_size + 1}",
                type='chunk',
                content=chunk_content,
                start_line=i + 1,
                end_line=min(i + chunk_size, len(lines)),
                language=language,
                dependencies=[],
                metadata={
                    'chunk_index': i // chunk_size + 1,
                    'line_count': len(chunk_lines)
                }
            ))

        return elements

    # Helper methods
    def _extract_functions_from_content(self, content: str) -> List[str]:
        """Extract function names from content."""
        functions = []
        for match in re.finditer(r'func\s+(\w+)', content):
            functions.append(match.group(1))
        return functions

    def _extract_properties_from_content(self, content: str) -> List[str]:
        """Extract property names from content."""
        properties = []
        for match in re.finditer(r'var\s+(\w+)', content):
            properties.append(match.group(1))
        return properties

    def _extract_function_dependencies(self, content: str) -> List[str]:
        """Extract dependencies from function content."""
        dependencies = []

        # Extract function calls
        for match in re.finditer(r'(\w+)\(', content):
            func_name = match.group(1)
            if func_name not in ['if', 'while', 'for', 'func', 'class', 'var', 'return']:
                dependencies.append(func_name)

        # Extract property accesses
        for match in re.finditer(r'\.(\w+)', content):
            prop_name = match.group(1)
            dependencies.append(prop_name)

        return list(set(dependencies))

    def _extract_return_type(self, content: str) -> str:
        """Extract return type from function."""
        match = re.search(r'->\s*([^\n:]+)', content)
        return match.group(1).strip() if match else "void"

    def _extract_enum_values(self, content: str) -> List[str]:
        """Extract enum values."""
        values = []
        in_enum = False

        for line in content.split('\n'):
            line = line.strip()

            if line.startswith('enum '):
                in_enum = True
                continue
            elif in_enum and line == '}':
                break
            elif in_enum and '=' in line and not line.startswith('#'):
                value = line.split('=')[0].strip()
                if value:
                    values.append(value)

        return values

    def _extract_csharp_methods(self, content: str) -> List[str]:
        """Extract C# method names."""
        methods = []
        for match in re.finditer(r'(?:public\s+|private\s+|protected\s+|internal\s+|static\s+|virtual\s+|override\s+)*(?:\w+\s+)*(\w+)\s*\(', content):
            methods.append(match.group(1))
        return list(set(methods))

    def _extract_csharp_properties(self, content: str) -> List[str]:
        """Extract C# property names."""
        properties = []
        for match in re.finditer(r'(?:public\s+|private\s+|protected\s+|internal\s+|static\s+)*(?:\w+\s+)(\w+)\s*{', content):
            properties.append(match.group(1))
        return list(set(properties))

    def _extract_csharp_dependencies(self, content: str) -> List[str]:
        """Extract dependencies from C# content."""
        dependencies = []

        # Extract type references
        for match in re.finditer(r'new\s+(\w+)', content):
            dependencies.append(match.group(1))

        # Extract method calls
        for match in re.finditer(r'(\w+)\(', content):
            func_name = match.group(1)
            if func_name not in ['if', 'while', 'for', 'foreach', 'switch', 'return', 'throw', 'using']:
                dependencies.append(func_name)

        return list(set(dependencies))

    def _parse_csharp_class_from_ast(self, node, content: str) -> Optional[ParsedElement]:
        """Parse C# class from AST (placeholder)."""
        # This would require a proper C# parser
        return None

    def _parse_csharp_function_from_ast(self, node, content: str) -> Optional[ParsedElement]:
        """Parse C# function from AST (placeholder)."""
        # This would require a proper C# parser
        return None