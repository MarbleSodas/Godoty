"""
Enhanced Context Engine with Vector Embeddings for Semantic Code Understanding

This module provides advanced RAG capabilities using sentence-transformers and FAISS
for semantic search and code understanding in the Godoty project.
"""

import os
import json
import logging
import pickle
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """Represents a chunk of code with its embedding and metadata"""
    file_path: str
    content: str
    chunk_type: str  # 'function', 'class', 'method', 'comment', 'general'
    start_line: int
    end_line: int
    language: str
    dependencies: List[str]
    embedding: Optional[np.ndarray] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SearchResult:
    """Represents a semantic search result"""
    file_path: str
    content: str
    chunk_type: str
    relevance_score: float
    similarity_score: float
    line_numbers: Tuple[int, int]
    explanation: str
    metadata: Dict[str, Any]


class EnhancedContextEngine:
    """
    Enhanced Context Engine with vector embeddings for semantic code understanding.

    Features:
    - Vector embeddings using sentence-transformers
    - FAISS for fast similarity search
    - Multi-language code support (GDScript, C#, TypeScript, Python)
    - Hierarchical indexing (file + function level)
    - Smart context windows with relevance ranking
    - Incremental updates for file changes
    """

    def __init__(self, project_path: str, cache_dir: str = ".vector_cache"):
        """
        Initialize the Enhanced Context Engine.

        Args:
            project_path: Root path of the Godot project
            cache_dir: Directory to store vector embeddings and index
        """
        self.project_path = Path(project_path)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # Initialize sentence transformer model
        logger.info("Loading sentence transformer model...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.embedding_dim = self.model.get_sentence_embedding_dimension()

        # Initialize FAISS index
        self.index = faiss.IndexFlatL2(self.embedding_dim)

        # Storage for chunks and metadata
        self.chunks: List[CodeChunk] = []
        self.file_embeddings: Dict[str, List[CodeChunk]] = {}
        self.code_index: Dict[str, int] = {}  # Maps chunk hash to index in FAISS

        # Supported file extensions
        self.supported_extensions = {
            '.gd': 'gdscript',
            '.cs': 'csharp',
            '.ts': 'typescript',
            '.py': 'python',
            '.json': 'json',
            '.tscn': 'godot_scene',
            '.tres': 'godot_resource',
            '.cfg': 'config'
        }

        # Validate project (tolerant approach - logs warnings but continues)
        is_valid_godot_project = self._validate_godot_project(self.project_path)
        if not is_valid_godot_project:
            logger.warning(f"Warning: {self.project_path} is not a valid Godot project")
            logger.warning("Context engine will continue with limited functionality")

        # Load existing index if available
        self._load_index()

        # Enhanced initialization log with project validation status
        project_status = "valid Godot project" if is_valid_godot_project else "invalid/non-Godot project"
        logger.info(f"Enhanced Context Engine initialized with {len(self.chunks)} chunks ({project_status})")

    def _validate_godot_project(self, project_path: Path) -> bool:
        """
        Validate that the provided path is a valid Godot project.

        Uses a tolerant approach - logs warnings but continues indexing even for invalid projects.

        Args:
            project_path: Path to validate as a Godot project

        Returns:
            bool: True if valid Godot project, False otherwise
        """
        try:
            # Check for project.godot file
            project_file = project_path / "project.godot"
            if not project_file.exists():
                logger.warning(f"No project.godot file found in {project_path}")
                return False

            # Basic validation of project.godot content
            try:
                content = project_file.read_text(encoding='utf-8')
                if not content.strip():
                    logger.warning(f"Empty project.godot file found in {project_path}")
                    return False

                # Check for basic Godot project file structure
                if not ('application/config' in content or 'config/version' in content or 'config/name' in content):
                    logger.warning(f"Invalid project.godot file format in {project_path}")
                    return False

                logger.info(f"Valid Godot project detected: {project_path}")
                return True

            except Exception as e:
                logger.warning(f"Error reading project.godot file in {project_path}: {e}")
                return False

        except Exception as e:
            logger.warning(f"Error validating Godot project {project_path}: {e}")
            return False

    def _get_file_priority(self, file_path: Path, language: str) -> float:
        """
        Get priority score for files based on Godot relevance.

        Higher priority for Godot-specific files and common directories.

        Args:
            file_path: Path to the file
            language: Detected language of the file

        Returns:
            float: Priority score (0.0 to 1.0)
        """
        priority = 0.5  # Base priority for all files

        # Higher priority for core Godot files
        if file_path.name == "project.godot":
            return 1.0
        elif file_path.suffix == '.gd':
            priority += 0.3
        elif file_path.suffix == '.cs' and language == 'csharp':
            priority += 0.2
        elif file_path.suffix in ['.tscn', '.tres']:
            priority += 0.2
        elif file_path.suffix in ['.json', '.cfg']:
            priority += 0.1

        # Priority for common Godot directories
        path_parts = [part.lower() for part in file_path.parts]
        if any(godot_dir in path_parts for godot_dir in ['scripts', 'scenes', 'resources', 'src', 'addons']):
            priority += 0.1

        # Ensure priority stays within bounds
        return min(priority, 1.0)

    def index_project(self, force_reindex: bool = False) -> None:
        """
        Index the entire project for semantic search.

        Uses tolerant validation approach - continues indexing even for invalid Godot projects
        with appropriate warnings.

        Args:
            force_reindex: Force complete reindexing even if cache exists
        """
        # Validate Godot project (tolerant approach - continues with warnings)
        is_valid_godot_project = self._validate_godot_project(self.project_path)
        if not is_valid_godot_project:
            logger.warning(f"Directory {self.project_path} does not appear to be a valid Godot project")
            logger.warning("Continuing indexing with limited functionality...")

        if not force_reindex and self._is_index_current():
            logger.info("Using existing vector index")
            return

        logger.info("Starting project indexing...")
        self.chunks.clear()
        self.file_embeddings.clear()
        self.code_index.clear()

        # Walk through project directory
        indexed_files = 0
        for file_path in self._walk_project():
            try:
                # Apply file prioritization during indexing
                file_ext = file_path.suffix.lower()
                language = self.supported_extensions.get(file_ext, 'unknown')
                priority = self._get_file_priority(file_path, language)

                # Log priority for debugging
                if priority >= 0.7:  # High priority files
                    logger.debug(f"High priority file: {file_path} (priority: {priority:.2f})")

                self._index_file(file_path)
                indexed_files += 1

            except Exception as e:
                logger.error(f"Error indexing file {file_path}: {e}")

        # Build FAISS index
        if self.chunks:
            self._build_faiss_index()
            self._save_index()

            # Enhanced logging with project validation status
            project_status = "valid Godot project" if is_valid_godot_project else "invalid/non-Godot project"
            logger.info(f"Indexed {len(self.chunks)} code chunks from {indexed_files} files ({project_status})")
        else:
            logger.warning("No code chunks found to index")
            if not is_valid_godot_project:
                logger.warning("This may be due to the directory not being a valid Godot project")

    def semantic_search(self, query: str, limit: int = 10,
                       file_types: Optional[List[str]] = None) -> List[SearchResult]:
        """
        Perform semantic search using vector embeddings.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            file_types: Optional list of file extensions to filter by

        Returns:
            List of search results with relevance scores
        """
        if not self.chunks:
            logger.warning("No indexed chunks available for search")
            return []

        # Generate query embedding
        query_embedding = self.model.encode([query])

        # Search FAISS index
        search_k = min(limit * 2, len(self.chunks))  # Search more than needed for ranking
        distances, indices = self.index.search(query_embedding, search_k)

        # Process and rank results
        results = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx < len(self.chunks):
                chunk = self.chunks[idx]

                # Apply file type filter if specified
                if file_types and Path(chunk.file_path).suffix not in file_types:
                    continue

                # Calculate relevance scores
                similarity_score = 1 - distance
                relevance_score = self._calculate_relevance(query, chunk)

                # Generate explanation
                explanation = self._generate_explanation(query, chunk, similarity_score)

                result = SearchResult(
                    file_path=chunk.file_path,
                    content=chunk.content,
                    chunk_type=chunk.chunk_type,
                    relevance_score=relevance_score,
                    similarity_score=similarity_score,
                    line_numbers=(chunk.start_line, chunk.end_line),
                    explanation=explanation,
                    metadata=chunk.metadata or {}
                )

                results.append(result)

        # Sort by combined relevance score and limit results
        results.sort(key=lambda x: x.similarity_score * x.relevance_score, reverse=True)
        return results[:limit]

    def get_context_for_file(self, file_path: str, window_size: int = 5) -> List[CodeChunk]:
        """
        Get contextual chunks around a specific file.

        Args:
            file_path: Path to the file
            window_size: Number of chunks to include before and after

        Returns:
            List of related code chunks
        """
        file_chunks = self.file_embeddings.get(str(file_path), [])
        if not file_chunks:
            return []

        # TODO: Implement smarter context window based on dependencies
        return file_chunks

    def update_file_index(self, file_path: str) -> None:
        """
        Update the index for a specific file when it changes.

        Args:
            file_path: Path to the modified file
        """
        logger.info(f"Updating index for file: {file_path}")

        # Remove existing chunks for this file
        self._remove_file_chunks(file_path)

        # Re-index the file
        self._index_file(file_path)

        # Rebuild FAISS index
        self._build_faiss_index()

        # Save updated index
        self._save_index()

    def _walk_project(self) -> List[Path]:
        """Walk through project directory and return supported files."""
        files = []

        # Skip common directories that don't need indexing
        skip_dirs = {
            '.git', '.github', 'node_modules', '__pycache__', '.pytest_cache',
            '.venv', 'venv', 'env', 'dist', 'build', '.godoty'
        }

        for file_path in self.project_path.rglob('*'):
            if file_path.is_file() and file_path.suffix in self.supported_extensions:
                # Skip files in ignored directories
                if any(skip_dir in file_path.parts for skip_dir in skip_dirs):
                    continue
                files.append(file_path)

        return files

    def _index_file(self, file_path: Path) -> None:
        """Index a single file and create code chunks."""
        try:
            content = file_path.read_text(encoding='utf-8')
            language = self.supported_extensions.get(file_path.suffix, 'text')

            # Create code chunks based on language
            chunks = self._chunk_code(content, str(file_path), language)

            # Store chunks
            self.file_embeddings[str(file_path)] = chunks
            self.chunks.extend(chunks)

            logger.debug(f"Indexed {len(chunks)} chunks from {file_path}")

        except Exception as e:
            logger.error(f"Failed to index file {file_path}: {e}")

    def _chunk_code(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """
        Chunk code into semantically meaningful segments.

        Args:
            content: File content
            file_path: Path to the file
            language: Programming language

        Returns:
            List of code chunks
        """
        chunks = []
        lines = content.split('\n')

        if language == 'gdscript':
            chunks.extend(self._chunk_gdscript(lines, file_path))
        elif language == 'csharp':
            chunks.extend(self._chunk_csharp(lines, file_path))
        elif language == 'python':
            chunks.extend(self._chunk_python(lines, file_path))
        elif language in ['json', 'godot_scene', 'godot_resource', 'config']:
            chunks.extend(self._chunk_structured_data(content, file_path, language))
        else:
            # Generic text chunking
            chunks.extend(self._chunk_generic_text(lines, file_path, language))

        return chunks

    def _chunk_gdscript(self, lines: List[str], file_path: str) -> List[CodeChunk]:
        """Chunk GDScript code into functions, classes, and methods."""
        chunks = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                i += 1
                continue

            # Function or method definition
            if line.startswith('func '):
                chunk_lines = [line]
                start_line = i + 1
                i += 1

                # Collect function body
                indent_level = len(lines[i-1]) - len(lines[i-1].lstrip()) if i < len(lines) else 0

                while i < len(lines):
                    current_line = lines[i]

                    # Stop if we reach same or lower indentation level
                    if current_line.strip() and len(current_line) - len(current_line.lstrip()) <= indent_level:
                        if not current_line.strip().startswith('#'):  # Allow comments at any level
                            break

                    chunk_lines.append(current_line)
                    i += 1

                content = '\n'.join(chunk_lines)
                chunks.append(CodeChunk(
                    file_path=file_path,
                    content=content,
                    chunk_type='function',
                    start_line=start_line,
                    end_line=i,
                    language='gdscript',
                    dependencies=self._extract_dependencies(content)
                ))

            # Class definition
            elif line.startswith('class '):
                chunk_lines = [line]
                start_line = i + 1
                i += 1

                # Collect class body
                while i < len(lines) and not (lines[i].strip() and lines[i].strip().startswith(('class ', 'func '))):
                    chunk_lines.append(lines[i])
                    i += 1

                content = '\n'.join(chunk_lines)
                chunks.append(CodeChunk(
                    file_path=file_path,
                    content=content,
                    chunk_type='class',
                    start_line=start_line,
                    end_line=i,
                    language='gdscript',
                    dependencies=self._extract_dependencies(content)
                ))

            # Variable declarations or other statements
            else:
                # Create small chunks for other statements
                chunk_content = line
                start_line = i + 1
                i += 1

                # Collect related lines (same indentation level)
                current_indent = len(line) - len(line.lstrip()) if line else 0

                while i < len(lines):
                    next_line = lines[i].strip()
                    if next_line and len(lines[i]) - len(lines[i].lstrip()) == current_indent:
                        chunk_content += '\n' + lines[i]
                        i += 1
                    else:
                        break

                chunks.append(CodeChunk(
                    file_path=file_path,
                    content=chunk_content,
                    chunk_type='statement',
                    start_line=start_line,
                    end_line=i,
                    language='gdscript',
                    dependencies=self._extract_dependencies(chunk_content)
                ))

        return chunks

    def _chunk_csharp(self, lines: List[str], file_path: str) -> List[CodeChunk]:
        """Chunk C# code into classes, methods, and properties."""
        # TODO: Implement proper C# chunking
        # For now, use generic text chunking
        return self._chunk_generic_text(lines, file_path, 'csharp')

    def _chunk_python(self, lines: List[str], file_path: str) -> List[CodeChunk]:
        """Chunk Python code into functions, classes, and methods."""
        chunks = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Function definition
            if line.startswith('def ') or line.startswith('async def '):
                chunk_lines = [line]
                start_line = i + 1
                i += 1

                # Collect function body
                indent_level = len(lines[i-1]) - len(lines[i-1].lstrip()) if i < len(lines) else 0

                while i < len(lines):
                    current_line = lines[i]
                    if current_line.strip() and len(current_line) - len(current_line.lstrip()) <= indent_level:
                        break
                    chunk_lines.append(current_line)
                    i += 1

                content = '\n'.join(chunk_lines)
                chunks.append(CodeChunk(
                    file_path=file_path,
                    content=content,
                    chunk_type='function',
                    start_line=start_line,
                    end_line=i,
                    language='python',
                    dependencies=self._extract_dependencies(content)
                ))

            # Class definition
            elif line.startswith('class '):
                chunk_lines = [line]
                start_line = i + 1
                i += 1

                while i < len(lines) and not (lines[i].strip() and lines[i].strip().startswith(('class ', 'def ', 'async def '))):
                    chunk_lines.append(lines[i])
                    i += 1

                content = '\n'.join(chunk_lines)
                chunks.append(CodeChunk(
                    file_path=file_path,
                    content=content,
                    chunk_type='class',
                    start_line=start_line,
                    end_line=i,
                    language='python',
                    dependencies=self._extract_dependencies(content)
                ))

            else:
                i += 1

        return chunks if chunks else self._chunk_generic_text(lines, file_path, 'python')

    def _chunk_structured_data(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """Chunk structured data files (JSON, scenes, resources)."""
        chunks = []

        # For structured data, create meaningful chunks
        if language in ['godot_scene', 'godot_resource']:
            # Parse Godot scene/resource structure
            lines = content.split('\n')
            current_chunk = []
            current_section = None
            start_line = 1

            for i, line in enumerate(lines):
                stripped = line.strip()

                # New section
                if stripped.startswith('[') and stripped.endswith(']'):
                    if current_chunk:
                        chunks.append(CodeChunk(
                            file_path=file_path,
                            content='\n'.join(current_chunk),
                            chunk_type='section',
                            start_line=start_line,
                            end_line=i + 1,
                            language=language,
                            dependencies=[]
                        ))

                    current_chunk = [line]
                    current_section = stripped[1:-1]
                    start_line = i + 1
                else:
                    current_chunk.append(line)

            # Add final chunk
            if current_chunk:
                chunks.append(CodeChunk(
                    file_path=file_path,
                    content='\n'.join(current_chunk),
                    chunk_type='section',
                    start_line=start_line,
                    end_line=len(lines),
                    language=language,
                    dependencies=[]
                ))
        else:
            # Generic structured data chunking
            chunks.append(CodeChunk(
                file_path=file_path,
                content=content,
                chunk_type='file',
                start_line=1,
                end_line=len(content.split('\n')),
                language=language,
                dependencies=[]
            ))

        return chunks

    def _chunk_generic_text(self, lines: List[str], file_path: str, language: str) -> List[CodeChunk]:
        """Generic text chunking for unsupported languages."""
        chunks = []
        chunk_size = 20  # lines per chunk
        overlap = 3

        for i in range(0, len(lines), chunk_size - overlap):
            chunk_lines = lines[i:i + chunk_size]
            content = '\n'.join(chunk_lines)

            chunks.append(CodeChunk(
                file_path=file_path,
                content=content,
                chunk_type='general',
                start_line=i + 1,
                end_line=min(i + chunk_size, len(lines)),
                language=language,
                dependencies=[]
            ))

        return chunks

    def _extract_dependencies(self, content: str) -> List[str]:
        """Extract dependencies from code chunk."""
        dependencies = []

        # Simple dependency extraction - can be enhanced
        if 'extends ' in content:
            extends_match = [line for line in content.split('\n') if 'extends ' in line]
            dependencies.extend([line.split('extends ')[1].strip() for line in extends_match])

        if 'import ' in content:
            import_matches = [line for line in content.split('\n') if 'import ' in line]
            dependencies.extend([line.split('import ')[1].strip() for line in import_matches])

        if 'from ' in content:
            from_matches = [line for line in content.split('\n') if 'from ' in line and ' import ' in line]
            dependencies.extend([line.split(' from ')[1].split(' import ')[0].strip() for line in from_matches])

        return dependencies

    def _build_faiss_index(self) -> None:
        """Build FAISS index from all chunks."""
        if not self.chunks:
            return

        logger.info("Building FAISS index...")

        # Generate embeddings for all chunks
        embeddings = []
        for chunk in self.chunks:
            # Use content for embedding, but limit size to avoid memory issues
            text_for_embedding = chunk.content[:1000]  # Limit to first 1000 characters
            embedding = self.model.encode([text_for_embedding])[0]
            chunk.embedding = embedding
            embeddings.append(embedding)

        # Create numpy array
        embeddings_array = np.array(embeddings).astype('float32')

        # Create new FAISS index
        self.index = faiss.IndexFlatL2(self.embedding_dim)
        self.index.add(embeddings_array)

        # Update code index mapping
        self.code_index = {
            hashlib.md5(chunk.content.encode()).hexdigest(): i
            for i, chunk in enumerate(self.chunks)
        }

        logger.info(f"Built FAISS index with {len(self.chunks)} embeddings")

    def _calculate_relevance(self, query: str, chunk: CodeChunk) -> float:
        """Calculate relevance score for query and chunk."""
        # Simple relevance scoring - can be enhanced
        relevance = 0.5  # Base score

        # Boost score based on chunk type
        if chunk.chunk_type in ['function', 'class', 'method']:
            relevance += 0.3
        elif chunk.chunk_type == 'section':
            relevance += 0.1

        # Boost score for specific keywords
        query_lower = query.lower()
        content_lower = chunk.content.lower()

        # Common Godot keywords
        godot_keywords = ['node', 'scene', 'script', 'signal', 'func', 'class', 'extends', 'var']
        keyword_matches = sum(1 for keyword in godot_keywords if keyword in query_lower and keyword in content_lower)
        relevance += min(keyword_matches * 0.1, 0.2)

        return min(relevance, 1.0)

    def _generate_explanation(self, query: str, chunk: CodeChunk, similarity_score: float) -> str:
        """Generate explanation for why this chunk matches the query."""
        if similarity_score > 0.8:
            relevance_level = "Highly relevant"
        elif similarity_score > 0.6:
            relevance_level = "Relevant"
        elif similarity_score > 0.4:
            relevance_level = "Somewhat relevant"
        else:
            relevance_level = "Potentially relevant"

        explanation = f"{relevance_level} {chunk.chunk_type}"

        if chunk.chunk_type in ['function', 'class', 'method']:
            # Try to extract name
            first_line = chunk.content.split('\n')[0].strip()
            if 'func ' in first_line:
                func_name = first_line.split('func ')[1].split('(')[0].strip()
                explanation += f": {func_name}"
            elif 'class ' in first_line:
                class_name = first_line.split('class ')[1].split(':')[0].strip()
                explanation += f": {class_name}"
            elif 'def ' in first_line:
                func_name = first_line.split('def ')[1].split('(')[0].strip()
                explanation += f": {func_name}"

        return explanation

    def _remove_file_chunks(self, file_path: str) -> None:
        """Remove all chunks for a specific file."""
        if str(file_path) in self.file_embeddings:
            del self.file_embeddings[str(file_path)]

        # Filter out chunks from this file
        self.chunks = [chunk for chunk in self.chunks if chunk.file_path != str(file_path)]

    def _is_index_current(self) -> bool:
        """Check if the current index is up-to-date."""
        index_file = self.cache_dir / "index.pkl"
        metadata_file = self.cache_dir / "metadata.json"

        if not index_file.exists() or not metadata_file.exists():
            return False

        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            # Check if project was modified after index was created
            index_time = datetime.fromisoformat(metadata.get('indexed_at', '1970-01-01'))

            # Check modification times (simplified)
            for file_path in self._walk_project():
                if file_path.stat().st_mtime > index_time.timestamp():
                    return False

            return True
        except Exception as e:
            logger.error(f"Error checking index currency: {e}")
            return False

    def _save_index(self) -> None:
        """Save FAISS index and metadata."""
        try:
            # Save FAISS index
            index_file = self.cache_dir / "faiss.index"
            faiss.write_index(self.index, str(index_file))

            # Save chunks
            chunks_file = self.cache_dir / "chunks.pkl"
            with open(chunks_file, 'wb') as f:
                pickle.dump(self.chunks, f)

            # Save file embeddings mapping
            mapping_file = self.cache_dir / "file_mapping.pkl"
            with open(mapping_file, 'wb') as f:
                pickle.dump(self.file_embeddings, f)

            # Save metadata
            metadata = {
                'indexed_at': datetime.now().isoformat(),
                'total_chunks': len(self.chunks),
                'total_files': len(self.file_embeddings),
                'embedding_dim': self.embedding_dim
            }

            metadata_file = self.cache_dir / "metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info("Saved vector index and metadata")

        except Exception as e:
            logger.error(f"Error saving index: {e}")

    def _load_index(self) -> None:
        """Load FAISS index and metadata if available."""
        try:
            index_file = self.cache_dir / "faiss.index"
            chunks_file = self.cache_dir / "chunks.pkl"
            mapping_file = self.cache_dir / "file_mapping.pkl"
            metadata_file = self.cache_dir / "metadata.json"

            if all(f.exists() for f in [index_file, chunks_file, mapping_file, metadata_file]):
                # Load FAISS index
                self.index = faiss.read_index(str(index_file))

                # Load chunks
                with open(chunks_file, 'rb') as f:
                    self.chunks = pickle.load(f)

                # Load file mapping
                with open(mapping_file, 'rb') as f:
                    self.file_embeddings = pickle.load(f)

                # Load metadata
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                # Rebuild code index
                self.code_index = {
                    hashlib.md5(chunk.content.encode()).hexdigest(): i
                    for i, chunk in enumerate(self.chunks)
                }

                logger.info(f"Loaded vector index with {len(self.chunks)} chunks from {len(self.file_embeddings)} files")

        except Exception as e:
            logger.error(f"Error loading index: {e}")
            # Start with empty index if loading fails
            self.chunks = []
            self.file_embeddings = {}
            self.code_index = {}
            self.index = faiss.IndexFlatL2(self.embedding_dim)


# Utility function to create and configure the engine
def create_context_engine(project_path: str, cache_dir: str = ".vector_cache") -> EnhancedContextEngine:
    """
    Create and configure an Enhanced Context Engine.

    Args:
        project_path: Root path of the Godot project
        cache_dir: Directory to store vector embeddings

    Returns:
        Configured EnhancedContextEngine instance
    """
    engine = EnhancedContextEngine(project_path, cache_dir)

    # Index the project on first use
    engine.index_project()

    return engine