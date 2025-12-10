"""
Context-Aware Tools for Godoty Agent.

This module provides tools that leverage the Context Engine to give 
the agent deep understanding of Godot project structure and semantics.
"""

import logging
from typing import List, Optional

from strands import tool

logger = logging.getLogger(__name__)

# Global context engine reference (set by agent initialization)
_context_engine = None


def set_context_engine(engine):
    """Set the global context engine instance."""
    global _context_engine
    _context_engine = engine


def get_context_engine():
    """Get the global context engine instance."""
    return _context_engine


# =============================================================================
# Context Retrieval Tools
# =============================================================================

@tool
def retrieve_context(
    query: str,
    filters: Optional[List[str]] = None
) -> str:
    """
    Retrieves relevant code, scene structures, and documentation for a query.
    
    This tool uses hybrid retrieval combining:
    - Knowledge graph for structural queries (dependencies, signals, inheritance)
    - Vector search for semantic queries (code patterns, implementations)
    
    Use this tool when you need to understand how something works in the project
    or find relevant code examples.
    
    Args:
        query: The search query describing what you're looking for
        filters: Optional list of sources to search: ["code", "scenes", "docs"]
                 If not provided, searches all sources.
    
    Returns:
        Formatted context including code snippets, scene structures,
        signal connections, and relevant documentation.
    
    Examples:
        - retrieve_context("player movement implementation")
        - retrieve_context("how is damage calculated")
        - retrieve_context("enemy AI behavior", filters=["code"])
    """
    engine = get_context_engine()
    
    if engine is None:
        return "Error: Context engine not initialized. The project may not be indexed yet."
    
    try:
        bundle = engine.retrieve_context(query, intent="auto", limit=8)
        
        # Format the results
        result = bundle.to_prompt_context(token_budget=3000)
        
        if not result or result.strip() == "":
            return f"No relevant context found for query: '{query}'. Try a different search term."
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving context: {e}")
        return f"Error retrieving context: {str(e)}"


@tool
def get_signal_flow(node_or_signal: str) -> str:
    """
    Traces signal connections for a specific node or signal name.
    
    Use this tool to understand the event flow in a Godot project -
    which signals are emitted by a node and what methods they connect to.
    
    Args:
        node_or_signal: Either a node path (e.g., "Player", "UI/HealthBar")
                        or a signal name (e.g., "body_entered", "health_changed")
    
    Returns:
        A formatted list of signal connections showing:
        - Source node and signal
        - Target method
        - Connection flags
    
    Examples:
        - get_signal_flow("Player") - Get all signals from Player node
        - get_signal_flow("health_changed") - Find all health_changed signal usages
        - get_signal_flow("Area2D") - Signals from Area2D nodes
    """
    engine = get_context_engine()
    
    if engine is None:
        return "Error: Context engine not initialized."
    
    try:
        connections = engine.get_signal_connections(node_or_signal)
        
        if not connections:
            return f"No signal connections found for '{node_or_signal}'.\n\nTips:\n- Try the exact node name without path\n- Try the signal name (e.g., 'body_entered')\n- The project may need to be re-indexed"
        
        # Format results
        lines = [f"## Signal Connections for '{node_or_signal}'", ""]
        
        for conn in connections:
            from_node = conn.get('from', 'unknown')
            signal = conn.get('signal', 'unknown')
            method = conn.get('method', 'unknown')
            lines.append(f"- **{from_node}** → `{signal}` → **{method}()**")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error getting signal flow: {e}")
        return f"Error getting signal flow: {str(e)}"


@tool  
def get_class_hierarchy(class_name: str) -> str:
    """
    Gets the inheritance chain for a GDScript class.
    
    Use this to understand what a class inherits from and its relationship
    to both project classes and Godot engine classes.
    
    Args:
        class_name: The name of the class (from class_name declaration)
                    or script file name
    
    Returns:
        The inheritance chain from the class to its root,
        e.g., "Player → CharacterBody2D → PhysicsBody2D → Node2D → Node"
    
    Examples:
        - get_class_hierarchy("Player")
        - get_class_hierarchy("Enemy")
        - get_class_hierarchy("HealthComponent")
    """
    engine = get_context_engine()
    
    if engine is None:
        return "Error: Context engine not initialized."
    
    try:
        hierarchy = engine.get_class_hierarchy(class_name)
        
        if not hierarchy:
            # Try finding it as a script name
            for node_id, data in engine.graph.graph.nodes(data=True):
                name = data.get('name', '')
                if class_name.lower() in name.lower() and data.get('type') == 'script':
                    path = data.get('path', '')
                    hierarchy = engine.graph.get_class_hierarchy(path)
                    if hierarchy:
                        break
        
        if not hierarchy:
            return f"Class '{class_name}' not found.\n\nTips:\n- Use the exact class_name from the script\n- Try the script filename without .gd extension\n- Ensure the project is indexed"
        
        # Format as inheritance chain
        return f"## Class Hierarchy\n\n**{' → '.join(hierarchy)}**"
        
    except Exception as e:
        logger.error(f"Error getting class hierarchy: {e}")
        return f"Error getting class hierarchy: {str(e)}"


@tool
def find_usages(entity_name: str) -> str:
    """
    Finds all locations where a class, function, or signal is used.
    
    Use this to understand the impact of changes - what parts of the
    codebase depend on or use a particular entity.
    
    Args:
        entity_name: Name of the class, function, or signal to search for
    
    Returns:
        A list of files and locations that reference the entity.
    
    Examples:
        - find_usages("Player") - Find all uses of Player class
        - find_usages("take_damage") - Find all calls to take_damage
        - find_usages("health_changed") - Find signal connections
    """
    engine = get_context_engine()
    
    if engine is None:
        return "Error: Context engine not initialized."
    
    try:
        usages = engine.find_usages(entity_name)
        
        if not usages:
            return f"No usages found for '{entity_name}'.\n\nTips:\n- Check the exact spelling\n- Try partial name matches\n- The entity may not be referenced elsewhere"
        
        # Format results
        lines = [f"## Usages of '{entity_name}'", ""]
        
        # Group by path
        by_path = {}
        for usage in usages:
            path = usage.get('path', 'unknown')
            if path not in by_path:
                by_path[path] = []
            by_path[path].append(usage)
        
        for path, path_usages in by_path.items():
            lines.append(f"### {path}")
            for usage in path_usages:
                used_by = usage.get('used_by', 'unknown')
                usage_type = usage.get('type', 'unknown')
                lines.append(f"  - Used by: {used_by} ({usage_type})")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error finding usages: {e}")
        return f"Error finding usages: {str(e)}"


@tool
def get_file_context(file_path: str) -> str:
    """
    Gets comprehensive context for a specific file.
    
    This returns all relevant information about a file including:
    - Dependencies (what this file uses)
    - Dependents (what uses this file)  
    - Scene tree (for scenes)
    - Class hierarchy (for scripts)
    - Signal connections
    
    Args:
        file_path: Path to the file, can be:
                   - res:// path (e.g., "res://player.gd")
                   - Relative path (e.g., "player.gd")
                   - Just the filename
    
    Returns:
        Comprehensive context about the file.
    
    Examples:
        - get_file_context("res://player.gd")
        - get_file_context("Main.tscn")
        - get_file_context("enemy.gd")
    """
    engine = get_context_engine()
    
    if engine is None:
        return "Error: Context engine not initialized."
    
    try:
        # Normalize path
        if not file_path.startswith("res://"):
            file_path = f"res://{file_path}"
        
        context = engine.get_file_context(file_path)
        
        if not context.get('dependencies') and not context.get('dependents'):
            # Try partial match
            found = False
            search_name = file_path.replace("res://", "").lower()
            for node_id, data in engine.graph.graph.nodes(data=True):
                path = data.get('path', '').lower()
                if search_name in path:
                    context = engine.get_file_context(data.get('path'))
                    found = True
                    break
            
            if not found:
                return f"File '{file_path}' not found in index.\n\nTips:\n- Check the exact path\n- Try just the filename\n- Ensure the project is indexed"
        
        # Format context
        lines = [f"## File Context: {context.get('path', file_path)}", ""]
        
        # Dependencies
        deps = context.get('dependencies', [])
        if deps:
            lines.append("### Dependencies (what this file uses)")
            for dep in deps[:20]:
                lines.append(f"  - {dep}")
        
        # Dependents
        dependents = context.get('dependents', [])
        if dependents:
            lines.append("\n### Dependents (what uses this file)")
            for dep in dependents[:20]:
                lines.append(f"  - {dep}")
        
        # Class info
        if context.get('class_name'):
            lines.append(f"\n### Class: {context['class_name']}")
            lines.append(f"Extends: {context.get('extends', 'unknown')}")
            if context.get('hierarchy'):
                lines.append(f"Hierarchy: {' → '.join(context['hierarchy'])}")
        
        # Scene tree
        if context.get('scene_tree'):
            tree = context['scene_tree']
            lines.append(f"\n### Scene Tree")
            lines.append(f"Root: {tree.get('root_type', 'Node')}")
            lines.append(f"Nodes: {tree.get('node_count', 0)}")
            for node in tree.get('nodes', [])[:15]:
                script = " [scripted]" if node.get('has_script') else ""
                lines.append(f"  - {node['path']}: {node['type']}{script}")
        
        # Signal connections
        connections = context.get('connections', [])
        if connections:
            lines.append("\n### Signal Connections")
            for conn in connections[:10]:
                lines.append(f"  - {conn['from']} → [{conn['signal']}] → {conn['method']}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error getting file context: {e}")
        return f"Error getting file context: {str(e)}"


@tool
def get_project_structure() -> str:
    """
    Gets a high-level overview of the project structure.
    
    This returns a summary of the entire project including:
    - Project name and statistics
    - List of scenes with node counts
    - List of scripts with class names
    - Autoloads (singletons)
    
    Use this to understand the overall architecture of a project.
    
    Returns:
        A formatted project structure overview.
    """
    engine = get_context_engine()
    
    if engine is None:
        return "Error: Context engine not initialized. Call initialize_session with a project path first."
    
    try:
        return engine.get_project_map()
    except Exception as e:
        logger.error(f"Error getting project structure: {e}")
        return f"Error getting project structure: {str(e)}"


@tool
def get_context_stats() -> str:
    """
    Gets statistics about the context engine and indexes.
    
    Use this to verify the context engine is working correctly
    and see what has been indexed.
    
    Returns:
        Statistics about the knowledge graph and vector store.
    """
    engine = get_context_engine()
    
    if engine is None:
        return "Context engine not initialized."
    
    try:
        stats = engine.get_stats()
        
        lines = ["## Context Engine Statistics", ""]
        lines.append(f"**Indexed:** {'Yes' if stats['indexed'] else 'No'}")
        lines.append(f"**Project:** {stats['project_path']}")
        
        lines.append("\n### Knowledge Graph")
        graph = stats['graph']
        lines.append(f"  - Scenes: {graph['scenes']}")
        lines.append(f"  - Scripts: {graph['scripts']}")  
        lines.append(f"  - Resources: {graph['resources']}")
        lines.append(f"  - Functions: {graph['functions']}")
        lines.append(f"  - Signals: {graph['signal_definitions']}")
        lines.append(f"  - Total Nodes: {graph['total_nodes']}")
        lines.append(f"  - Total Edges: {graph['total_edges']}")
        
        if graph['autoloads']:
            lines.append(f"  - Autoloads: {', '.join(graph['autoloads'])}")
        
        lines.append("\n### Vector Store")
        vs = stats['vector_store']
        if vs['available']:
            lines.append(f"  - Code Chunks: {vs['code_chunks']}")
            lines.append(f"  - Scene Chunks: {vs['scene_chunks']}")
            lines.append(f"  - Doc Chunks: {vs['doc_chunks']}")
            lines.append(f"  - Embedding: {vs['embedding_type']}")
        else:
            lines.append("  - Not available (ChromaDB not installed)")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return f"Error getting stats: {str(e)}"
