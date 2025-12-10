"""
Agno Knowledge Integration for Godot Context Engine.

This module provides Agno-compatible Knowledge sources that wrap
the existing GodotContextEngine for seamless integration with
Agno agents.

Components:
- GodotProjectKnowledge: Agentic RAG knowledge source using LanceDB
- GodotContextRetriever: Custom retriever using the context engine
- GodotDocumentProcessor: Processes Godot files into Document format
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from agno.knowledge import AgentKnowledge
from agno.vectordb.lancedb import LanceDb
from agno.document import Document
from agno.embedder.openai import OpenAIEmbedder

from .engine import GodotContextEngine, ContextBundle, QueryIntent, IndexProgress, IndexStatus
from .godot_parsers import parse_tscn, parse_gdscript, get_godot_file_type

logger = logging.getLogger(__name__)


# =============================================================================
# Godot Document Types
# =============================================================================

class GodotDocumentType:
    """Document types for Godot project files."""
    SCRIPT = "gdscript"
    SCENE = "scene"
    RESOURCE = "resource"
    CONFIG = "config"
    DOCUMENTATION = "documentation"


# =============================================================================
# Document Processing
# =============================================================================

@dataclass
class GodotDocument:
    """A Godot-specific document for the knowledge base."""
    id: str
    name: str
    content: str
    doc_type: str
    file_path: str
    metadata: Dict[str, Any]
    
    def to_agno_document(self) -> Document:
        """Convert to Agno Document format."""
        return Document(
            id=self.id,
            name=self.name,
            content=self.content,
            meta_data={
                "doc_type": self.doc_type,
                "file_path": self.file_path,
                **self.metadata
            }
        )


class GodotDocumentProcessor:
    """Process Godot project files into documents for the knowledge base."""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
    
    def process_project(self, progress_callback: Optional[Callable[[str, int, int], None]] = None) -> List[Document]:
        """
        Process all relevant files in the Godot project.
        
        Args:
            progress_callback: Optional callback(status, current, total)
            
        Returns:
            List of Agno Documents
        """
        documents = []
        
        # Collect files to process
        files = []
        for root, dirs, filenames in os.walk(self.project_path):
            # Skip hidden directories and common excludes
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      {'__pycache__', 'addons', '.godot', '.import', 'node_modules'}]
            
            for filename in filenames:
                file_path = Path(root) / filename
                if self._should_process(file_path):
                    files.append(file_path)
        
        total = len(files)
        
        # Process each file
        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(f"Processing {file_path.name}", i, total)
            
            try:
                docs = self._process_file(file_path)
                documents.extend(docs)
            except Exception as e:
                logger.warning(f"Error processing {file_path}: {e}")
        
        logger.info(f"Processed {len(files)} files into {len(documents)} documents")
        return documents
    
    def _should_process(self, file_path: Path) -> bool:
        """Check if a file should be processed."""
        suffix = file_path.suffix.lower()
        return suffix in {'.gd', '.tscn', '.tres', '.godot', '.cfg'}
    
    def _process_file(self, file_path: Path) -> List[Document]:
        """Process a single file into documents."""
        suffix = file_path.suffix.lower()
        rel_path = file_path.relative_to(self.project_path)
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if suffix == '.gd':
            return self._process_gdscript(file_path, rel_path, content)
        elif suffix == '.tscn':
            return self._process_scene(file_path, rel_path, content)
        elif suffix == '.tres':
            return self._process_resource(file_path, rel_path, content)
        elif suffix in {'.godot', '.cfg'}:
            return self._process_config(file_path, rel_path, content)
        
        return []
    
    def _process_gdscript(self, file_path: Path, rel_path: Path, content: str) -> List[Document]:
        """Process a GDScript file into documents."""
        documents = []
        
        # Parse script info
        parsed = parse_gdscript(str(file_path))
        
        # Create main document for the script
        doc_id = f"script:{rel_path}"
        metadata = {
            "class_name": parsed.get("class_name", ""),
            "extends": parsed.get("extends", ""),
            "function_count": len(parsed.get("functions", [])),
            "signal_count": len(parsed.get("signals", [])),
        }
        
        doc = Document(
            id=doc_id,
            name=file_path.stem,
            content=content,
            meta_data={
                "doc_type": GodotDocumentType.SCRIPT,
                "file_path": str(rel_path),
                **metadata
            }
        )
        documents.append(doc)
        
        # Create separate documents for each function (for fine-grained search)
        for func in parsed.get("functions", []):
            func_name = func.get("name", "")
            func_content = func.get("body", "")
            if func_name and func_content:
                func_doc = Document(
                    id=f"func:{rel_path}:{func_name}",
                    name=f"{file_path.stem}.{func_name}",
                    content=f"func {func_name}({func.get('args', '')}):\n{func_content}",
                    meta_data={
                        "doc_type": GodotDocumentType.SCRIPT,
                        "file_path": str(rel_path),
                        "function_name": func_name,
                        "parent_class": parsed.get("class_name", file_path.stem),
                    }
                )
                documents.append(func_doc)
        
        return documents
    
    def _process_scene(self, file_path: Path, rel_path: Path, content: str) -> List[Document]:
        """Process a scene file into documents."""
        parsed = parse_tscn(str(file_path))
        
        # Extract node info for metadata
        nodes = parsed.get("nodes", [])
        node_types = list(set(n.get("type", "") for n in nodes if n.get("type")))
        
        metadata = {
            "node_count": len(nodes),
            "root_type": parsed.get("root_type", ""),
            "has_scripts": any(n.get("script") for n in nodes),
            "node_types": node_types[:10],  # Limit to avoid huge metadata
        }
        
        # Create scene structure summary
        structure_lines = []
        for node in nodes[:50]:  # Limit node output
            indent = "  " * node.get("depth", 0)
            name = node.get("name", "")
            node_type = node.get("type", "")
            script = " [scripted]" if node.get("script") else ""
            structure_lines.append(f"{indent}- {name} ({node_type}){script}")
        
        structure_summary = "\n".join(structure_lines)
        if len(nodes) > 50:
            structure_summary += f"\n... and {len(nodes) - 50} more nodes"
        
        doc_content = f"""Scene: {rel_path}
Root: {parsed.get('root_type', 'Unknown')}
Node Count: {len(nodes)}

Scene Structure:
{structure_summary}

Raw Scene Data:
{content[:3000]}...
"""
        
        doc = Document(
            id=f"scene:{rel_path}",
            name=file_path.stem,
            content=doc_content,
            meta_data={
                "doc_type": GodotDocumentType.SCENE,
                "file_path": str(rel_path),
                **metadata
            }
        )
        
        return [doc]
    
    def _process_resource(self, file_path: Path, rel_path: Path, content: str) -> List[Document]:
        """Process a resource file into documents."""
        doc = Document(
            id=f"resource:{rel_path}",
            name=file_path.stem,
            content=content[:5000],  # Limit content size
            meta_data={
                "doc_type": GodotDocumentType.RESOURCE,
                "file_path": str(rel_path),
            }
        )
        return [doc]
    
    def _process_config(self, file_path: Path, rel_path: Path, content: str) -> List[Document]:
        """Process a config file into documents."""
        doc = Document(
            id=f"config:{rel_path}",
            name=file_path.name,
            content=content,
            meta_data={
                "doc_type": GodotDocumentType.CONFIG,
                "file_path": str(rel_path),
            }
        )
        return [doc]


# =============================================================================
# Custom Knowledge Retriever
# =============================================================================

class GodotContextRetriever:
    """
    Custom retriever that uses the GodotContextEngine for hybrid search.
    
    This allows using the existing context engine's sophisticated
    intent-based routing while integrating with Agno's Knowledge system.
    """
    
    def __init__(self, context_engine: GodotContextEngine):
        self.context_engine = context_engine
    
    def retrieve(self, query: str, num_documents: int = 10) -> List[Document]:
        """
        Retrieve relevant documents using the context engine.
        
        Args:
            query: The search query
            num_documents: Maximum documents to return
            
        Returns:
            List of Agno Documents
        """
        # Use context engine's hybrid retrieval
        bundle = self.context_engine.retrieve_context(
            query=query,
            intent="auto",
            limit=num_documents
        )
        
        documents = []
        
        # Convert code results
        for result in bundle.code_results:
            doc = Document(
                id=f"code:{result.file_path}:{result.name}",
                name=result.name or "Code",
                content=result.content,
                meta_data={
                    "doc_type": GodotDocumentType.SCRIPT,
                    "file_path": result.file_path,
                    "score": result.score,
                }
            )
            documents.append(doc)
        
        # Convert scene results
        for result in bundle.scene_results:
            doc = Document(
                id=f"scene:{result.file_path}",
                name=result.name or "Scene",
                content=result.content,
                meta_data={
                    "doc_type": GodotDocumentType.SCENE,
                    "file_path": result.file_path,
                    "score": result.score,
                }
            )
            documents.append(doc)
        
        # Convert graph results to documents
        for result in bundle.graph_results:
            content = self._format_graph_result(result)
            doc = Document(
                id=f"graph:{result.get('type')}:{result.get('entity', 'unknown')}",
                name=f"Structure: {result.get('type', 'unknown')}",
                content=content,
                meta_data={
                    "doc_type": "structural",
                    "result_type": result.get('type'),
                }
            )
            documents.append(doc)
        
        return documents[:num_documents]
    
    def _format_graph_result(self, result: Dict[str, Any]) -> str:
        """Format a graph result as readable content."""
        result_type = result.get('type', 'unknown')
        entity = result.get('entity', 'Unknown')
        
        if result_type == 'signal_connections':
            connections = result.get('connections', [])
            lines = [f"Signal connections for {entity}:"]
            for conn in connections:
                lines.append(f"  {conn['from']} → [{conn['signal']}] → {conn['method']}")
            return "\n".join(lines)
        
        elif result_type == 'class_hierarchy':
            hierarchy = result.get('hierarchy', [])
            return f"Class hierarchy for {entity}: {' → '.join(hierarchy)}"
        
        elif result_type == 'dependencies':
            deps = result.get('deps', [])
            return f"Dependencies for {entity}:\n" + "\n".join(f"  - {d}" for d in deps)
        
        elif result_type == 'scene_tree':
            nodes = result.get('nodes', [])
            lines = [f"Scene tree for {result.get('scene', 'Unknown')}:"]
            for node in nodes[:20]:
                script_marker = " [scripted]" if node.get('has_script') else ""
                lines.append(f"  {node['path']}: {node['type']}{script_marker}")
            return "\n".join(lines)
        
        return str(result)


# =============================================================================
# Agno Knowledge Source
# =============================================================================

class GodotProjectKnowledge(AgentKnowledge):
    """
    Agno Knowledge source for Godot projects.
    
    This knowledge source provides:
    - Vector search using LanceDB for semantic queries
    - Custom retriever using GodotContextEngine for hybrid queries
    - Automatic indexing and re-indexing of project files
    
    Usage:
        knowledge = GodotProjectKnowledge(
            project_path="/path/to/godot/project",
            embedder=OpenAIEmbedder(...)  # or other embedder
        )
        await knowledge.build_index()
        
        # Use with agent
        agent = Agent(
            knowledge=knowledge,
            search_knowledge=True,  # Enable agentic RAG
        )
    """
    
    def __init__(
        self,
        project_path: str,
        embedder: Optional[OpenAIEmbedder] = None,
        use_hybrid_retrieval: bool = True,
        data_dir: str = ".godoty",
        **kwargs
    ):
        """
        Initialize Godot project knowledge.
        
        Args:
            project_path: Path to the Godot project root
            embedder: Embedder for vector search (defaults to OpenAI)
            use_hybrid_retrieval: Use context engine for hybrid retrieval
            data_dir: Directory for storing index data
        """
        self.project_path = Path(project_path)
        self.use_hybrid_retrieval = use_hybrid_retrieval
        self.data_dir = self.project_path / data_dir
        self.data_dir.mkdir(exist_ok=True)
        
        # Initialize context engine for hybrid retrieval
        self.context_engine = GodotContextEngine(str(self.project_path))
        
        # Create custom retriever
        self._custom_retriever = GodotContextRetriever(self.context_engine) if use_hybrid_retrieval else None
        
        # Initialize LanceDB vector store
        lance_uri = str(self.data_dir / "lancedb")
        vector_db = LanceDb(
            uri=lance_uri,
            table_name="godot_project",
            embedder=embedder or OpenAIEmbedder(),
        )
        
        # Document processor
        self._processor = GodotDocumentProcessor(str(self.project_path))
        
        # Indexing state
        self._indexed = False
        self._index_progress = IndexProgress()
        
        # Initialize parent
        super().__init__(
            vector_db=vector_db,
            **kwargs
        )
    
    @property
    def indexed(self) -> bool:
        """Check if the knowledge base has been indexed."""
        return self._indexed
    
    def get_index_progress(self) -> IndexProgress:
        """Get current indexing progress."""
        return self._index_progress
    
    async def build_index(
        self,
        force: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> None:
        """
        Build or rebuild the knowledge index.
        
        Args:
            force: Force rebuild even if index exists
            progress_callback: Optional callback(status, current, total)
        """
        # Check if we need to rebuild
        if not force and self._check_index_valid():
            logger.info("Index is up to date, skipping rebuild")
            self._indexed = True
            return
        
        logger.info(f"Building knowledge index for {self.project_path}")
        self._index_progress = IndexProgress(
            status=IndexStatus.SCANNING,
            phase="Processing project files",
            started_at=datetime.utcnow().isoformat()
        )
        
        try:
            # Process project files into documents
            def doc_progress(status: str, current: int, total: int):
                self._index_progress.current_file = status
                self._index_progress.current_step = current
                self._index_progress.total_steps = total
                if progress_callback:
                    progress_callback(status, current, total)
            
            documents = self._processor.process_project(doc_progress)
            
            # Build vector index
            self._index_progress.status = IndexStatus.BUILDING_VECTORS
            self._index_progress.phase = "Building vector embeddings"
            
            # Clear existing documents and add new ones
            self.vector_db.clear()
            await self.aload_documents(documents)
            
            # Build context engine index for hybrid retrieval
            if self.use_hybrid_retrieval:
                self._index_progress.status = IndexStatus.BUILDING_GRAPH
                self._index_progress.phase = "Building knowledge graph"
                self.context_engine.build_index(force=True)
            
            # Save index metadata
            self._save_index_metadata()
            
            self._indexed = True
            self._index_progress.status = IndexStatus.COMPLETE
            self._index_progress.phase = "Indexing complete"
            self._index_progress.completed_at = datetime.utcnow().isoformat()
            
            logger.info(f"Knowledge index built: {len(documents)} documents")
            
        except Exception as e:
            logger.error(f"Error building knowledge index: {e}")
            self._index_progress.status = IndexStatus.FAILED
            self._index_progress.error = str(e)
            raise
    
    def _check_index_valid(self) -> bool:
        """Check if the existing index is valid."""
        metadata_path = self.data_dir / "knowledge_index.json"
        if not metadata_path.exists():
            return False
        
        try:
            import json
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Check if project hash matches
            current_hash = self._compute_project_hash()
            if metadata.get("project_hash") != current_hash:
                return False
            
            return True
            
        except Exception:
            return False
    
    def _save_index_metadata(self) -> None:
        """Save index metadata for cache invalidation."""
        import json
        
        metadata = {
            "project_path": str(self.project_path),
            "project_hash": self._compute_project_hash(),
            "indexed_at": datetime.utcnow().isoformat(),
        }
        
        metadata_path = self.data_dir / "knowledge_index.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def _compute_project_hash(self) -> str:
        """Compute a hash of project files for cache invalidation."""
        import hashlib
        
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
    
    async def search(
        self,
        query: str,
        num_documents: int = 10,
        **kwargs
    ) -> List[Document]:
        """
        Search the knowledge base.
        
        Uses hybrid retrieval if enabled, otherwise falls back to
        pure vector search.
        
        Args:
            query: Search query
            num_documents: Maximum documents to return
            
        Returns:
            List of relevant documents
        """
        if self.use_hybrid_retrieval and self._custom_retriever:
            # Use context engine's hybrid retrieval
            return self._custom_retriever.retrieve(query, num_documents)
        else:
            # Fall back to vector search
            return await super().search(query, num_documents=num_documents, **kwargs)
    
    def get_project_context(self, token_budget: int = 4000) -> str:
        """
        Get formatted project context for system prompt injection.
        
        Args:
            token_budget: Maximum tokens to use
            
        Returns:
            Formatted project overview
        """
        return self.context_engine.get_project_map()
    
    def get_query_context(self, query: str, token_budget: int = 4000) -> str:
        """
        Get query-specific context for prompt injection.
        
        Args:
            query: The user's query
            token_budget: Maximum tokens to use
            
        Returns:
            Formatted context relevant to the query
        """
        return self.context_engine.get_context_for_prompt(query, token_budget)


# =============================================================================
# Convenience Functions
# =============================================================================

def create_godot_knowledge(
    project_path: str,
    api_key: Optional[str] = None,
    use_hybrid: bool = True
) -> GodotProjectKnowledge:
    """
    Create a Godot project knowledge source.
    
    Args:
        project_path: Path to the Godot project
        api_key: OpenAI API key for embeddings (uses env var if not provided)
        use_hybrid: Enable hybrid retrieval with context engine
        
    Returns:
        Configured GodotProjectKnowledge instance
    """
    embedder = OpenAIEmbedder(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        model="text-embedding-3-small"
    )
    
    return GodotProjectKnowledge(
        project_path=project_path,
        embedder=embedder,
        use_hybrid_retrieval=use_hybrid
    )
