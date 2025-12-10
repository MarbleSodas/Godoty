"""
Godot File Parsers Module.

This module provides parsers for Godot-specific file formats:
- .tscn (Text Scene files)
- .tres (Text Resource files)
- .gd (GDScript files)
- project.godot (Project configuration)

Uses regex-based parsing optimized for real-time indexing.
"""

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ExtResource:
    """External resource reference (script, texture, scene, etc.)."""
    id: str
    path: str
    type: str
    uid: Optional[str] = None


@dataclass
class SubResource:
    """Inline sub-resource definition."""
    id: str
    type: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneNode:
    """Node in a scene tree."""
    name: str
    type: str
    parent: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    instance: Optional[str] = None  # For instanced scenes
    script: Optional[str] = None
    groups: List[str] = field(default_factory=list)


@dataclass
class SignalConnection:
    """Signal connection between nodes."""
    signal: str
    from_node: str
    to_node: str
    method: str
    flags: int = 0
    binds: List[Any] = field(default_factory=list)


@dataclass
class ParsedScene:
    """Complete parsed scene file."""
    path: str
    uid: Optional[str]
    format_version: int
    ext_resources: Dict[str, ExtResource]
    sub_resources: Dict[str, SubResource]
    nodes: List[SceneNode]
    connections: List[SignalConnection]
    root_node: Optional[SceneNode] = None
    
    def get_node_tree(self) -> Dict[str, Any]:
        """Build hierarchical tree structure."""
        tree = {}
        node_map = {n.name: n for n in self.nodes}
        
        for node in self.nodes:
            if node.parent is None or node.parent == ".":
                tree[node.name] = {"node": node, "children": {}}
            else:
                # Find parent in tree and add as child
                parent_path = node.parent
                parent_name = parent_path.split("/")[-1] if "/" in parent_path else parent_path
                if parent_name in node_map:
                    # Build path from parent
                    pass  # Simplified for now
        return tree


@dataclass
class FunctionInfo:
    """Information about a GDScript function."""
    name: str
    parameters: List[Tuple[str, Optional[str]]]  # (name, type_hint)
    return_type: Optional[str]
    docstring: Optional[str]
    line_number: int
    is_static: bool = False
    is_virtual: bool = False  # Starts with _


@dataclass
class ExportInfo:
    """Information about an @export variable."""
    name: str
    type: str
    default_value: Optional[str]
    hint: Optional[str] = None
    line_number: int = 0


@dataclass
class SignalDefInfo:
    """Signal definition in a GDScript."""
    name: str
    parameters: List[Tuple[str, Optional[str]]]
    line_number: int


@dataclass
class GDScriptInfo:
    """Parsed GDScript file information."""
    path: str
    class_name: Optional[str]
    extends: str
    functions: List[FunctionInfo]
    signals: List[SignalDefInfo]
    exports: List[ExportInfo]
    docstring: Optional[str]
    constants: Dict[str, Any] = field(default_factory=dict)
    onready_vars: List[str] = field(default_factory=list)


@dataclass
class ParsedResource:
    """Parsed .tres resource file."""
    path: str
    type: str
    uid: Optional[str]
    properties: Dict[str, Any]
    ext_resources: Dict[str, ExtResource]
    sub_resources: Dict[str, SubResource]


@dataclass
class ProjectConfig:
    """Parsed project.godot configuration."""
    project_name: str
    config_version: int
    features: List[str]
    autoloads: Dict[str, str]  # name -> path
    input_actions: Dict[str, List[Dict[str, Any]]]
    settings: Dict[str, Dict[str, Any]]  # section -> key -> value


# =============================================================================
# Regex Patterns
# =============================================================================

class GodotPatterns:
    """Compiled regex patterns for Godot file parsing."""
    
    # Scene/Resource header
    SCENE_HEADER = re.compile(
        r'\[gd_scene\s+(?:load_steps=(\d+)\s+)?format=(\d+)(?:\s+uid="([^"]+)")?\]'
    )
    RESOURCE_HEADER = re.compile(
        r'\[gd_resource\s+type="([^"]+)"(?:\s+script_class="([^"]+)")?(?:\s+load_steps=(\d+))?\s+format=(\d+)(?:\s+uid="([^"]+)")?\]'
    )
    
    # External resources
    EXT_RESOURCE = re.compile(
        r'\[ext_resource\s+(?:type="([^"]+)"\s+)?(?:uid="([^"]+)"\s+)?path="([^"]+)"(?:\s+type="([^"]+)")?(?:\s+uid="([^"]+)")?\s+id="([^"]+)"\]'
    )
    
    # Alternative ext_resource format (Godot 4.x)
    EXT_RESOURCE_V4 = re.compile(
        r'\[ext_resource\s+type="([^"]+)"\s+(?:uid="([^"]+)"\s+)?path="([^"]+)"\s+id="([^"]+)"\]'
    )
    
    # Sub-resources
    SUB_RESOURCE = re.compile(
        r'\[sub_resource\s+type="([^"]+)"\s+id="([^"]+)"\]'
    )
    
    # Nodes
    NODE = re.compile(
        r'\[node\s+name="([^"]+)"(?:\s+type="([^"]+)")?(?:\s+parent="([^"]+)")?(?:\s+instance=ExtResource\("([^"]+)"\))?(?:\s+groups=\[([^\]]*)\])?\]'
    )
    
    # Signal connections
    CONNECTION = re.compile(
        r'\[connection\s+signal="([^"]+)"\s+from="([^"]+)"\s+to="([^"]+)"\s+method="([^"]+)"(?:\s+flags=(\d+))?(?:\s+binds=\[([^\]]*)\])?\]'
    )
    
    # Property assignment
    PROPERTY = re.compile(r'^(\w+)\s*=\s*(.+)$', re.MULTILINE)
    
    # GDScript patterns
    GDSCRIPT_CLASS_NAME = re.compile(r'^class_name\s+(\w+)', re.MULTILINE)
    GDSCRIPT_EXTENDS = re.compile(r'^extends\s+(\w+)', re.MULTILINE)
    GDSCRIPT_SIGNAL = re.compile(r'^signal\s+(\w+)(?:\(([^)]*)\))?', re.MULTILINE)
    GDSCRIPT_FUNC = re.compile(
        r'^(static\s+)?func\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*(\w+))?:',
        re.MULTILINE
    )
    GDSCRIPT_EXPORT = re.compile(
        r'^@export(?:_\w+)?(?:\(([^)]*)\))?\s*var\s+(\w+)\s*(?::\s*(\w+))?(?:\s*=\s*(.+))?$',
        re.MULTILINE
    )
    GDSCRIPT_ONREADY = re.compile(
        r'^@onready\s+var\s+(\w+)',
        re.MULTILINE
    )
    GDSCRIPT_CONST = re.compile(
        r'^const\s+(\w+)\s*(?::\s*\w+)?\s*=\s*(.+)$',
        re.MULTILINE
    )
    GDSCRIPT_DOCSTRING = re.compile(r'^##\s*(.+)$', re.MULTILINE)
    
    # Project.godot patterns
    PROJECT_SECTION = re.compile(r'^\[([^\]]+)\]$', re.MULTILINE)
    PROJECT_SETTING = re.compile(r'^([^=\s]+)\s*=\s*(.+?)(?:\n|$)', re.MULTILINE)
    AUTOLOAD = re.compile(r'"([^"]+)":\s*"(\*)?([^"]+)"')


# =============================================================================
# Parser Functions
# =============================================================================

def parse_tscn(file_path: str) -> ParsedScene:
    """
    Parse a Godot .tscn (Text Scene) file.
    
    Args:
        file_path: Path to the .tscn file
        
    Returns:
        ParsedScene with all extracted information
    """
    path = Path(file_path)
    content = path.read_text(encoding='utf-8')
    
    # Parse header
    header_match = GodotPatterns.SCENE_HEADER.search(content)
    if not header_match:
        logger.warning(f"Invalid scene file format: {file_path}")
        return ParsedScene(
            path=str(path),
            uid=None,
            format_version=0,
            ext_resources={},
            sub_resources={},
            nodes=[],
            connections=[]
        )
    
    load_steps = int(header_match.group(1)) if header_match.group(1) else 0
    format_version = int(header_match.group(2))
    uid = header_match.group(3)
    
    # Parse external resources
    ext_resources = {}
    for match in GodotPatterns.EXT_RESOURCE_V4.finditer(content):
        res_type, res_uid, res_path, res_id = match.groups()
        ext_resources[res_id] = ExtResource(
            id=res_id,
            path=res_path,
            type=res_type,
            uid=res_uid
        )
    
    # Fallback to older format
    if not ext_resources:
        for match in GodotPatterns.EXT_RESOURCE.finditer(content):
            groups = match.groups()
            res_type = groups[0] or groups[3]
            res_uid = groups[1] or groups[4]
            res_path = groups[2]
            res_id = groups[5]
            ext_resources[res_id] = ExtResource(
                id=res_id,
                path=res_path,
                type=res_type or "Unknown",
                uid=res_uid
            )
    
    # Parse sub-resources
    sub_resources = {}
    for match in GodotPatterns.SUB_RESOURCE.finditer(content):
        res_type, res_id = match.groups()
        sub_resources[res_id] = SubResource(id=res_id, type=res_type)
    
    # Parse nodes
    nodes = []
    root_node = None
    
    # Split content by sections to parse properties per node
    sections = re.split(r'(?=\[(?:node|connection|ext_resource|sub_resource|gd_scene))', content)
    
    for section in sections:
        node_match = GodotPatterns.NODE.match(section.strip())
        if node_match:
            name, node_type, parent, instance_id, groups_str = node_match.groups()
            
            # Parse properties within this section
            properties = {}
            lines = section.split('\n')[1:]  # Skip the [node] line
            for line in lines:
                prop_match = GodotPatterns.PROPERTY.match(line.strip())
                if prop_match:
                    prop_name, prop_value = prop_match.groups()
                    properties[prop_name] = prop_value
            
            # Extract script reference
            script = None
            if 'script' in properties:
                script_val = properties['script']
                script_match = re.search(r'ExtResource\("([^"]+)"\)', script_val)
                if script_match:
                    script_id = script_match.group(1)
                    if script_id in ext_resources:
                        script = ext_resources[script_id].path
            
            # Parse groups
            groups = []
            if groups_str:
                groups = [g.strip().strip('"') for g in groups_str.split(',')]
            
            node = SceneNode(
                name=name,
                type=node_type or "PackedScene",  # Instanced scenes might not have type
                parent=parent,
                properties=properties,
                instance=instance_id,
                script=script,
                groups=groups
            )
            nodes.append(node)
            
            if parent is None:
                root_node = node
    
    # Parse signal connections
    connections = []
    for match in GodotPatterns.CONNECTION.finditer(content):
        signal, from_node, to_node, method, flags, binds = match.groups()
        connections.append(SignalConnection(
            signal=signal,
            from_node=from_node,
            to_node=to_node,
            method=method,
            flags=int(flags) if flags else 0,
            binds=[]  # Parse binds if needed
        ))
    
    return ParsedScene(
        path=str(path),
        uid=uid,
        format_version=format_version,
        ext_resources=ext_resources,
        sub_resources=sub_resources,
        nodes=nodes,
        connections=connections,
        root_node=root_node
    )


def parse_tres(file_path: str) -> ParsedResource:
    """
    Parse a Godot .tres (Text Resource) file.
    
    Args:
        file_path: Path to the .tres file
        
    Returns:
        ParsedResource with all extracted information
    """
    path = Path(file_path)
    content = path.read_text(encoding='utf-8')
    
    # Parse header
    header_match = GodotPatterns.RESOURCE_HEADER.search(content)
    if not header_match:
        logger.warning(f"Invalid resource file format: {file_path}")
        return ParsedResource(
            path=str(path),
            type="Unknown",
            uid=None,
            properties={},
            ext_resources={},
            sub_resources={}
        )
    
    res_type = header_match.group(1)
    script_class = header_match.group(2)
    load_steps = header_match.group(3)
    format_version = int(header_match.group(4))
    uid = header_match.group(5)
    
    # Parse external resources (same as scenes)
    ext_resources = {}
    for match in GodotPatterns.EXT_RESOURCE_V4.finditer(content):
        res_type_ext, res_uid, res_path, res_id = match.groups()
        ext_resources[res_id] = ExtResource(
            id=res_id,
            path=res_path,
            type=res_type_ext,
            uid=res_uid
        )
    
    # Parse sub-resources
    sub_resources = {}
    for match in GodotPatterns.SUB_RESOURCE.finditer(content):
        sub_type, sub_id = match.groups()
        sub_resources[sub_id] = SubResource(id=sub_id, type=sub_type)
    
    # Parse main resource properties
    properties = {}
    # Find the [resource] section
    resource_section = re.search(r'\[resource\]([\s\S]*?)(?=\[|$)', content)
    if resource_section:
        for prop_match in GodotPatterns.PROPERTY.finditer(resource_section.group(1)):
            prop_name, prop_value = prop_match.groups()
            properties[prop_name] = prop_value
    
    return ParsedResource(
        path=str(path),
        type=res_type,
        uid=uid,
        properties=properties,
        ext_resources=ext_resources,
        sub_resources=sub_resources
    )


def parse_gdscript(file_path: str) -> GDScriptInfo:
    """
    Parse a GDScript (.gd) file for structure and metadata.
    
    Args:
        file_path: Path to the .gd file
        
    Returns:
        GDScriptInfo with parsed information
    """
    path = Path(file_path)
    content = path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    # Parse class name
    class_name = None
    class_match = GodotPatterns.GDSCRIPT_CLASS_NAME.search(content)
    if class_match:
        class_name = class_match.group(1)
    
    # Parse extends
    extends = "RefCounted"  # Default base class
    extends_match = GodotPatterns.GDSCRIPT_EXTENDS.search(content)
    if extends_match:
        extends = extends_match.group(1)
    
    # Parse top-level docstring (## comments at start)
    docstring = None
    docstring_lines = []
    for line in lines:
        if line.startswith('##'):
            docstring_lines.append(line[2:].strip())
        elif line.strip() and not line.startswith('#'):
            break
    if docstring_lines:
        docstring = '\n'.join(docstring_lines)
    
    # Parse signals
    signals = []
    for i, line in enumerate(lines):
        signal_match = GodotPatterns.GDSCRIPT_SIGNAL.match(line)
        if signal_match:
            sig_name = signal_match.group(1)
            params_str = signal_match.group(2) or ""
            params = []
            if params_str.strip():
                for param in params_str.split(','):
                    param = param.strip()
                    if ':' in param:
                        pname, ptype = param.split(':', 1)
                        params.append((pname.strip(), ptype.strip()))
                    else:
                        params.append((param, None))
            signals.append(SignalDefInfo(
                name=sig_name,
                parameters=params,
                line_number=i + 1
            ))
    
    # Parse functions
    functions = []
    for i, line in enumerate(lines):
        func_match = GodotPatterns.GDSCRIPT_FUNC.match(line)
        if func_match:
            is_static = bool(func_match.group(1))
            func_name = func_match.group(2)
            params_str = func_match.group(3)
            return_type = func_match.group(4)
            
            # Parse parameters
            params = []
            if params_str.strip():
                for param in params_str.split(','):
                    param = param.strip()
                    # Handle default values
                    if '=' in param:
                        param = param.split('=')[0].strip()
                    if ':' in param:
                        pname, ptype = param.split(':', 1)
                        params.append((pname.strip(), ptype.strip()))
                    else:
                        params.append((param, None))
            
            # Look for docstring (## comment before function)
            func_doc = None
            if i > 0:
                doc_lines = []
                for j in range(i - 1, -1, -1):
                    if lines[j].strip().startswith('##'):
                        doc_lines.insert(0, lines[j].strip()[2:].strip())
                    elif lines[j].strip() == '':
                        continue
                    else:
                        break
                if doc_lines:
                    func_doc = '\n'.join(doc_lines)
            
            functions.append(FunctionInfo(
                name=func_name,
                parameters=params,
                return_type=return_type,
                docstring=func_doc,
                line_number=i + 1,
                is_static=is_static,
                is_virtual=func_name.startswith('_')
            ))
    
    # Parse exports
    exports = []
    for i, line in enumerate(lines):
        export_match = GodotPatterns.GDSCRIPT_EXPORT.match(line)
        if export_match:
            hint, var_name, var_type, default_val = export_match.groups()
            exports.append(ExportInfo(
                name=var_name,
                type=var_type or "Variant",
                default_value=default_val,
                hint=hint,
                line_number=i + 1
            ))
    
    # Parse constants
    constants = {}
    for match in GodotPatterns.GDSCRIPT_CONST.finditer(content):
        const_name, const_value = match.groups()
        constants[const_name] = const_value.strip()
    
    # Parse @onready variables
    onready_vars = []
    for match in GodotPatterns.GDSCRIPT_ONREADY.finditer(content):
        onready_vars.append(match.group(1))
    
    return GDScriptInfo(
        path=str(path),
        class_name=class_name,
        extends=extends,
        functions=functions,
        signals=signals,
        exports=exports,
        docstring=docstring,
        constants=constants,
        onready_vars=onready_vars
    )


def parse_project_godot(file_path: str) -> ProjectConfig:
    """
    Parse a project.godot file.
    
    Args:
        file_path: Path to project.godot
        
    Returns:
        ProjectConfig with parsed settings
    """
    path = Path(file_path)
    content = path.read_text(encoding='utf-8')
    
    # Parse into sections
    sections: Dict[str, Dict[str, str]] = {}
    current_section = ""
    
    for line in content.split('\n'):
        line = line.strip()
        
        section_match = GodotPatterns.PROJECT_SECTION.match(line)
        if section_match:
            current_section = section_match.group(1)
            sections[current_section] = {}
            continue
        
        if '=' in line and current_section:
            key, value = line.split('=', 1)
            sections[current_section][key.strip()] = value.strip()
    
    # Extract common settings
    application = sections.get('application', {})
    project_name = application.get('config/name', 'Unknown Project')
    # Remove quotes
    project_name = project_name.strip('"')
    
    # Features
    features = []
    features_str = application.get('config/features', '')
    if features_str:
        features = re.findall(r'"([^"]+)"', features_str)
    
    # Autoloads
    autoloads = {}
    autoload_section = sections.get('autoload', {})
    for key, value in autoload_section.items():
        # Format: "name"="*res://path.gd" (* means singleton)
        match = re.match(r'\*?"?([^"]*)"?', value)
        if match:
            autoloads[key] = match.group(1) if match.group(1) else value
    
    # Input actions
    input_actions = {}
    input_section = sections.get('input', {})
    for key, value in input_section.items():
        if key.endswith('events'):
            continue
        action_name = key.replace('input/', '')
        input_actions[action_name] = []
    
    return ProjectConfig(
        project_name=project_name,
        config_version=int(sections.get('', {}).get('config_version', '5')),
        features=features,
        autoloads=autoloads,
        input_actions=input_actions,
        settings=sections
    )


# =============================================================================
# Utility Functions
# =============================================================================

def get_godot_file_type(file_path: str) -> Optional[str]:
    """Determine the type of Godot file."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    type_map = {
        '.tscn': 'scene',
        '.tres': 'resource',
        '.gd': 'script',
        '.gdshader': 'shader',
        '.gdshaderinc': 'shader_include',
        '.import': 'import_config',
    }
    
    if path.name == 'project.godot':
        return 'project_config'
    
    return type_map.get(suffix)


def extract_res_path(absolute_path: str, project_root: str) -> str:
    """Convert absolute path to res:// path."""
    try:
        rel = Path(absolute_path).relative_to(project_root)
        return f"res://{rel.as_posix()}"
    except ValueError:
        return absolute_path
