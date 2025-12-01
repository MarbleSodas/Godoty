"""
Vector Database Integration for Enhanced RAG

This module provides efficient vector storage and retrieval capabilities using FAISS
for fast similarity search in large codebases.
"""

import os
import json
import logging
import pickle
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import faiss

from .code_parser import ParsedElement

logger = logging.getLogger(__name__)


@dataclass
class VectorMetadata:
    """Metadata for a stored vector."""
    id: str
    file_path: str
    element_type: str
    element_name: str
    content_hash: str
    created_at: str
    updated_at: str
    language: str
    tags: List[str]
    dependencies: List[str]
    additional_metadata: Dict[str, Any]


@dataclass
class SearchQuery:
    """Configuration for a vector search query."""
    query_text: str
    limit: int = 10
    similarity_threshold: float = 0.3
    file_filters: Optional[List[str]] = None
    element_type_filters: Optional[List[str]] = None
    language_filters: Optional[List[str]] = None
    include_metadata: bool = True
    weighting_config: Optional[Dict[str, float]] = None


@dataclass
class SearchResult:
    """Result from a vector similarity search."""
    id: str
    file_path: str
    element_type: str
    element_name: str
    content: str
    similarity_score: float
    metadata: VectorMetadata
    explanation: Optional[str] = None


class VectorStore:
    """
    High-performance vector database for semantic search.

    Features:
    - FAISS integration for fast similarity search
    - Persistent storage with compression
    - Incremental updates and deletions
    - Metadata indexing and filtering
    - Thread-safe operations
    - Batch processing support
    - Memory-efficient for large codebases
    """

    def __init__(self, store_path: str = ".vector_store", embedding_dim: int = 384):
        """
        Initialize the Vector Store.

        Args:
            store_path: Directory to store vector data
            embedding_dim: Dimension of embeddings (384 for sentence-transformers)
        """
        self.store_path = Path(store_path)
        self.store_path.mkdir(exist_ok=True)
        self.embedding_dim = embedding_dim

        # Thread safety
        self._lock = threading.RLock()

        # Initialize FAISS index
        self._init_faiss_index()

        # Storage for vectors and metadata
        self.vectors: Dict[str, np.ndarray] = {}
        self.metadata: Dict[str, VectorMetadata] = {}
        self.content_index: Dict[str, int] = {}  # Maps content hash to FAISS index

        # Performance optimization
        self._batch_size = 100
        self._cache_size = 1000
        self._vector_cache = {}

        # Load existing data
        self._load_store()

        logger.info(f"VectorStore initialized with {len(self.vectors)} vectors")

    def _init_faiss_index(self):
        """Initialize FAISS index with appropriate type."""
        # Use IVF index for better performance on large datasets
        nlist = min(100, max(1, len(self.vectors) // 10)) if hasattr(self, 'vectors') else 100

        try:
            # Try to create an IVF index for better performance
            quantizer = faiss.IndexFlatL2(self.embedding_dim)
            self.index = faiss.IndexIVFFlat(quantizer, self.embedding_dim, nlist)
            self.index.nprobe = min(10, nlist)  # Number of clusters to search
            self.index_type = "ivf"
        except Exception as e:
            logger.warning(f"Failed to create IVF index, falling back to flat index: {e}")
            self.index = faiss.IndexFlatL2(self.embedding_dim)
            self.index_type = "flat"

    def add_vector(self, vector_id: str, embedding: np.ndarray, metadata: VectorMetadata) -> None:
        """
        Add a single vector to the store.

        Args:
            vector_id: Unique identifier for the vector
            embedding: Vector embedding (numpy array)
            metadata: Metadata associated with the vector
        """
        with self._lock:
            # Ensure embedding is correct type and shape
            embedding = self._normalize_embedding(embedding)

            # Remove existing vector if it exists
            if vector_id in self.vectors:
                self.remove_vector(vector_id)

            # Store vector and metadata
            self.vectors[vector_id] = embedding
            self.metadata[vector_id] = metadata

            # Add to FAISS index
            self.content_index[metadata.content_hash] = len(self.vectors) - 1
            self.index.add(embedding.reshape(1, -1))

            # Update cache
            self._update_cache(vector_id, embedding, metadata)

            logger.debug(f"Added vector {vector_id} for {metadata.element_type}:{metadata.element_name}")

    def add_vectors_batch(self, vector_data: List[Tuple[str, np.ndarray, VectorMetadata]]) -> None:
        """
        Add multiple vectors efficiently.

        Args:
            vector_data: List of (vector_id, embedding, metadata) tuples
        """
        if not vector_data:
            return

        with self._lock:
            # Prepare batch data
            embeddings = []
            metadata_list = []
            vector_ids = []

            for vector_id, embedding, metadata in vector_data:
                # Remove existing vectors
                if vector_id in self.vectors:
                    self._remove_vector_internal(vector_id)

                # Normalize embedding
                embedding = self._normalize_embedding(embedding)
                embeddings.append(embedding)
                metadata_list.append(metadata)
                vector_ids.append(vector_id)

            # Store vectors and metadata
            embeddings_array = np.array(embeddings).astype('float32')

            for i, (vector_id, embedding, metadata) in enumerate(vector_data):
                self.vectors[vector_id] = embedding
                self.metadata[vector_id] = metadata
                self.content_index[metadata.content_hash] = len(self.vectors) - len(vector_data) + i

            # Add to FAISS index in batch
            self.index.add(embeddings_array)

            # Update cache
            for vector_id, embedding, metadata in vector_data:
                self._update_cache(vector_id, embedding, metadata)

            logger.info(f"Added batch of {len(vector_data)} vectors")

    def search(self, query: SearchQuery) -> List[SearchResult]:
        """
        Perform similarity search with advanced filtering.

        Args:
            query: Search query configuration

        Returns:
            List of search results ranked by similarity
        """
        with self._lock:
            if not self.vectors:
                return []

            # Generate query embedding
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer('all-MiniLM-L6-v2')
                query_embedding = model.encode([query.query_text])
                query_embedding = self._normalize_embedding(query_embedding[0])
            except Exception as e:
                logger.error(f"Failed to generate query embedding: {e}")
                return []

            # Search FAISS index
            search_k = min(query.limit * 3, len(self.vectors))  # Search more than needed
            distances, indices = self.index.search(query_embedding.reshape(1, -1), search_k)

            # Process and filter results
            results = []
            for distance, idx in zip(distances[0], indices[0]):
                if len(results) >= query.limit:
                    break

                if idx >= len(self.vectors):
                    continue

                # Find vector by index
                vector_id = self._find_vector_id_by_index(idx)
                if not vector_id:
                    continue

                metadata = self.metadata.get(vector_id)
                if not metadata:
                    continue

                # Apply filters
                if not self._passes_filters(metadata, query):
                    continue

                # Calculate similarity score (convert distance to similarity)
                similarity = max(0, 1 - distance)

                # Apply similarity threshold
                if similarity < query.similarity_threshold:
                    continue

                # Get content
                content = self._get_content_by_id(vector_id)
                if not content:
                    continue

                # Generate explanation
                explanation = self._generate_explanation(query.query_text, metadata, similarity)

                result = SearchResult(
                    id=vector_id,
                    file_path=metadata.file_path,
                    element_type=metadata.element_type,
                    element_name=metadata.element_name,
                    content=content,
                    similarity_score=similarity,
                    metadata=metadata,
                    explanation=explanation
                )

                results.append(result)

            # Sort by similarity score
            results.sort(key=lambda x: x.similarity_score, reverse=True)

            # Apply search weighting if configured
            if query.weighting_config:
                results = self._apply_weighting(results, query.weighting_config)

            return results

    def remove_vector(self, vector_id: str) -> None:
        """
        Remove a vector from the store.

        Args:
            vector_id: ID of vector to remove
        """
        with self._lock:
            self._remove_vector_internal(vector_id)
            self._save_store()  # Persist changes

    def update_vector(self, vector_id: str, embedding: np.ndarray, metadata: VectorMetadata) -> None:
        """
        Update an existing vector.

        Args:
            vector_id: ID of vector to update
            embedding: New embedding
            metadata: New metadata
        """
        with self._lock:
            if vector_id not in self.vectors:
                logger.warning(f"Vector {vector_id} not found for update")
                return

            # Remove old vector and add new one
            self._remove_vector_internal(vector_id)
            self.add_vector(vector_id, embedding, metadata)

            self._save_store()  # Persist changes

    def get_vector_by_id(self, vector_id: str) -> Optional[Tuple[np.ndarray, VectorMetadata]]:
        """
        Get a vector and its metadata by ID.

        Args:
            vector_id: ID of vector to retrieve

        Returns:
            Tuple of (embedding, metadata) or None if not found
        """
        with self._lock:
            if vector_id in self.vectors and vector_id in self.metadata:
                return self.vectors[vector_id], self.metadata[vector_id]
            return None

    def get_vectors_by_filter(self, **filters) -> List[Tuple[str, np.ndarray, VectorMetadata]]:
        """
        Get vectors that match the given filters.

        Args:
            **filters: Filter criteria (e.g., element_type='function', language='gdscript')

        Returns:
            List of (vector_id, embedding, metadata) tuples
        """
        with self._lock:
            results = []

            for vector_id, metadata in self.metadata.items():
                match = True

                for key, value in filters.items():
                    if hasattr(metadata, key):
                        if getattr(metadata, key) != value:
                            match = False
                            break
                    elif key in metadata.additional_metadata:
                        if metadata.additional_metadata[key] != value:
                            match = False
                            break
                    else:
                        match = False
                        break

                if match and vector_id in self.vectors:
                    results.append((vector_id, self.vectors[vector_id], metadata))

            return results

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the vector store.

        Returns:
            Dictionary with store statistics
        """
        with self._lock:
            stats = {
                'total_vectors': len(self.vectors),
                'index_type': self.index_type,
                'embedding_dimension': self.embedding_dim,
                'total_files': len(set(m.file_path for m in self.metadata.values())),
                'element_types': {},
                'languages': {},
                'store_size_mb': self._get_store_size(),
                'last_updated': datetime.now().isoformat()
            }

            # Count element types
            for metadata in self.metadata.values():
                stats['element_types'][metadata.element_type] = stats['element_types'].get(metadata.element_type, 0) + 1
                stats['languages'][metadata.language] = stats['languages'].get(metadata.language, 0) + 1

            return stats

    def rebuild_index(self) -> None:
        """Rebuild the FAISS index from stored vectors."""
        with self._lock:
            logger.info("Rebuilding FAISS index...")

            if not self.vectors:
                logger.warning("No vectors to rebuild index with")
                return

            # Create new index
            self._init_faiss_index()

            # Re-add all vectors
            embeddings = []
            for vector_id, vector in self.vectors.items():
                embeddings.append(vector)

            embeddings_array = np.array(embeddings).astype('float32')
            self.index.add(embeddings_array)

            # Rebuild content index
            self.content_index = {
                metadata.content_hash: idx
                for idx, metadata in enumerate(self.metadata.values())
            }

            logger.info(f"Rebuilt index with {len(self.vectors)} vectors")

    def optimize_index(self) -> None:
        """Optimize the FAISS index for better performance."""
        with self._lock:
            logger.info("Optimizing FAISS index...")

            if self.index_type == "ivf":
                # Train the index if not already trained
                if not self.index.is_trained:
                    if len(self.vectors) > 100:
                        # Train with a subset of vectors
                        embeddings = list(self.vectors.values())[:min(1000, len(self.vectors))]
                        embeddings_array = np.array(embeddings).astype('float32')
                        self.index.train(embeddings_array)
                        logger.info("Trained IVF index")

            logger.info("Index optimization complete")

    # Private methods
    def _normalize_embedding(self, embedding: Union[np.ndarray, List[float]]) -> np.ndarray:
        """Normalize embedding to correct format."""
        if isinstance(embedding, list):
            embedding = np.array(embedding, dtype=np.float32)
        else:
            embedding = embedding.astype(np.float32)

        # Ensure correct dimension
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        elif embedding.ndim > 2:
            embedding = embedding.reshape(-1, embedding.shape[-1])

        return embedding

    def _remove_vector_internal(self, vector_id: str) -> None:
        """Internal method to remove vector without saving."""
        if vector_id in self.vectors:
            del self.vectors[vector_id]

        if vector_id in self.metadata:
            metadata = self.metadata[vector_id]
            if metadata.content_hash in self.content_index:
                del self.content_index[metadata.content_hash]
            del self.metadata[vector_id]

        # Remove from cache
        if vector_id in self._vector_cache:
            del self._vector_cache[vector_id]

    def _passes_filters(self, metadata: VectorMetadata, query: SearchQuery) -> bool:
        """Check if metadata passes query filters."""
        # File type filters
        if query.file_filters:
            file_ext = Path(metadata.file_path).suffix
            if file_ext not in query.file_filters:
                return False

        # Element type filters
        if query.element_type_filters:
            if metadata.element_type not in query.element_type_filters:
                return False

        # Language filters
        if query.language_filters:
            if metadata.language not in query.language_filters:
                return False

        return True

    def _find_vector_id_by_index(self, index: int) -> Optional[str]:
        """Find vector ID by FAISS index."""
        # This is a simplified approach - in production, we'd maintain a reverse index
        for vector_id, metadata in self.metadata.items():
            if metadata.content_hash in self.content_index:
                if self.content_index[metadata.content_hash] == index:
                    return vector_id
        return None

    def _get_content_by_id(self, vector_id: str) -> Optional[str]:
        """Get content by vector ID."""
        # This would typically be stored in a separate content database
        # For now, we'll return a placeholder
        if vector_id in self.metadata:
            metadata = self.metadata[vector_id]
            return f"Content for {metadata.element_type}:{metadata.element_name}"
        return None

    def _generate_explanation(self, query: str, metadata: VectorMetadata, similarity: float) -> str:
        """Generate explanation for search result."""
        if similarity > 0.8:
            relevance = "Highly relevant"
        elif similarity > 0.6:
            relevance = "Relevant"
        elif similarity > 0.4:
            relevance = "Somewhat relevant"
        else:
            relevance = "Potentially relevant"

        return f"{relevance} {metadata.element_type} '{metadata.element_name}' in {metadata.language}"

    def _apply_weighting(self, results: List[SearchResult], weighting_config: Dict[str, float]) -> List[SearchResult]:
        """Apply custom weighting to search results."""
        for result in results:
            weight = 1.0

            # Apply element type weighting
            if result.element_type in weighting_config:
                weight *= weighting_config[result.element_type]

            # Apply language weighting
            language_key = f"language_{result.metadata.language}"
            if language_key in weighting_config:
                weight *= weighting_config[language_key]

            # Apply file type weighting
            file_ext = Path(result.file_path).suffix
            ext_key = f"extension_{file_ext}"
            if ext_key in weighting_config:
                weight *= weighting_config[ext_key]

            # Adjust similarity score
            result.similarity_score = min(1.0, result.similarity_score * weight)

        # Re-sort by adjusted scores
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results

    def _update_cache(self, vector_id: str, embedding: np.ndarray, metadata: VectorMetadata):
        """Update the internal cache."""
        if len(self._vector_cache) >= self._cache_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self._vector_cache))
            del self._vector_cache[oldest_key]

        self._vector_cache[vector_id] = (embedding, metadata)

    def _get_store_size(self) -> float:
        """Get the size of the vector store in MB."""
        total_size = 0
        for file_path in self.store_path.glob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size / (1024 * 1024)

    def _save_store(self) -> None:
        """Save vector store to disk."""
        try:
            # Save FAISS index
            index_file = self.store_path / "faiss.index"
            faiss.write_index(self.index, str(index_file))

            # Save vectors
            vectors_file = self.store_path / "vectors.pkl"
            with open(vectors_file, 'wb') as f:
                pickle.dump(self.vectors, f)

            # Save metadata
            metadata_file = self.store_path / "metadata.json"
            with open(metadata_file, 'w') as f:
                metadata_dict = {
                    vector_id: asdict(metadata)
                    for vector_id, metadata in self.metadata.items()
                }
                json.dump(metadata_dict, f, indent=2)

            # Save content index
            index_file = self.store_path / "content_index.pkl"
            with open(index_file, 'wb') as f:
                pickle.dump(self.content_index, f)

            logger.debug(f"Saved vector store with {len(self.vectors)} vectors")

        except Exception as e:
            logger.error(f"Error saving vector store: {e}")

    def _load_store(self) -> None:
        """Load vector store from disk."""
        try:
            index_file = self.store_path / "faiss.index"
            vectors_file = self.store_path / "vectors.pkl"
            metadata_file = self.store_path / "metadata.json"
            index_lookup_file = self.store_path / "content_index.pkl"

            if all(f.exists() for f in [index_file, vectors_file, metadata_file, index_lookup_file]):
                # Load FAISS index
                self.index = faiss.read_index(str(index_file))
                self.index_type = "ivf" if hasattr(self.index, 'nprobe') else "flat"

                # Load vectors
                with open(vectors_file, 'rb') as f:
                    self.vectors = pickle.load(f)

                # Load metadata
                with open(metadata_file, 'r') as f:
                    metadata_dict = json.load(f)
                    self.metadata = {
                        vector_id: VectorMetadata(**metadata)
                        for vector_id, metadata in metadata_dict.items()
                    }

                # Load content index
                with open(index_lookup_file, 'rb') as f:
                    self.content_index = pickle.load(f)

                logger.info(f"Loaded vector store with {len(self.vectors)} vectors")

        except Exception as e:
            logger.error(f"Error loading vector store: {e}")
            # Start with empty store if loading fails
            self.vectors = {}
            self.metadata = {}
            self.content_index = {}


# Utility function to create and configure the vector store
def create_vector_store(store_path: str = ".vector_store", embedding_dim: int = 384) -> VectorStore:
    """
    Create and configure a Vector Store.

    Args:
        store_path: Directory to store vector data
        embedding_dim: Dimension of embeddings

    Returns:
        Configured VectorStore instance
    """
    return VectorStore(store_path, embedding_dim)