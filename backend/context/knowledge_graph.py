"""
Knowledge Graph Module for Godot Projects.

This module implements a NetworkX-based knowledge graph that represents
the structural relationships within a Godot project:
- File dependencies
- Scene hierarchies
- Script inheritance
- Signal connections
- Resource references

The graph enables structural queries like "What uses this class?" or
"What signals does this node emit?"
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple

try:
    import networkx as nx
except ImportError:
    nx = None
    
from .godot_parsers import (
    parse_tscn, parse_tres, parse_gdscript, parse_project_godot,
    get_godot_file_type, extract_res_path,
    ParsedScene, GDScriptInfo, ParsedResource, ProjectConfig,
    SignalConnection, SceneNode
)

logger = logging.getLogger(__name__)


# =============================================================================
# Node and Edge Types
# =============================================================================

class NodeType(Enum):
    """Types of nodes in the knowledge graph."""
    FILE = "file"
    SCENE = "scene"
    SCRIPT = "script"
    OBJECT = "object"  # Node within a scene
    FUNCTION = "function"
    SIGNAL_DEF = "signal_def"
    RESOURCE = "resource"
    AUTOLOAD = "autoload"


class EdgeType(Enum):
    """Types of edges in the knowledge graph."""
    DEFINES = "defines"           # File -> Script/Scene
    INHERITS = "inherits"         # Script -> Script/EngineClass
    INSTANTIATES = "instantiates" # Scene -> Scene
    CONNECTS_TO = "connects_to"   # Object -> Function (signal connection)
    HAS_RESOURCE = "has_resource" # Scene -> File (external resource)
    CONTAINS = "contains"         # Scene -> Object (node hierarchy)
    HAS_METHOD = "has_method"     # Script -> Function
    EMITS = "emits"               # Script/Object -> SignalDef
    REFERENCES = "references"     # Generic reference
    AUTOLOAD = "autoload"         # Project -> Autoload


# =============================================================================
# Graph Node Data Classes
# =============================================================================

@dataclass
class GraphNode:
    """Base class for graph nodes."""
    id: str
    type: NodeType
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class FileGraphNode(GraphNode):
    """Represents a file in the project."""
    path: str = ""
    file_type: str = ""  # scene, script, resource
    last_modified: float = 0.0


@dataclass
class SceneGraphNode(GraphNode):
    """Represents a scene."""
    path: str = ""
    root_type: str = ""
    node_count: int = 0


@dataclass
class ScriptGraphNode(GraphNode):
    """Represents a GDScript file."""
    path: str = ""
    class_name: Optional[str] = None
    extends: str = "RefCounted"


@dataclass
class ObjectGraphNode(GraphNode):
    """Represents a node within a scene."""
    scene_path: str = ""
    node_path: str = ""
    node_type: str = ""
    has_script: bool = False


@dataclass
class FunctionGraphNode(GraphNode):
    """Represents a function/method."""
    script_path: str = ""
    signature: str = ""
    docstring: Optional[str] = None
    line_number: int = 0


@dataclass
class SignalDefGraphNode(GraphNode):
    """Represents a signal definition."""
    script_path: str = ""
    parameters: List[Tuple[str, Optional[str]]] = field(default_factory=list)


# =============================================================================
# Knowledge Graph Implementation
# =============================================================================

class GodotKnowledgeGraph:
    """
    NetworkX-based knowledge graph for Godot projects.
    
    The graph represents structural relationships between files, scenes,
    scripts, and nodes enabling queries like:
    - What scenes use this script?
    - What signals does this node emit?
    - What is the class hierarchy of this script?
    """
    
    def __init__(self):
        if nx is None:
            raise ImportError("NetworkX is required: pip install networkx")
        
        self.graph = nx.DiGraph()
        self.project_root: Optional[str] = None
        self.project_config: Optional[ProjectConfig] = None
        
        # Index for fast lookups
        self._path_to_node: Dict[str, str] = {}
        self._class_to_script: Dict[str, str] = {}
        self._signal_to_nodes: Dict[str, List[str]] = {}
    
    def build_from_project(self, project_path: str) -> None:
        """
        Build the knowledge graph from a Godot project directory.
        
        Args:
            project_path: Path to the Godot project root (containing project.godot)
        """
        self.project_root = project_path
        self.graph.clear()
        self._path_to_node.clear()
        self._class_to_script.clear()
        self._signal_to_nodes.clear()
        
        logger.info(f"Building knowledge graph for: {project_path}")
        
        # Parse project.godot first
        project_file = Path(project_path) / "project.godot"
        if project_file.exists():
            self.project_config = parse_project_godot(str(project_file))
            self._add_project_node()
        
        # Walk the project directory
        file_count = 0
        for root, dirs, files in os.walk(project_path):
            # Skip hidden directories and common excludes
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      {'__pycache__', 'addons', '.godot', '.import'}]
            
            for file in files:
                file_path = os.path.join(root, file)
                file_type = get_godot_file_type(file_path)
                
                if file_type == 'scene':
                    self._process_scene(file_path)
                    file_count += 1
                elif file_type == 'script':
                    self._process_script(file_path)
                    file_count += 1
                elif file_type == 'resource':
                    self._process_resource(file_path)
                    file_count += 1
        
        # Build inheritance relationships after all scripts are processed
        self._build_inheritance_edges()
        
        logger.info(f"Knowledge graph built: {self.graph.number_of_nodes()} nodes, "
                   f"{self.graph.number_of_edges()} edges from {file_count} files")
    
    def _add_project_node(self) -> None:
        """Add the project configuration node."""
        if not self.project_config:
            return
        
        project_id = "project:root"
        self.graph.add_node(
            project_id,
            type=NodeType.FILE.value,
            name=self.project_config.project_name,
            file_type="project_config"
        )
        
        # Add autoload nodes
        for name, path in self.project_config.autoloads.items():
            autoload_id = f"autoload:{name}"
            self.graph.add_node(
                autoload_id,
                type=NodeType.AUTOLOAD.value,
                name=name,
                path=path
            )
            self.graph.add_edge(
                project_id,
                autoload_id,
                type=EdgeType.AUTOLOAD.value
            )
    
    def _process_scene(self, file_path: str) -> None:
        """Process a scene file and add to graph."""
        try:
            scene = parse_tscn(file_path)
            res_path = extract_res_path(file_path, self.project_root)
            
            # Add scene node
            scene_id = f"scene:{res_path}"
            root_type = scene.root_node.type if scene.root_node else "Node"
            
            self.graph.add_node(
                scene_id,
                type=NodeType.SCENE.value,
                name=Path(file_path).stem,
                path=res_path,
                root_type=root_type,
                node_count=len(scene.nodes)
            )
            self._path_to_node[res_path] = scene_id
            
            # Add file node
            file_id = f"file:{res_path}"
            self.graph.add_node(
                file_id,
                type=NodeType.FILE.value,
                name=Path(file_path).name,
                path=res_path,
                file_type="scene"
            )
            self._path_to_node[res_path] = file_id
            
            # File defines scene
            self.graph.add_edge(file_id, scene_id, type=EdgeType.DEFINES.value)
            
            # Process external resources
            for res_id, ext_res in scene.ext_resources.items():
                ext_path = ext_res.path
                ext_file_id = f"file:{ext_path}"
                
                if ext_file_id not in self.graph:
                    self.graph.add_node(
                        ext_file_id,
                        type=NodeType.FILE.value,
                        name=Path(ext_path).name if ext_path.startswith("res://") else ext_path,
                        path=ext_path,
                        file_type=ext_res.type.lower()
                    )
                
                self.graph.add_edge(
                    scene_id,
                    ext_file_id,
                    type=EdgeType.HAS_RESOURCE.value,
                    resource_type=ext_res.type
                )
            
            # Process nodes within the scene
            for node in scene.nodes:
                self._add_scene_node(scene_id, res_path, node)
            
            # Process signal connections
            for conn in scene.connections:
                self._add_signal_connection(scene_id, res_path, conn)
                
        except Exception as e:
            logger.warning(f"Failed to process scene {file_path}: {e}")
    
    def _add_scene_node(self, scene_id: str, scene_path: str, node: SceneNode) -> None:
        """Add a scene node (object) to the graph."""
        # Build full node path
        if node.parent is None:
            node_path = node.name
        elif node.parent == ".":
            node_path = node.name
        else:
            node_path = f"{node.parent}/{node.name}"
        
        object_id = f"object:{scene_path}:{node_path}"
        
        self.graph.add_node(
            object_id,
            type=NodeType.OBJECT.value,
            name=node.name,
            scene_path=scene_path,
            node_path=node_path,
            node_type=node.type,
            has_script=node.script is not None,
            groups=node.groups
        )
        
        # Scene contains object
        self.graph.add_edge(scene_id, object_id, type=EdgeType.CONTAINS.value)
        
        # If node has script, link to it
        if node.script:
            script_file_id = f"file:{node.script}"
            if script_file_id in self.graph:
                self.graph.add_edge(
                    object_id,
                    script_file_id,
                    type=EdgeType.HAS_RESOURCE.value,
                    resource_type="Script"
                )
        
        # If node is an instance, link to instanced scene
        if node.instance:
            # Resolve ExtResource ID to path
            pass  # Would need scene ext_resources here
    
    def _add_signal_connection(self, scene_id: str, scene_path: str, 
                               conn: SignalConnection) -> None:
        """Add a signal connection to the graph."""
        from_object_id = f"object:{scene_path}:{conn.from_node}"
        to_object_id = f"object:{scene_path}:{conn.to_node}"
        
        # Create a synthetic function node for the method
        method_id = f"method:{scene_path}:{conn.to_node}:{conn.method}"
        
        if method_id not in self.graph:
            self.graph.add_node(
                method_id,
                type=NodeType.FUNCTION.value,
                name=conn.method,
                scene_path=scene_path,
                connected_from_signal=conn.signal
            )
        
        # Object connects to function via signal
        self.graph.add_edge(
            from_object_id,
            method_id,
            type=EdgeType.CONNECTS_TO.value,
            signal=conn.signal,
            flags=conn.flags
        )
        
        # Track signal sources
        if conn.signal not in self._signal_to_nodes:
            self._signal_to_nodes[conn.signal] = []
        self._signal_to_nodes[conn.signal].append(from_object_id)
    
    def _process_script(self, file_path: str) -> None:
        """Process a GDScript file and add to graph."""
        try:
            script = parse_gdscript(file_path)
            res_path = extract_res_path(file_path, self.project_root)
            
            # Add file node
            file_id = f"file:{res_path}"
            self.graph.add_node(
                file_id,
                type=NodeType.FILE.value,
                name=Path(file_path).name,
                path=res_path,
                file_type="script"
            )
            self._path_to_node[res_path] = file_id
            
            # Add script node
            script_id = f"script:{res_path}"
            self.graph.add_node(
                script_id,
                type=NodeType.SCRIPT.value,
                name=script.class_name or Path(file_path).stem,
                path=res_path,
                class_name=script.class_name,
                extends=script.extends,
                docstring=script.docstring
            )
            
            # File defines script
            self.graph.add_edge(file_id, script_id, type=EdgeType.DEFINES.value)
            
            # Track class name for inheritance
            if script.class_name:
                self._class_to_script[script.class_name] = script_id
            
            # Add function nodes
            for func in script.functions:
                func_id = f"function:{res_path}:{func.name}"
                
                # Build signature string
                params = ", ".join(
                    f"{p[0]}: {p[1]}" if p[1] else p[0] 
                    for p in func.parameters
                )
                ret = f" -> {func.return_type}" if func.return_type else ""
                signature = f"func {func.name}({params}){ret}"
                
                self.graph.add_node(
                    func_id,
                    type=NodeType.FUNCTION.value,
                    name=func.name,
                    script_path=res_path,
                    signature=signature,
                    docstring=func.docstring,
                    line_number=func.line_number,
                    is_static=func.is_static,
                    is_virtual=func.is_virtual
                )
                
                # Script has method
                self.graph.add_edge(script_id, func_id, type=EdgeType.HAS_METHOD.value)
            
            # Add signal definitions
            for sig in script.signals:
                signal_id = f"signal:{res_path}:{sig.name}"
                
                self.graph.add_node(
                    signal_id,
                    type=NodeType.SIGNAL_DEF.value,
                    name=sig.name,
                    script_path=res_path,
                    parameters=sig.parameters,
                    line_number=sig.line_number
                )
                
                # Script emits signal
                self.graph.add_edge(script_id, signal_id, type=EdgeType.EMITS.value)
                
        except Exception as e:
            logger.warning(f"Failed to process script {file_path}: {e}")
    
    def _process_resource(self, file_path: str) -> None:
        """Process a resource file and add to graph."""
        try:
            resource = parse_tres(file_path)
            res_path = extract_res_path(file_path, self.project_root)
            
            # Add file node
            file_id = f"file:{res_path}"
            self.graph.add_node(
                file_id,
                type=NodeType.FILE.value,
                name=Path(file_path).name,
                path=res_path,
                file_type="resource",
                resource_type=resource.type
            )
            self._path_to_node[res_path] = file_id
            
            # Add resource node
            resource_id = f"resource:{res_path}"
            self.graph.add_node(
                resource_id,
                type=NodeType.RESOURCE.value,
                name=Path(file_path).stem,
                path=res_path,
                resource_type=resource.type
            )
            
            # File defines resource
            self.graph.add_edge(file_id, resource_id, type=EdgeType.DEFINES.value)
            
            # Process external resources
            for res_id, ext_res in resource.ext_resources.items():
                ext_path = ext_res.path
                ext_file_id = f"file:{ext_path}"
                
                if ext_file_id not in self.graph:
                    self.graph.add_node(
                        ext_file_id,
                        type=NodeType.FILE.value,
                        name=Path(ext_path).name if ext_path.startswith("res://") else ext_path,
                        path=ext_path,
                        file_type=ext_res.type.lower()
                    )
                
                self.graph.add_edge(
                    resource_id,
                    ext_file_id,
                    type=EdgeType.HAS_RESOURCE.value,
                    resource_type=ext_res.type
                )
                
        except Exception as e:
            logger.warning(f"Failed to process resource {file_path}: {e}")
    
    def _build_inheritance_edges(self) -> None:
        """Build inheritance edges between scripts."""
        # Collect script nodes first to avoid modifying during iteration
        scripts_to_process = []
        for node_id, data in list(self.graph.nodes(data=True)):
            if data.get('type') == NodeType.SCRIPT.value:
                extends = data.get('extends')
                if extends:
                    scripts_to_process.append((node_id, extends))
        
        # Now process inheritance
        for node_id, extends in scripts_to_process:
            # Check if extends is a project class
            if extends in self._class_to_script:
                parent_id = self._class_to_script[extends]
                self.graph.add_edge(
                    node_id,
                    parent_id,
                    type=EdgeType.INHERITS.value
                )
            else:
                # It's an engine class - create synthetic node
                engine_class_id = f"engine_class:{extends}"
                if engine_class_id not in self.graph:
                    self.graph.add_node(
                        engine_class_id,
                        type=NodeType.SCRIPT.value,
                        name=extends,
                        is_engine_class=True
                    )
                self.graph.add_edge(
                    node_id,
                    engine_class_id,
                    type=EdgeType.INHERITS.value
                )
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def get_scene_tree(self, scene_path: str) -> Dict[str, Any]:
        """
        Get the node hierarchy for a scene.
        
        Args:
            scene_path: res:// path to the scene
            
        Returns:
            Hierarchical dict of scene nodes
        """
        scene_id = f"scene:{scene_path}"
        if scene_id not in self.graph:
            return {}
        
        # Get all objects in the scene
        objects = []
        for succ in self.graph.successors(scene_id):
            data = self.graph.nodes[succ]
            if data.get('type') == NodeType.OBJECT.value:
                objects.append({
                    'name': data.get('name'),
                    'type': data.get('node_type'),
                    'path': data.get('node_path'),
                    'has_script': data.get('has_script', False),
                    'groups': data.get('groups', [])
                })
        
        return {
            'scene': scene_path,
            'root_type': self.graph.nodes[scene_id].get('root_type'),
            'node_count': self.graph.nodes[scene_id].get('node_count'),
            'nodes': objects
        }
    
    def get_signal_connections(self, node_or_signal: str) -> List[Dict[str, Any]]:
        """
        Get all signal connections for a node or signal.
        
        Args:
            node_or_signal: Node path or signal name
            
        Returns:
            List of connection dictionaries
        """
        connections = []
        
        for edge in self.graph.edges(data=True):
            source, target, data = edge
            if data.get('type') != EdgeType.CONNECTS_TO.value:
                continue
            
            signal_name = data.get('signal', '')
            if node_or_signal in source or node_or_signal == signal_name:
                target_data = self.graph.nodes.get(target, {})
                connections.append({
                    'from': source,
                    'signal': signal_name,
                    'to': target,
                    'method': target_data.get('name', ''),
                    'flags': data.get('flags', 0)
                })
        
        return connections
    
    def get_class_hierarchy(self, script_path: str) -> List[str]:
        """
        Get the inheritance chain for a script.
        
        Args:
            script_path: res:// path to the script
            
        Returns:
            List of class names from child to parent
        """
        script_id = f"script:{script_path}"
        if script_id not in self.graph:
            return []
        
        hierarchy = []
        current = script_id
        visited = set()
        
        while current and current not in visited:
            visited.add(current)
            data = self.graph.nodes.get(current, {})
            
            name = data.get('class_name') or data.get('name', '')
            if name:
                hierarchy.append(name)
            
            # Find parent (INHERITS edge)
            parent = None
            for succ in self.graph.successors(current):
                edge_data = self.graph.edges[current, succ]
                if edge_data.get('type') == EdgeType.INHERITS.value:
                    parent = succ
                    break
            
            current = parent
        
        return hierarchy
    
    def find_usages(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        Find all places where an entity (class, function, signal) is used.
        
        Args:
            entity_name: Name of the entity to search for
            
        Returns:
            List of usage dictionaries
        """
        usages = []
        
        for node_id, data in self.graph.nodes(data=True):
            name = data.get('name', '')
            class_name = data.get('class_name', '')
            
            if entity_name in (name, class_name):
                # Find what references this
                for pred in self.graph.predecessors(node_id):
                    pred_data = self.graph.nodes[pred]
                    usages.append({
                        'used_by': pred,
                        'type': pred_data.get('type'),
                        'path': pred_data.get('path') or pred_data.get('scene_path')
                    })
        
        return usages
    
    def get_dependencies(self, file_path: str) -> List[str]:
        """
        Get all files that a file depends on.
        
        Args:
            file_path: res:// path to the file
            
        Returns:
            List of dependency paths
        """
        file_id = f"file:{file_path}"
        if file_id not in self.graph:
            # Try scene or script
            for prefix in ['scene:', 'script:', 'resource:']:
                alt_id = f"{prefix}{file_path}"
                if alt_id in self.graph:
                    file_id = alt_id
                    break
        
        if file_id not in self.graph:
            return []
        
        deps = []
        for succ in nx.descendants(self.graph, file_id):
            data = self.graph.nodes[succ]
            if data.get('type') == NodeType.FILE.value:
                path = data.get('path')
                if path:
                    deps.append(path)
        
        return deps
    
    def get_dependents(self, file_path: str) -> List[str]:
        """
        Get all files that depend on this file.
        
        Args:
            file_path: res:// path to the file
            
        Returns:
            List of dependent file paths
        """
        file_id = f"file:{file_path}"
        if file_id not in self.graph:
            return []
        
        dependents = []
        for pred in nx.ancestors(self.graph, file_id):
            data = self.graph.nodes[pred]
            if data.get('type') == NodeType.FILE.value:
                path = data.get('path')
                if path:
                    dependents.append(path)
        
        return dependents
    
    def get_project_summary(self) -> Dict[str, Any]:
        """Get a high-level summary of the project structure."""
        node_counts = {nt.value: 0 for nt in NodeType}
        
        for _, data in self.graph.nodes(data=True):
            node_type = data.get('type')
            if node_type in node_counts:
                node_counts[node_type] += 1
        
        # Get autoloads
        autoloads = []
        if self.project_config:
            autoloads = list(self.project_config.autoloads.keys())
        
        return {
            'project_name': self.project_config.project_name if self.project_config else "Unknown",
            'total_nodes': self.graph.number_of_nodes(),
            'total_edges': self.graph.number_of_edges(),
            'scenes': node_counts[NodeType.SCENE.value],
            'scripts': node_counts[NodeType.SCRIPT.value],
            'resources': node_counts[NodeType.RESOURCE.value],
            'functions': node_counts[NodeType.FUNCTION.value],
            'signal_definitions': node_counts[NodeType.SIGNAL_DEF.value],
            'autoloads': autoloads
        }
    
    def to_text_summary(self) -> str:
        """Generate a text summary suitable for LLM context injection."""
        summary = self.get_project_summary()
        lines = [
            f"# Project: {summary['project_name']}",
            f"",
            f"## Statistics",
            f"- Scenes: {summary['scenes']}",
            f"- Scripts: {summary['scripts']}",
            f"- Resources: {summary['resources']}",
            f"- Functions: {summary['functions']}",
            f"- Signal Definitions: {summary['signal_definitions']}",
        ]
        
        if summary['autoloads']:
            lines.append("")
            lines.append("## Autoloads (Singletons)")
            for al in summary['autoloads']:
                lines.append(f"- {al}")
        
        # List key scenes
        lines.append("")
        lines.append("## Scenes")
        for node_id, data in self.graph.nodes(data=True):
            if data.get('type') == NodeType.SCENE.value:
                path = data.get('path', '')
                root = data.get('root_type', 'Node')
                nodes = data.get('node_count', 0)
                lines.append(f"- {path} ({root}, {nodes} nodes)")
        
        # List scripts with class names
        lines.append("")
        lines.append("## Scripts")
        for node_id, data in self.graph.nodes(data=True):
            if data.get('type') == NodeType.SCRIPT.value and not data.get('is_engine_class'):
                path = data.get('path', '')
                class_name = data.get('class_name')
                extends = data.get('extends', '')
                if class_name:
                    lines.append(f"- {class_name} ({path}) extends {extends}")
                else:
                    lines.append(f"- {path} extends {extends}")
        
        return '\n'.join(lines)
