"""Godot Documentation Knowledge Base.

Provides vector-indexed Godot documentation for agent retrieval.
Uses LanceDB for local storage and efficient similarity search.
Uses HuggingFace sentence-transformers for local embeddings.
"""

from __future__ import annotations

# Disable tokenizers parallelism warning (must be set before importing tokenizers)
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from agno.knowledge.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb

if TYPE_CHECKING:
    from agno.knowledge.document import Document

logger = logging.getLogger(__name__)

# Default paths
KNOWLEDGE_DIR = Path.home() / ".godoty" / "knowledge"

# Default HuggingFace embedding model
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "GODOTY_EMBEDDING_MODEL",
    "Qwen/Qwen3-Embedding-0.6B"  # Efficient Qwen embedding model (~1.2GB)
)

# Global cache for knowledge instances
_knowledge_cache: dict[str, GodotDocsKnowledge] = {}


def _get_embedder():
    """Get the embedder instance for vector embeddings.
    
    Uses SentenceTransformer from HuggingFace for local embeddings.
    Model is downloaded on first use and cached locally.
    """
    try:
        from agno.knowledge.embedder.sentence_transformer import SentenceTransformerEmbedder
        
        embedder = SentenceTransformerEmbedder(id=DEFAULT_EMBEDDING_MODEL)
        logger.info(f"Using SentenceTransformerEmbedder with model: {DEFAULT_EMBEDDING_MODEL}")
        return embedder
    except Exception as e:
        logger.warning(f"Failed to initialize SentenceTransformerEmbedder: {e}")
        logger.warning("Falling back to default embeddings")
        return None


class GodotDocsKnowledge:
    """Knowledge base for Godot documentation.
    
    Wraps Agno's Knowledge class with LanceDB vector storage,
    providing version-aware documentation indexing and retrieval.
    
    Uses Ollama with Qwen3-Embedding-4B for local embeddings by default.
    
    Example:
        >>> knowledge = GodotDocsKnowledge(version="4.3")
        >>> await knowledge.load()  # Downloads and indexes docs on first run
        >>> results = await knowledge.search("How to use move_and_slide")
    """
    
    def __init__(
        self,
        version: str = "4.5",
        db_path: Path | None = None,
        use_local_embeddings: bool = True,
    ):
        """Initialize the Godot documentation knowledge base.
        
        Args:
            version: Godot version (e.g., "4.3", "4.2")
            db_path: Custom path for LanceDB storage (default: ~/.godoty/knowledge/)
            use_local_embeddings: If True, use Ollama for local embeddings
        """
        self.version = version
        self.db_path = db_path or KNOWLEDGE_DIR
        self.use_local_embeddings = use_local_embeddings
        
        # Ensure directory exists
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Create version-specific table name
        table_name = f"godot_docs_{version.replace('.', '_')}"
        
        # Get embedder (local Ollama or fallback to OpenAI)
        embedder = _get_embedder() if use_local_embeddings else None
        
        # Initialize LanceDB vector store with embedder
        self.vector_db = LanceDb(
            table_name=table_name,
            uri=str(self.db_path),
            embedder=embedder,
        )
        
        # Create Agno Knowledge wrapper
        self.knowledge = Knowledge(vector_db=self.vector_db)
        
        self._loaded = False
        self._indexing = False
        logger.info(f"Initialized GodotDocsKnowledge for version {version}")
    
    @property
    def is_indexing(self) -> bool:
        """Check if documentation is currently being indexed."""
        return self._indexing
    
    @property
    def is_loaded(self) -> bool:
        """Check if documentation has been indexed."""
        return self._loaded
    
    async def is_indexed(self) -> bool:
        """Check if documentation for this version has been indexed in the DB."""
        try:
            count = await self.vector_db.async_get_count()
            return count > 0
        except Exception:
            return False
    
    async def load(
        self,
        force_reload: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
        embedding_callback: Callable[[int, int], None] | None = None,
    ) -> bool:
        """Load Godot documentation into the knowledge base.
        
        Downloads and indexes documentation if not already present.
        
        Args:
            force_reload: If True, re-download and re-index all docs
            progress_callback: Optional callback(current, total) for fetching progress
            embedding_callback: Optional callback(current, total) for embedding progress
            
        Returns:
            True if loading was successful
        """
        # Check if already indexed in database
        if not force_reload and await self.is_indexed():
            self._loaded = True
            logger.info(f"Documentation for Godot {self.version} already indexed")
            return True
        
        if self._indexing:
            logger.warning("Indexing already in progress")
            return False
            
        self._indexing = True
        try:
            # Import loader here to avoid circular imports
            from .godot_docs_loader import GodotDocsLoader
            import hashlib
            
            # If force_reload, delete existing table directory to avoid embedding dimension mismatch
            if force_reload:
                import shutil
                table_name = f"godot_docs_{self.version.replace('.', '_')}"
                table_dir = self.db_path / f"{table_name}.lance"
                if table_dir.exists():
                    try:
                        shutil.rmtree(table_dir)
                        logger.info(f"Deleted existing table directory: {table_dir}")
                    except Exception as e:
                        logger.warning(f"Could not delete table directory: {e}")
            
            loader = GodotDocsLoader(version=self.version, cache_dir=self.db_path / "cache")
            documents = await loader.load_documents(progress_callback=progress_callback)
            
            if documents:
                # Generate content hash for this version
                content_hash = hashlib.md5(f"godot_docs_{self.version}".encode()).hexdigest()
                
                # Insert documents in small batches (3 at a time) to reduce memory pressure
                batch_size = 3
                total_docs = len(documents)
                total_batches = (total_docs + batch_size - 1) // batch_size
                
                for i in range(0, total_docs, batch_size):
                    batch = documents[i:i + batch_size]
                    batch_hash = f"{content_hash}_{i // batch_size}"
                    await self.vector_db.async_insert(batch_hash, batch)
                    
                    # Report embedding progress
                    batch_num = i // batch_size + 1
                    if embedding_callback:
                        try:
                            embedding_callback(batch_num, total_batches)
                        except Exception as e:
                            logger.warning(f"Embedding callback failed: {e}")
                    
                    logger.debug(f"Inserted batch {batch_num}/{total_batches}")
                
                self._loaded = True
                logger.info(f"Indexed {len(documents)} documents for Godot {self.version}")
                return True
            else:
                logger.warning(f"No documents loaded for Godot {self.version}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to load Godot documentation: {e}")
            return False
        finally:
            self._indexing = False
    
    async def search(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[dict]:
        """Search the knowledge base for relevant documentation.
        
        Automatically triggers indexing if docs haven't been loaded yet.
        
        Args:
            query: Natural language search query
            num_results: Maximum number of results to return
            
        Returns:
            List of relevant document chunks with content and metadata
        """
        # Auto-load if not already indexed
        if not await self.is_indexed():
            logger.info(f"Auto-indexing Godot {self.version} documentation...")
            if not await self.load():
                return [{"error": "Failed to index documentation"}]
        
        try:
            results = await self.vector_db.async_search(query, limit=num_results)
            
            return [
                {
                    "content": doc.content,
                    "metadata": doc.meta_data,
                    "name": doc.name,
                }
                for doc in results
            ]
        except Exception as e:
            logger.error(f"Knowledge search failed: {e}")
            return []
    
    def search_sync(self, query: str, num_results: int = 5) -> list[dict]:
        """Synchronous version of search (for non-async contexts)."""
        try:
            results = self.knowledge.search(query, num_documents=num_results)
            
            return [
                {
                    "content": doc.content,
                    "metadata": doc.meta_data,
                    "name": doc.name,
                }
                for doc in results
            ]
        except Exception as e:
            logger.error(f"Knowledge search failed: {e}")
            return []


def get_godot_knowledge(
    version: str = "4.5",
    db_path: Path | None = None,
) -> GodotDocsKnowledge:
    """Get a cached GodotDocsKnowledge instance for the specified version.
    
    Args:
        version: Godot version (e.g., "4.3", "4.2")
        db_path: Custom path for LanceDB storage
        
    Returns:
        GodotDocsKnowledge instance (cached per version)
    """
    cache_key = f"{version}:{db_path or 'default'}"
    
    if cache_key not in _knowledge_cache:
        _knowledge_cache[cache_key] = GodotDocsKnowledge(
            version=version,
            db_path=db_path,
        )
    
    return _knowledge_cache[cache_key]
