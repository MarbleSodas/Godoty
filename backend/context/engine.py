"""
Godot Context Engine.

This module provides the main context engine that combines:
- Knowledge Graph (NetworkX) for structural queries
- Vector Store (ChromaDB) for semantic queries
- Hybrid retrieval with intent-based routing

The context engine is used by the Godoty agent to understand
the structure and semantics of Godot projects.
"""

import json
import logging
import os
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from enum import Enum

from .godot_parsers import (
    parse_tscn, parse_tres, parse_gdscript, parse_project_godot,
    get_godot_file_type
)
from .knowledge_graph import GodotKnowledgeGraph
from .vector_store import GodotVectorStore, SearchResult

logger = logging.getLogger(__name__)


# =============================================================================
# Index Status
# =============================================================================

class IndexStatus(Enum):
    """Status of the context engine index."""
    NOT_STARTED = "not_started"
    SCANNING = "scanning"
    BUILDING_GRAPH = "building_graph"
    BUILDING_VECTORS = "building_vectors"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class IndexProgress:
    """Progress information for indexing."""
    status: IndexStatus = IndexStatus.NOT_STARTED
    phase: str = ""
    current_step: int = 0
    total_steps: int = 0
    current_file: str = ""
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "phase": self.phase,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "current_file": self.current_file,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress_percent": int(
                (self.current_step / self.total_steps * 100) 
                if self.total_steps > 0 else 0
            )
        }


@dataclass
class IndexMetadata:
    """Metadata about a project's index."""
    project_path: str
    project_hash: str  # Hash of project file list for invalidation
    indexed_at: str
    godot_version: Optional[str] = None
    file_count: int = 0
    scene_count: int = 0
    script_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_path": self.project_path,
            "project_hash": self.project_hash,
            "indexed_at": self.indexed_at,
            "godot_version": self.godot_version,
            "file_count": self.file_count,
            "scene_count": self.scene_count,
            "script_count": self.script_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexMetadata":
        return cls(
            project_path=data.get("project_path", ""),
            project_hash=data.get("project_hash", ""),
            indexed_at=data.get("indexed_at", ""),
            godot_version=data.get("godot_version"),
            file_count=data.get("file_count", 0),
            scene_count=data.get("scene_count", 0),
            script_count=data.get("script_count", 0)
        )


# =============================================================================
# Query Intent Classification
# =============================================================================

class QueryIntent(Enum):
    """Types of query intents for routing."""
    STRUCTURAL = "structural"  # Where is X? What uses Y?
    SEMANTIC = "semantic"      # How does X work?
    API = "api"                # What does class X do?
    HYBRID = "hybrid"          # Complex queries needing both


# Intent classification keywords
STRUCTURAL_KEYWORDS = {
    'where', 'find', 'locate', 'uses', 'depends', 'connected', 'signals',
    'inherits', 'extends', 'parent', 'child', 'scene', 'node', 'path'
}

SEMANTIC_KEYWORDS = {
    'how', 'implement', 'work', 'logic', 'algorithm', 'why', 'explain',
    'example', 'code', 'function', 'method'
}

API_KEYWORDS = {
    'what is', 'what does', 'api', 'reference', 'documentation', 'docs',
    'parameters', 'returns', 'godot class', 'built-in'
}


# =============================================================================
# Context Bundle
# =============================================================================

@dataclass
class ContextBundle:
    """Bundle of retrieved context from multiple sources."""
    query: str
    intent: QueryIntent
    
    # Structural context from knowledge graph
    graph_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Semantic context from vector store
    code_results: List[SearchResult] = field(default_factory=list)
    scene_results: List[SearchResult] = field(default_factory=list)
    doc_results: List[SearchResult] = field(default_factory=list)
    
    # Metadata
    token_estimate: int = 0
    
    def to_prompt_context(self, token_budget: int = 4000) -> str:
        """
        Format the context bundle for injection into a prompt.
        
        Args:
            token_budget: Maximum tokens to use (rough estimate: 4 chars = 1 token)
            
        Returns:
            Formatted context string
        """
        sections = []
        remaining_chars = token_budget * 4  # Rough estimate
        
        # Add structural context
        if self.graph_results:
            struct_section = self._format_graph_results()
            if len(struct_section) < remaining_chars * 0.3:
                sections.append(struct_section)
                remaining_chars -= len(struct_section)
        
        # Add code context
        if self.code_results:
            code_section = self._format_code_results(int(remaining_chars * 0.5))
            sections.append(code_section)
            remaining_chars -= len(code_section)
        
        # Add scene context
        if self.scene_results:
            scene_section = self._format_scene_results(int(remaining_chars * 0.3))
            sections.append(scene_section)
            remaining_chars -= len(scene_section)
        
        # Add documentation context
        if self.doc_results:
            doc_section = self._format_doc_results(remaining_chars)
            sections.append(doc_section)
        
        return "\n\n".join(sections)
    
    def _format_graph_results(self) -> str:
        """Format structural graph results."""
        lines = ["## Structural Context"]
        
        for result in self.graph_results[:5]:
            result_type = result.get('type', 'unknown')
            
            if result_type == 'signal_connections':
                lines.append("\n### Signal Connections")
                for conn in result.get('connections', []):
                    lines.append(f"- {conn['from']} → [{conn['signal']}] → {conn['method']}")
            
            elif result_type == 'class_hierarchy':
                lines.append("\n### Class Hierarchy")
                hierarchy = result.get('hierarchy', [])
                lines.append(" → ".join(hierarchy))
            
            elif result_type == 'dependencies':
                lines.append("\n### Dependencies")
                for dep in result.get('deps', [])[:10]:
                    lines.append(f"- {dep}")
            
            elif result_type == 'scene_tree':
                lines.append(f"\n### Scene: {result.get('scene', 'Unknown')}")
                for node in result.get('nodes', [])[:10]:
                    script_marker = " [scripted]" if node.get('has_script') else ""
                    lines.append(f"- {node['path']}: {node['type']}{script_marker}")
        
        return "\n".join(lines)
    
    def _format_code_results(self, max_chars: int) -> str:
        """Format code search results."""
        lines = ["## Relevant Code"]
        char_count = len(lines[0])
        
        for result in self.code_results:
            header = f"\n### {result.name or 'Code'} ({result.file_path})"
            content = f"```gdscript\n{result.content}\n```"
            
            entry = header + "\n" + content
            if char_count + len(entry) > max_chars:
                break
            
            lines.append(entry)
            char_count += len(entry)
        
        return "\n".join(lines)
    
    def _format_scene_results(self, max_chars: int) -> str:
        """Format scene search results."""
        lines = ["## Relevant Scenes"]
        char_count = len(lines[0])
        
        for result in self.scene_results:
            entry = f"\n### {result.name} ({result.file_path})\n{result.content}"
            
            if char_count + len(entry) > max_chars:
                break
            
            lines.append(entry)
            char_count += len(entry)
        
        return "\n".join(lines)
    
    def _format_doc_results(self, max_chars: int) -> str:
        """Format documentation results."""
        lines = ["## Documentation"]
        char_count = len(lines[0])
        
        for result in self.doc_results:
            entry = f"\n### {result.name}\n{result.content}"
            
            if char_count + len(entry) > max_chars:
                break
            
            lines.append(entry)
            char_count += len(entry)
        
        return "\n".join(lines)


# =============================================================================
# Main Context Engine
# =============================================================================

class GodotContextEngine:
    """
    Hybrid context engine combining knowledge graph and vector search.
    
    Provides intelligent context retrieval for Godot projects by:
    - Using knowledge graph for structural queries (dependencies, signals, inheritance)
    - Using vector store for semantic queries (code search, documentation)
    - Intent-based routing to select the best retrieval strategy
    """
    
    INDEX_METADATA_FILE = "context_index.json"
    
    def __init__(self, project_path: str):
        """
        Initialize the context engine.
        
        Args:
            project_path: Path to the Godot project root (containing project.godot)
        """
        self.project_path = project_path
        self.graph = GodotKnowledgeGraph()
        self.vector_store = GodotVectorStore(project_path)
        self._indexed = False
        
        # Index status tracking
        self._progress = IndexProgress()
        self._metadata: Optional[IndexMetadata] = None
        self._status_callbacks: List[Callable[[IndexProgress], None]] = []
        
        logger.info(f"Context engine initialized for: {project_path}")
    
    def add_status_callback(self, callback: Callable[[IndexProgress], None]) -> None:
        """Add a callback for index status updates."""
        self._status_callbacks.append(callback)
    
    def remove_status_callback(self, callback: Callable[[IndexProgress], None]) -> None:
        """Remove a status callback."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    def _notify_status(self) -> None:
        """Notify all callbacks of status change."""
        for callback in self._status_callbacks:
            try:
                callback(self._progress)
            except Exception as e:
                logger.warning(f"Status callback error: {e}")
    
    def get_index_progress(self) -> IndexProgress:
        """Get current indexing progress."""
        return self._progress
    
    def get_index_metadata(self) -> Optional[IndexMetadata]:
        """Get metadata about the current index."""
        return self._metadata
    
    def _get_metadata_path(self) -> str:
        """Get path to the index metadata file."""
        godoty_dir = os.path.join(self.project_path, ".godoty")
        return os.path.join(godoty_dir, self.INDEX_METADATA_FILE)
    
    def _compute_project_hash(self) -> str:
        """Compute a hash of project files for cache invalidation."""
        file_list = []
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      {'__pycache__', 'addons', '.godot', '.import'}]
            for f in files:
                if f.endswith(('.gd', '.tscn', '.tres')):
                    filepath = os.path.join(root, f)
                    mtime = os.path.getmtime(filepath)
                    file_list.append(f"{filepath}:{mtime}")
        
        content = "\n".join(sorted(file_list))
        return hashlib.md5(content.encode()).hexdigest()
    
    def _load_metadata(self) -> Optional[IndexMetadata]:
        """Load index metadata from disk."""
        metadata_path = self._get_metadata_path()
        if not os.path.exists(metadata_path):
            return None
        
        try:
            with open(metadata_path, 'r') as f:
                data = json.load(f)
            return IndexMetadata.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load index metadata: {e}")
            return None
    
    def _save_metadata(self, metadata: IndexMetadata) -> None:
        """Save index metadata to disk."""
        metadata_path = self._get_metadata_path()
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
        
        try:
            with open(metadata_path, 'w') as f:
                json.dump(metadata.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save index metadata: {e}")
    
    def needs_reindex(self) -> bool:
        """
        Check if the project needs to be re-indexed.
        
        Returns:
            True if index is missing, invalid, or outdated
        """
        metadata = self._load_metadata()
        if metadata is None:
            logger.info("No index metadata found - needs indexing")
            return True
        
        current_hash = self._compute_project_hash()
        if metadata.project_hash != current_hash:
            logger.info("Project files changed - needs re-indexing")
            return True
        
        # Check if ChromaDB data exists
        if not self.vector_store.get_stats().get('available', False):
            logger.info("Vector store not available - needs indexing")
            return True
        
        logger.info("Project index is up to date")
        self._metadata = metadata
        self._indexed = True
        return False
    
    def build_index(self, progress_callback: Optional[Callable] = None, force: bool = False) -> None:
        """
        Build the full project index.
        
        Args:
            progress_callback: Optional callback(status, current, total)
            force: If True, rebuild even if cached index is valid
        """
        # Check if we need to index
        if not force and not self.needs_reindex():
            logger.info("Using cached index")
            self._progress.status = IndexStatus.COMPLETE
            self._notify_status()
            return
        
        logger.info("Building context index...")
        self._progress = IndexProgress(
            status=IndexStatus.SCANNING,
            phase="Scanning project files",
            started_at=datetime.utcnow().isoformat()
        )
        self._notify_status()
        
        try:
            # Count files for progress
            file_count = 0
            scene_count = 0
            script_count = 0
            
            for root, dirs, files in os.walk(self.project_path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                          {'__pycache__', 'addons', '.godot', '.import'}]
                for f in files:
                    if f.endswith('.gd'):
                        script_count += 1
                        file_count += 1
                    elif f.endswith('.tscn'):
                        scene_count += 1
                        file_count += 1
                    elif f.endswith('.tres'):
                        file_count += 1
            
            self._progress.total_steps = file_count + 1  # +1 for vectorization
            
            # Build knowledge graph
            self._progress.status = IndexStatus.BUILDING_GRAPH
            self._progress.phase = "Building knowledge graph"
            self._notify_status()
            
            if progress_callback:
                progress_callback("Building knowledge graph...", 0, 2)
            self.graph.build_from_project(self.project_path)
            
            self._progress.current_step = file_count
            self._notify_status()
            
            # Build vector store
            self._progress.status = IndexStatus.BUILDING_VECTORS
            self._progress.phase = "Building semantic index"
            self._notify_status()
            
            if progress_callback:
                progress_callback("Building vector store...", 1, 2)
            
            def vector_progress(status: str, current: int, total: int):
                self._progress.current_file = status
                self._progress.current_step = file_count + current
                self._progress.total_steps = file_count + total
                self._notify_status()
            
            self.vector_store.index_project(vector_progress)
            
            # Save metadata
            self._metadata = IndexMetadata(
                project_path=self.project_path,
                project_hash=self._compute_project_hash(),
                indexed_at=datetime.utcnow().isoformat(),
                file_count=file_count,
                scene_count=scene_count,
                script_count=script_count
            )
            self._save_metadata(self._metadata)
            
            # Complete
            self._indexed = True
            self._progress.status = IndexStatus.COMPLETE
            self._progress.phase = "Indexing complete"
            self._progress.completed_at = datetime.utcnow().isoformat()
            self._notify_status()
            
            logger.info("Context index built successfully")
            
        except Exception as e:
            logger.error(f"Error building index: {e}")
            self._progress.status = IndexStatus.FAILED
            self._progress.phase = "Indexing failed"
            self._progress.error = str(e)
            self._notify_status()
            raise
    
    def is_indexed(self) -> bool:
        """Check if the project has been indexed."""
        return self._indexed
    
    # =========================================================================
    # Intent Classification
    # =========================================================================
    
    def classify_intent(self, query: str) -> QueryIntent:
        """
        Classify the intent of a query to determine routing strategy.
        
        Args:
            query: The user's query
            
        Returns:
            QueryIntent enum value
        """
        query_lower = query.lower()
        words = set(query_lower.split())
        
        structural_score = len(words & STRUCTURAL_KEYWORDS)
        semantic_score = len(words & SEMANTIC_KEYWORDS)
        api_score = sum(1 for kw in API_KEYWORDS if kw in query_lower)
        
        # Check for specific patterns
        if 'what is' in query_lower or 'what does' in query_lower:
            api_score += 2
        if 'how to' in query_lower or 'how do' in query_lower:
            semantic_score += 2
        if 'where' in query_lower or 'find' in query_lower:
            structural_score += 2
        
        max_score = max(structural_score, semantic_score, api_score)
        
        if max_score == 0:
            return QueryIntent.HYBRID
        elif structural_score == max_score:
            return QueryIntent.STRUCTURAL
        elif semantic_score == max_score:
            return QueryIntent.SEMANTIC
        else:
            return QueryIntent.API
    
    # =========================================================================
    # Retrieval Methods
    # =========================================================================
    
    def retrieve_context(
        self,
        query: str,
        intent: str = "auto",
        limit: int = 10
    ) -> ContextBundle:
        """
        Main retrieval method implementing hybrid RAG.
        
        Args:
            query: The search query
            intent: "structural", "semantic", "api", "hybrid", or "auto"
            limit: Maximum results per source
            
        Returns:
            ContextBundle with all retrieved context
        """
        # Determine intent
        if intent == "auto":
            detected_intent = self.classify_intent(query)
        else:
            detected_intent = QueryIntent(intent)
        
        bundle = ContextBundle(query=query, intent=detected_intent)
        
        # Route based on intent
        if detected_intent in (QueryIntent.STRUCTURAL, QueryIntent.HYBRID):
            bundle.graph_results = self._retrieve_structural(query, limit)
        
        if detected_intent in (QueryIntent.SEMANTIC, QueryIntent.HYBRID):
            bundle.code_results = self.vector_store.search_code(query, limit)
        
        if detected_intent in (QueryIntent.API, QueryIntent.HYBRID):
            bundle.doc_results = self.vector_store.search_docs(query, limit)
        
        # Always include some scene context for complex queries
        if detected_intent == QueryIntent.HYBRID:
            bundle.scene_results = self.vector_store.search_scenes(query, limit // 2)
        
        return bundle
    
    def _retrieve_structural(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Retrieve structural context from the knowledge graph."""
        results = []
        query_lower = query.lower()
        
        # Extract potential entity names from query
        entities = self._extract_entities(query)
        
        for entity in entities:
            # Try to find signal connections
            if 'signal' in query_lower or 'connect' in query_lower:
                connections = self.graph.get_signal_connections(entity)
                if connections:
                    results.append({
                        'type': 'signal_connections',
                        'entity': entity,
                        'connections': connections
                    })
            
            # Try to find class hierarchy
            if 'inherit' in query_lower or 'extend' in query_lower or 'class' in query_lower:
                # Look for script with this class name
                for node_id, data in self.graph.graph.nodes(data=True):
                    if data.get('class_name') == entity or data.get('name') == entity:
                        path = data.get('path', '')
                        if path:
                            hierarchy = self.graph.get_class_hierarchy(path)
                            if hierarchy:
                                results.append({
                                    'type': 'class_hierarchy',
                                    'entity': entity,
                                    'hierarchy': hierarchy
                                })
            
            # Try to find dependencies
            if 'depend' in query_lower or 'use' in query_lower:
                deps = self.graph.get_dependencies(entity)
                if deps:
                    results.append({
                        'type': 'dependencies',
                        'entity': entity,
                        'deps': deps
                    })
            
            # Try to find scene tree
            if 'scene' in query_lower or 'node' in query_lower:
                # Look for matching scene
                for node_id, data in self.graph.graph.nodes(data=True):
                    name = data.get('name', '').lower()
                    if entity.lower() in name and data.get('type') == 'scene':
                        path = data.get('path', '')
                        tree = self.graph.get_scene_tree(path)
                        if tree:
                            results.append({
                                'type': 'scene_tree',
                                'scene': path,
                                'nodes': tree.get('nodes', [])
                            })
        
        return results[:limit]
    
    def _extract_entities(self, query: str) -> List[str]:
        """Extract potential entity names from a query."""
        import re
        
        # Look for quoted strings
        quoted = re.findall(r'"([^"]+)"', query)
        if quoted:
            return quoted
        
        # Look for PascalCase words (likely class names)
        pascal = re.findall(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', query)
        
        # Look for words that might be identifiers
        words = query.split()
        potential = []
        skip_words = {'the', 'a', 'an', 'is', 'are', 'what', 'where', 'how', 'why',
                     'does', 'do', 'to', 'for', 'in', 'on', 'with', 'of', 'and', 'or'}
        
        for word in words:
            clean = word.strip('?.,!:;()[]{}')
            if clean and clean.lower() not in skip_words and len(clean) > 2:
                potential.append(clean)
        
        return pascal + potential
    
    # =========================================================================
    # High-Level Context Methods  
    # =========================================================================
    
    def get_project_map(self) -> str:
        """
        Get a high-level project structure map.
        
        This is suitable for injection into the system prompt to give
        the agent an overview of the project.
        
        Returns:
            Formatted project map string
        """
        return self.graph.to_text_summary()
    
    def get_context_for_prompt(self, user_query: str, token_budget: int = 4000) -> str:
        """
        Get formatted context for prompt injection.
        
        This combines the project map with query-specific context.
        
        Args:
            user_query: The user's query
            token_budget: Maximum tokens to use
            
        Returns:
            Formatted context string suitable for prompt injection
        """
        # Reserve some budget for project map
        map_budget = min(1000, token_budget // 4)
        query_budget = token_budget - map_budget
        
        # Get project map (truncated)
        project_map = self.get_project_map()
        if len(project_map) > map_budget * 4:
            project_map = project_map[:map_budget * 4] + "\n... (truncated)"
        
        # Get query-specific context
        bundle = self.retrieve_context(user_query, intent="auto", limit=5)
        query_context = bundle.to_prompt_context(query_budget)
        
        return f"""=== PROJECT OVERVIEW ===
{project_map}

=== QUERY-SPECIFIC CONTEXT ===
{query_context}"""
    
    # =========================================================================
    # Specific Query Methods
    # =========================================================================
    
    def get_signal_connections(self, node_or_signal: str) -> List[Dict[str, Any]]:
        """
        Get signal connections for a node or signal.
        
        Args:
            node_or_signal: Node path or signal name
            
        Returns:
            List of connection dictionaries
        """
        return self.graph.get_signal_connections(node_or_signal)
    
    def get_class_hierarchy(self, class_name: str) -> List[str]:
        """
        Get the inheritance chain for a class.
        
        Args:
            class_name: GDScript class name
            
        Returns:
            List of class names from child to parent
        """
        # Find the script with this class name
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get('class_name') == class_name:
                path = data.get('path', '')
                if path:
                    return self.graph.get_class_hierarchy(path)
        return []
    
    def find_usages(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        Find all usages of an entity.
        
        Args:
            entity_name: Class, function, or signal name
            
        Returns:
            List of usage dictionaries
        """
        return self.graph.find_usages(entity_name)
    
    def get_file_context(self, file_path: str) -> Dict[str, Any]:
        """
        Get full context for a specific file.
        
        Args:
            file_path: res:// path to the file
            
        Returns:
            Dictionary with file context
        """
        context = {
            'path': file_path,
            'dependencies': self.graph.get_dependencies(file_path),
            'dependents': self.graph.get_dependents(file_path)
        }
        
        # Get file type specific info
        file_type = get_godot_file_type(file_path)
        
        if file_type == 'scene':
            context['scene_tree'] = self.graph.get_scene_tree(file_path)
            context['connections'] = self.get_signal_connections(file_path)
        
        elif file_type == 'script':
            # Find class info
            for node_id, data in self.graph.graph.nodes(data=True):
                if data.get('path') == file_path and data.get('type') == 'script':
                    context['class_name'] = data.get('class_name')
                    context['extends'] = data.get('extends')
                    context['hierarchy'] = self.graph.get_class_hierarchy(file_path)
                    break
        
        return context
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the context engine."""
        graph_summary = self.graph.get_project_summary()
        vector_stats = self.vector_store.get_stats()
        
        return {
            'indexed': self._indexed,
            'project_path': self.project_path,
            'graph': graph_summary,
            'vector_store': vector_stats
        }
