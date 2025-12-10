"""
Vector Store Module for Godot Projects.

This module implements a ChromaDB-based vector store for semantic search
over GDScript code, scene descriptions, and documentation.

Features:
- Syntax-aware code chunking for GDScript
- Metadata filtering by file type, function, class
- Persistent storage for session continuity
"""

import logging
import os
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)

# Optional imports - gracefully handle missing dependencies
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not available. Vector search will be disabled.")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available. Using fallback embeddings.")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CodeChunk:
    """A chunk of code with metadata."""
    content: str
    file_path: str
    chunk_type: str  # "function", "class", "property", "signal_handler", "class_header"
    name: Optional[str] = None
    class_name: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    docstring: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_id(self) -> str:
        """Generate unique ID for this chunk."""
        content_hash = hashlib.md5(self.content.encode()).hexdigest()[:8]
        return f"{self.file_path}:{self.chunk_type}:{self.name or 'anon'}:{content_hash}"


@dataclass
class SearchResult:
    """A search result from the vector store."""
    content: str
    file_path: str
    chunk_type: str
    name: Optional[str]
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Syntax-Aware Chunker
# =============================================================================

class GDScriptChunker:
    """
    Chunks GDScript based on syntax structure, not arbitrary splits.
    
    Creates chunks at function/class boundaries to ensure retrieved
    code is syntactically complete and meaningful.
    """
    
    def __init__(self, max_chunk_size: int = 1500):
        self.max_chunk_size = max_chunk_size
    
    def chunk_script(self, content: str, file_path: str) -> List[CodeChunk]:
        """
        Split a GDScript file into semantic chunks.
        
        Args:
            content: The script content
            file_path: Path for metadata
            
        Returns:
            List of CodeChunks
        """
        chunks = []
        lines = content.split('\n')
        
        # Extract script-level info
        class_name = None
        extends = None
        
        for line in lines:
            if line.startswith('class_name '):
                class_name = line.split()[1].strip()
            elif line.startswith('extends '):
                extends = line.split()[1].strip()
        
        # Create class header chunk (exports, onready vars, constants)
        header_chunk = self._extract_header_chunk(lines, file_path, class_name, extends)
        if header_chunk:
            chunks.append(header_chunk)
        
        # Find and chunk functions
        func_chunks = self._extract_functions(lines, file_path, class_name)
        chunks.extend(func_chunks)
        
        # If no chunks created, create a single chunk for the whole file
        if not chunks and content.strip():
            chunks.append(CodeChunk(
                content=content[:self.max_chunk_size],
                file_path=file_path,
                chunk_type="file",
                name=Path(file_path).stem,
                class_name=class_name,
                line_start=1,
                line_end=len(lines),
                metadata={"extends": extends}
            ))
        
        return chunks
    
    def _extract_header_chunk(self, lines: List[str], file_path: str, 
                              class_name: Optional[str], extends: Optional[str]) -> Optional[CodeChunk]:
        """Extract the class header (imports, exports, signals, etc.)."""
        header_lines = []
        header_end = 0
        in_function = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Stop at first function definition
            if stripped.startswith('func ') or stripped.startswith('static func '):
                in_function = True
                header_end = i
                break
            
            # Include these in header
            if (stripped.startswith('extends ') or
                stripped.startswith('class_name ') or
                stripped.startswith('@export') or
                stripped.startswith('@onready') or
                stripped.startswith('signal ') or
                stripped.startswith('const ') or
                stripped.startswith('var ') or
                stripped.startswith('enum ') or
                stripped.startswith('##') or
                stripped.startswith('#') or
                stripped == ''):
                header_lines.append(line)
        
        if not header_lines:
            return None
        
        content = '\n'.join(header_lines)
        if len(content) < 20:  # Skip nearly empty headers
            return None
        
        return CodeChunk(
            content=content,
            file_path=file_path,
            chunk_type="class_header",
            name=class_name or Path(file_path).stem,
            class_name=class_name,
            line_start=1,
            line_end=header_end or len(header_lines),
            metadata={"extends": extends}
        )
    
    def _extract_functions(self, lines: List[str], file_path: str,
                          class_name: Optional[str]) -> List[CodeChunk]:
        """Extract function chunks from the script."""
        chunks = []
        current_func = None
        func_lines = []
        func_start = 0
        func_docstring = []
        base_indent = 0
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check for function definition
            if stripped.startswith('func ') or stripped.startswith('static func '):
                # Save previous function if exists
                if current_func and func_lines:
                    chunks.append(self._create_function_chunk(
                        current_func, func_lines, func_start, i - 1,
                        file_path, class_name, func_docstring
                    ))
                
                # Start new function
                is_static = stripped.startswith('static ')
                func_def = stripped.replace('static ', '')
                
                # Parse function name
                try:
                    name_part = func_def.split('(')[0].replace('func ', '').strip()
                except:
                    name_part = "unknown"
                
                current_func = name_part
                func_lines = [line]
                func_start = i + 1
                base_indent = len(line) - len(line.lstrip())
                
                # Look back for docstring (## comments)
                func_docstring = []
                for j in range(i - 1, max(0, i - 10), -1):
                    prev = lines[j].strip()
                    if prev.startswith('##'):
                        func_docstring.insert(0, prev[2:].strip())
                    elif prev == '':
                        continue
                    else:
                        break
                
            elif current_func:
                # Check if we're still in the function
                if stripped == '':
                    func_lines.append(line)
                elif line.startswith('\t') or line.startswith(' ' * (base_indent + 1)):
                    func_lines.append(line)
                elif stripped.startswith('#'):
                    func_lines.append(line)
                else:
                    # End of function
                    chunks.append(self._create_function_chunk(
                        current_func, func_lines, func_start, i - 1,
                        file_path, class_name, func_docstring
                    ))
                    current_func = None
                    func_lines = []
                    func_docstring = []
                    continue  # Don't increment i, process this line again
            
            i += 1
        
        # Handle last function
        if current_func and func_lines:
            chunks.append(self._create_function_chunk(
                current_func, func_lines, func_start, len(lines),
                file_path, class_name, func_docstring
            ))
        
        return chunks
    
    def _create_function_chunk(self, func_name: str, lines: List[str],
                               start: int, end: int, file_path: str,
                               class_name: Optional[str],
                               docstring_lines: List[str]) -> CodeChunk:
        """Create a CodeChunk for a function."""
        content = '\n'.join(lines)
        
        # Determine chunk type based on function name
        if func_name.startswith('_on_'):
            chunk_type = "signal_handler"
        elif func_name.startswith('_'):
            chunk_type = "virtual_method"
        else:
            chunk_type = "function"
        
        docstring = '\n'.join(docstring_lines) if docstring_lines else None
        
        return CodeChunk(
            content=content[:self.max_chunk_size],
            file_path=file_path,
            chunk_type=chunk_type,
            name=func_name,
            class_name=class_name,
            line_start=start,
            line_end=end,
            docstring=docstring,
            metadata={"is_virtual": func_name.startswith('_')}
        )


class SceneChunker:
    """Chunks scene files into meaningful descriptions."""
    
    def chunk_scene(self, scene_data: Dict[str, Any], file_path: str) -> List[CodeChunk]:
        """Create searchable chunks from a parsed scene."""
        chunks = []
        
        # Create a scene overview chunk
        root_type = scene_data.get('root_type', 'Node')
        node_count = scene_data.get('node_count', 0)
        nodes = scene_data.get('nodes', [])
        
        # Build description
        node_types = {}
        for node in nodes:
            ntype = node.get('type', 'Node')
            node_types[ntype] = node_types.get(ntype, 0) + 1
        
        type_summary = ', '.join(f"{count}x {t}" for t, count in sorted(node_types.items()))
        
        description = f"""Scene: {Path(file_path).stem}
Root: {root_type}
Total nodes: {node_count}
Node types: {type_summary}
"""
        
        # Add node hierarchy
        if nodes:
            description += "\nHierarchy:\n"
            for node in nodes[:20]:  # Limit for chunk size
                path = node.get('path', node.get('name', ''))
                ntype = node.get('type', 'Node')
                has_script = " [scripted]" if node.get('has_script') else ""
                description += f"  {path}: {ntype}{has_script}\n"
        
        chunks.append(CodeChunk(
            content=description,
            file_path=file_path,
            chunk_type="scene",
            name=Path(file_path).stem,
            metadata={"root_type": root_type, "node_count": node_count}
        ))
        
        return chunks


# =============================================================================
# Embedding Functions
# =============================================================================

class EmbeddingFunction:
    """Base class for embedding functions."""
    
    def __call__(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class SentenceTransformerEmbedding(EmbeddingFunction):
    """Embedding using sentence-transformers models."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers required: pip install sentence-transformers")
        self.model = SentenceTransformer(model_name)
    
    def __call__(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()


class SimpleHashEmbedding(EmbeddingFunction):
    """Fallback embedding using simple hashing (for testing without ML models)."""
    
    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions
    
    def __call__(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            # Create a simple hash-based embedding
            text_hash = hashlib.sha256(text.encode()).digest()
            # Convert to floats in range [-1, 1]
            embedding = []
            for i in range(self.dimensions):
                byte_val = text_hash[i % len(text_hash)]
                embedding.append((byte_val / 127.5) - 1.0)
            embeddings.append(embedding)
        return embeddings


# =============================================================================
# Vector Store Implementation
# =============================================================================

class GodotVectorStore:
    """
    ChromaDB-based vector store for semantic search.
    
    Provides:
    - Code search across GDScript functions
    - Scene structure search
    - Documentation search
    """
    
    def __init__(self, project_path: str, persist_dir: Optional[str] = None):
        """
        Initialize the vector store.
        
        Args:
            project_path: Path to the Godot project
            persist_dir: Optional directory for persistence (defaults to .godoty/context_db)
        """
        self.project_path = project_path
        
        # Set up persistence directory
        if persist_dir is None:
            persist_dir = os.path.join(project_path, '.godoty', 'context_db')
        self.persist_dir = persist_dir
        
        # Initialize embedding function
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self._embedding_fn = SentenceTransformerEmbedding()
                logger.info("Using sentence-transformers for embeddings")
            except Exception as e:
                logger.warning(f"Failed to load sentence-transformers: {e}, using fallback")
                self._embedding_fn = SimpleHashEmbedding()
        else:
            self._embedding_fn = SimpleHashEmbedding()
            logger.info("Using simple hash embedding (install sentence-transformers for better results)")
        
        # Initialize ChromaDB
        self.client = None
        self.code_collection = None
        self.scene_collection = None
        self.docs_collection = None
        
        if CHROMADB_AVAILABLE:
            self._init_chromadb()
        else:
            logger.warning("ChromaDB not available - vector search disabled")
        
        # Initialize chunkers
        self.code_chunker = GDScriptChunker()
        self.scene_chunker = SceneChunker()
    
    def _init_chromadb(self) -> None:
        """Initialize ChromaDB client and collections."""
        os.makedirs(self.persist_dir, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Create or get collections
        self.code_collection = self.client.get_or_create_collection(
            name="godot_code",
            metadata={"description": "GDScript code chunks"}
        )
        
        self.scene_collection = self.client.get_or_create_collection(
            name="godot_scenes",
            metadata={"description": "Scene descriptions"}
        )
        
        self.docs_collection = self.client.get_or_create_collection(
            name="godot_docs",
            metadata={"description": "Godot documentation"}
        )
        
        logger.info(f"ChromaDB initialized at {self.persist_dir}")
    
    def index_project(self, progress_callback: Optional[Callable[[str, int, int], None]] = None) -> None:
        """
        Index all files in the project.
        
        Args:
            progress_callback: Optional callback(status, current, total)
        """
        if not CHROMADB_AVAILABLE:
            logger.error("Cannot index: ChromaDB not available")
            return
        
        # Clear existing data
        self.code_collection.delete(where={"file_path": {"$ne": ""}})
        self.scene_collection.delete(where={"file_path": {"$ne": ""}})
        
        # Find all files
        gd_files = []
        scene_files = []
        
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      {'__pycache__', 'addons', '.godot', '.import'}]
            
            for file in files:
                file_path = os.path.join(root, file)
                if file.endswith('.gd'):
                    gd_files.append(file_path)
                elif file.endswith('.tscn'):
                    scene_files.append(file_path)
        
        total_files = len(gd_files) + len(scene_files)
        current = 0
        
        # Index GDScript files
        for file_path in gd_files:
            try:
                self._index_script_file(file_path)
            except Exception as e:
                logger.warning(f"Failed to index {file_path}: {e}")
            
            current += 1
            if progress_callback:
                progress_callback(f"Indexing {Path(file_path).name}", current, total_files)
        
        # Index scene files
        for file_path in scene_files:
            try:
                self._index_scene_file(file_path)
            except Exception as e:
                logger.warning(f"Failed to index {file_path}: {e}")
            
            current += 1
            if progress_callback:
                progress_callback(f"Indexing {Path(file_path).name}", current, total_files)
        
        logger.info(f"Indexed {len(gd_files)} scripts and {len(scene_files)} scenes")
    
    def _index_script_file(self, file_path: str) -> None:
        """Index a single GDScript file."""
        content = Path(file_path).read_text(encoding='utf-8')
        res_path = self._to_res_path(file_path)
        
        chunks = self.code_chunker.chunk_script(content, res_path)
        
        if not chunks:
            return
        
        # Prepare batch data
        ids = []
        documents = []
        metadatas = []
        embeddings = []
        
        # Generate embeddings
        texts = [c.docstring or c.content for c in chunks]
        chunk_embeddings = self._embedding_fn(texts)
        
        for chunk, embedding in zip(chunks, chunk_embeddings):
            ids.append(chunk.get_id())
            documents.append(chunk.content)
            metadatas.append({
                "file_path": chunk.file_path,
                "chunk_type": chunk.chunk_type,
                "name": chunk.name or "",
                "class_name": chunk.class_name or "",
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "has_docstring": bool(chunk.docstring)
            })
            embeddings.append(embedding)
        
        # Add to collection
        self.code_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )
    
    def _index_scene_file(self, file_path: str) -> None:
        """Index a single scene file."""
        from .godot_parsers import parse_tscn
        
        res_path = self._to_res_path(file_path)
        
        try:
            scene = parse_tscn(file_path)
            scene_data = {
                'root_type': scene.root_node.type if scene.root_node else 'Node',
                'node_count': len(scene.nodes),
                'nodes': [
                    {
                        'name': n.name,
                        'type': n.type,
                        'path': n.parent + '/' + n.name if n.parent else n.name,
                        'has_script': n.script is not None
                    }
                    for n in scene.nodes
                ]
            }
        except Exception as e:
            logger.warning(f"Failed to parse scene {file_path}: {e}")
            return
        
        chunks = self.scene_chunker.chunk_scene(scene_data, res_path)
        
        if not chunks:
            return
        
        # Prepare batch data
        ids = []
        documents = []
        metadatas = []
        embeddings = []
        
        texts = [c.content for c in chunks]
        chunk_embeddings = self._embedding_fn(texts)
        
        for chunk, embedding in zip(chunks, chunk_embeddings):
            ids.append(chunk.get_id())
            documents.append(chunk.content)
            metadatas.append({
                "file_path": chunk.file_path,
                "chunk_type": chunk.chunk_type,
                "name": chunk.name or "",
                **chunk.metadata
            })
            embeddings.append(embedding)
        
        self.scene_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )
    
    def _to_res_path(self, absolute_path: str) -> str:
        """Convert absolute path to res:// path."""
        try:
            rel = Path(absolute_path).relative_to(self.project_path)
            return f"res://{rel.as_posix()}"
        except ValueError:
            return absolute_path
    
    # =========================================================================
    # Search Methods
    # =========================================================================
    
    def search_code(self, query: str, limit: int = 5,
                   filters: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
        """
        Search GDScript code.
        
        Args:
            query: Search query
            limit: Maximum results
            filters: Optional metadata filters
            
        Returns:
            List of SearchResults
        """
        if not CHROMADB_AVAILABLE or self.code_collection is None:
            return []
        
        # Generate query embedding
        query_embedding = self._embedding_fn([query])[0]
        
        # Build where clause
        where = filters if filters else None
        
        results = self.code_collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        
        return self._format_results(results)
    
    def search_scenes(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Search scene descriptions."""
        if not CHROMADB_AVAILABLE or self.scene_collection is None:
            return []
        
        query_embedding = self._embedding_fn([query])[0]
        
        results = self.scene_collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )
        
        return self._format_results(results)
    
    def search_docs(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Search Godot documentation."""
        if not CHROMADB_AVAILABLE or self.docs_collection is None:
            return []
        
        query_embedding = self._embedding_fn([query])[0]
        
        results = self.docs_collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )
        
        return self._format_results(results)
    
    def search_all(self, query: str, limit: int = 10,
                  filters: Optional[List[str]] = None) -> List[SearchResult]:
        """
        Search across all collections.
        
        Args:
            query: Search query
            limit: Maximum total results
            filters: Optional list of collections to search ["code", "scenes", "docs"]
            
        Returns:
            Combined list of SearchResults sorted by score
        """
        all_results = []
        per_collection = limit // 2 + 1
        
        collections_to_search = filters or ["code", "scenes", "docs"]
        
        if "code" in collections_to_search:
            all_results.extend(self.search_code(query, per_collection))
        
        if "scenes" in collections_to_search:
            all_results.extend(self.search_scenes(query, per_collection))
        
        if "docs" in collections_to_search:
            all_results.extend(self.search_docs(query, per_collection))
        
        # Sort by score (lower distance = better)
        all_results.sort(key=lambda r: r.score)
        
        return all_results[:limit]
    
    def _format_results(self, raw_results: Dict) -> List[SearchResult]:
        """Format ChromaDB results into SearchResults."""
        results = []
        
        if not raw_results.get('documents'):
            return results
        
        documents = raw_results['documents'][0]
        metadatas = raw_results['metadatas'][0]
        distances = raw_results['distances'][0]
        
        for doc, meta, dist in zip(documents, metadatas, distances):
            results.append(SearchResult(
                content=doc,
                file_path=meta.get('file_path', ''),
                chunk_type=meta.get('chunk_type', 'unknown'),
                name=meta.get('name'),
                score=dist,  # Lower is better in ChromaDB
                metadata=meta
            ))
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        if not CHROMADB_AVAILABLE:
            return {"available": False}
        
        return {
            "available": True,
            "code_chunks": self.code_collection.count() if self.code_collection else 0,
            "scene_chunks": self.scene_collection.count() if self.scene_collection else 0,
            "doc_chunks": self.docs_collection.count() if self.docs_collection else 0,
            "persist_dir": self.persist_dir,
            "embedding_type": type(self._embedding_fn).__name__
        }
