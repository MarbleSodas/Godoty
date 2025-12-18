"""Godot Knowledge Base Module.

Provides knowledge retrieval for Godot documentation and LSP integration.

Exports:
    - GodotDocsKnowledge: Original knowledge base for Godot class reference
    - EnhancedGodotKnowledge: Extended knowledge with GDScript reference and tutorials
    - KnowledgeTools integration: create_godot_knowledge_tools, get_godot_knowledge_tools
    - GDScriptLSPClient: Language Server Protocol client for code intelligence
"""

from .godot_knowledge import GodotDocsKnowledge, get_godot_knowledge
from .lsp_client import GDScriptLSPClient, get_lsp_client
from .enhanced_knowledge import EnhancedGodotKnowledge, get_enhanced_godot_knowledge
from .knowledge_tools import create_godot_knowledge_tools, get_godot_knowledge_tools

__all__ = [
    # Original knowledge base
    "GodotDocsKnowledge",
    "get_godot_knowledge",
    # Enhanced knowledge base
    "EnhancedGodotKnowledge",
    "get_enhanced_godot_knowledge",
    # KnowledgeTools integration
    "create_godot_knowledge_tools",
    "get_godot_knowledge_tools",
    # LSP client
    "GDScriptLSPClient",
    "get_lsp_client",
]
