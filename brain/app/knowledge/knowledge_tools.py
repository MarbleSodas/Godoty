"""Agno KnowledgeTools wrapper for Godoty.

Provides KnowledgeTools integration with the enhanced Godot knowledge base.
Enables agents to search, think, and analyze Godot documentation with
reasoning capabilities.

Based on Agno's KnowledgeTools pattern for RAG workflows.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agno.tools.knowledge import KnowledgeTools

from .enhanced_knowledge import EnhancedGodotKnowledge, get_enhanced_godot_knowledge

if TYPE_CHECKING:
    from agno.knowledge.knowledge import Knowledge

logger = logging.getLogger(__name__)


def create_godot_knowledge_tools(
    version: str = "4.5",
    enable_think: bool = True,
    enable_search: bool = True,
    enable_analyze: bool = True,
    add_instructions: bool = True,
    add_few_shot: bool = True,
) -> KnowledgeTools:
    """Create KnowledgeTools configured for Godot documentation search.
    
    This wraps the EnhancedGodotKnowledge with Agno's KnowledgeTools,
    providing agents with think(), search(), and analyze() tools for
    intelligent documentation retrieval.
    
    Args:
        version: Godot version (e.g., "4.3", "4.2")
        enable_think: Enable the think tool for reasoning about search strategy
        enable_search: Enable the search tool for querying the knowledge base
        enable_analyze: Enable the analyze tool for evaluating result relevance
        add_instructions: Add default instructions for using the tools
        add_few_shot: Add few-shot examples for better tool usage
        
    Returns:
        KnowledgeTools instance configured for Godot docs
        
    Example:
        >>> tools = create_godot_knowledge_tools(version="4.3")
        >>> agent = Agent(tools=[tools], ...)
    """
    # Get cached EnhancedGodotKnowledge instance
    enhanced_knowledge = get_enhanced_godot_knowledge(version=version)
    
    # Extract the underlying Agno Knowledge object
    knowledge = enhanced_knowledge.knowledge
    
    # Create KnowledgeTools with Godot-specific configuration
    godot_tools = KnowledgeTools(
        knowledge=knowledge,
        enable_think=enable_think,
        enable_search=enable_search,
        enable_analyze=enable_analyze,
        add_instructions=add_instructions,
        add_few_shot=add_few_shot,
        # Custom few-shot examples for Godot-specific queries
        few_shot_examples=_get_godot_few_shot_examples() if add_few_shot else None,
    )
    
    logger.info(f"Created KnowledgeTools for Godot {version}")
    return godot_tools


def _get_godot_few_shot_examples() -> str:
    """Return few-shot examples tailored for Godot documentation queries.
    
    These examples help the agent understand how to effectively use
    the knowledge tools for GDScript and Godot-related questions.
    """
    return """
Example 1: Signal Usage
User: "How do I emit a signal with parameters in GDScript?"
Think: "I need to search for signal emission syntax. Key terms: 'emit', 'signal', 'parameters', 'GDScript'"
Search: "emit signal parameters GDScript"
Analyze: "The search returned documentation about Signal.emit() method. It shows the syntax signal_name.emit(arg1, arg2). This directly answers the user's question about emitting with parameters."

Example 2: Node Inheritance
User: "What's the difference between CharacterBody2D and RigidBody2D?"
Think: "I should search for both classes to compare their purposes. Key terms: 'CharacterBody2D', 'RigidBody2D', 'physics', 'movement'"
Search: "CharacterBody2D RigidBody2D"
Analyze: "Found class references for both. CharacterBody2D is for kinematic character movement with move_and_slide(). RigidBody2D uses physics simulation. The key difference is control vs physics-driven movement."

Example 3: Export Annotations
User: "How do I expose a variable to the inspector?"
Think: "The user wants to know about @export annotations. Key terms: '@export', 'inspector', 'variable', 'property'"
Search: "@export annotation inspector"
Analyze: "Found GDScript exports documentation. Shows @export, @export_range, @export_enum and other variants. This covers all ways to expose variables to the editor inspector."
"""


# Singleton cache for KnowledgeTools instances
_knowledge_tools_cache: dict[str, KnowledgeTools] = {}


def get_godot_knowledge_tools(version: str = "4.5") -> KnowledgeTools:
    """Get a cached KnowledgeTools instance for the specified Godot version.
    
    Uses singleton pattern to avoid recreating tools for the same version.
    
    Args:
        version: Godot version (e.g., "4.3", "4.2")
        
    Returns:
        Cached KnowledgeTools instance
    """
    if version not in _knowledge_tools_cache:
        _knowledge_tools_cache[version] = create_godot_knowledge_tools(version=version)
    
    return _knowledge_tools_cache[version]


__all__ = [
    "create_godot_knowledge_tools",
    "get_godot_knowledge_tools",
]
