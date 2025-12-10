"""
Godot Context Engine Package.

This package provides context-aware functionality for the Godoty agent:
- Godot file parsers (.tscn, .tres, .gd, project.godot)
- Knowledge graph for structural queries
- Vector store for semantic search
- Hybrid retrieval engine
"""

from .engine import (
    GodotContextEngine, ContextBundle, QueryIntent,
    IndexStatus, IndexProgress, IndexMetadata
)
from .godot_parsers import (
    parse_tscn, parse_tres, parse_gdscript, parse_project_godot,
    ParsedScene, GDScriptInfo, ParsedResource, ProjectConfig,
    SceneNode, SignalConnection, ExtResource
)
from .knowledge_graph import GodotKnowledgeGraph, NodeType, EdgeType
from .vector_store import GodotVectorStore, SearchResult, CodeChunk

__all__ = [
    # Main engine
    "GodotContextEngine",
    "ContextBundle",
    "QueryIntent",
    # Index status
    "IndexStatus",
    "IndexProgress", 
    "IndexMetadata",
    # Parsers
    "parse_tscn",
    "parse_tres",
    "parse_gdscript",
    "parse_project_godot",
    "ParsedScene",
    "GDScriptInfo",
    "ParsedResource",
    "ProjectConfig",
    "SceneNode",
    "SignalConnection",
    "ExtResource",
    # Knowledge graph
    "GodotKnowledgeGraph",
    "NodeType",
    "EdgeType",
    # Vector store
    "GodotVectorStore",
    "SearchResult",
    "CodeChunk",
]
