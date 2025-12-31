"""Godot Knowledge Base Module.

Provides knowledge retrieval for Godot documentation and LSP integration.

Exports:
    - GodotDocsKnowledge: Original knowledge base for Godot class reference
    - EnhancedGodotKnowledge: Extended knowledge with GDScript reference and tutorials
    - ProjectKnowledge: Project-specific knowledge with hash-based invalidation
    - KnowledgeTools integration: create_godot_knowledge_tools, get_godot_knowledge_tools
    - GDScriptLSPClient: Language Server Protocol client for code intelligence
"""

from .godot_knowledge import GodotDocsKnowledge, get_godot_knowledge
from .lsp_client import GDScriptLSPClient, get_lsp_client
from .enhanced_knowledge import EnhancedGodotKnowledge, get_enhanced_godot_knowledge
from .knowledge_tools import create_godot_knowledge_tools, get_godot_knowledge_tools
from .project_knowledge import ProjectKnowledge, get_project_knowledge, clear_project_knowledge

__all__ = [
    # Original knowledge base
    "GodotDocsKnowledge",
    "get_godot_knowledge",
    # Enhanced knowledge base
    "EnhancedGodotKnowledge",
    "get_enhanced_godot_knowledge",
    # Project-specific knowledge
    "ProjectKnowledge",
    "get_project_knowledge",
    "clear_project_knowledge",
    # KnowledgeTools integration
    "create_godot_knowledge_tools",
    "get_godot_knowledge_tools",
    # LSP client
    "GDScriptLSPClient",
    "get_lsp_client",
]
