"""Enhanced Godot Knowledge Base with multi-source support.

Extends the base GodotDocsKnowledge with:
1. GDScript language reference classes
2. Curated community tutorials
3. Hybrid search for better retrieval
4. Version-aware content management

Based on BMAD methodology for context-engineered development.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from agno.knowledge.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb, SearchType

from .godot_knowledge import KNOWLEDGE_DIR, _get_embedder
from .godot_docs_loader import (
    GodotDocsLoader,
    PRIORITY_CLASSES,
    GDSCRIPT_REFERENCE_CLASSES,
    get_tutorials_for_version,
)

if TYPE_CHECKING:
    from agno.knowledge.document import Document

logger = logging.getLogger(__name__)


class EnhancedGodotKnowledge:
    """Extended knowledge base combining multiple Godot documentation sources.
    
    Provides unified search across:
    1. Official Class Reference (nodes, resources, types)
    2. GDScript Language Reference (@GDScript, @GlobalScope, primitives)
    3. Curated Community Tutorials (style guides, patterns, best practices)
    
    All sources are version-aware and use hybrid search (semantic + keyword).
    
    Example:
        >>> knowledge = EnhancedGodotKnowledge(version="4.3")
        >>> await knowledge.load()
        >>> results = await knowledge.search("How to use signals with emit")
    """
    
    def __init__(
        self,
        version: str = "4.5",
        db_path: Path | None = None,
        use_hybrid_search: bool = True,
    ):
        """Initialize the enhanced knowledge base.
        
        Args:
            version: Godot version (e.g., "4.3", "4.2")
            db_path: Custom path for LanceDB storage (default: ~/.godoty/knowledge/)
            use_hybrid_search: If True, use hybrid search (semantic + keyword)
        """
        self.version = version
        self.db_path = db_path or KNOWLEDGE_DIR
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Create version-specific table name
        table_name = f"godot_enhanced_{version.replace('.', '_')}"
        
        # Get embedder for vector embeddings
        embedder = _get_embedder()
        
        # Configure search type
        search_type = SearchType.hybrid if use_hybrid_search else SearchType.vector
        
        # Initialize LanceDB with hybrid search
        self.vector_db = LanceDb(
            table_name=table_name,
            uri=str(self.db_path),
            embedder=embedder,
            search_type=search_type,
        )
        
        # Create Agno Knowledge wrapper
        self.knowledge = Knowledge(vector_db=self.vector_db)
        
        self._loaded = False
        self._indexing = False
        self._source_counts: dict[str, int] = {}
        
        logger.info(f"Initialized EnhancedGodotKnowledge for version {version}")
    
    @property
    def is_loaded(self) -> bool:
        """Check if knowledge has been indexed."""
        return self._loaded
    
    @property
    def is_indexing(self) -> bool:
        """Check if indexing is in progress."""
        return self._indexing
    
    @property
    def source_counts(self) -> dict[str, int]:
        """Get document counts per source type."""
        return self._source_counts.copy()
    
    async def is_indexed(self) -> bool:
        """Check if knowledge has been indexed in the database."""
        try:
            count = await self.vector_db.async_get_count()
            return count > 0
        except Exception:
            return False
    
    async def load(
        self,
        force_reload: bool = False,
        include_gdscript_ref: bool = True,
        include_tutorials: bool = True,
        max_classes: int | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> bool:
        """Load all knowledge sources into the database.
        
        Args:
            force_reload: If True, re-index all sources
            include_gdscript_ref: Include GDScript language reference
            include_tutorials: Include community tutorials
            max_classes: Limit number of classes (for testing)
            progress_callback: Callback(source_name, current, total) for progress
            
        Returns:
            True if loading was successful
        """
        if not force_reload and await self.is_indexed():
            self._loaded = True
            logger.info(f"Enhanced knowledge for Godot {self.version} already indexed")
            return True
        
        if self._indexing:
            logger.warning("Indexing already in progress")
            return False
        
        self._indexing = True
        self._source_counts = {}
        
        try:
            # Clear existing table if force reload
            if force_reload:
                await self._clear_table()
            
            loader = GodotDocsLoader(
                version=self.version,
                cache_dir=self.db_path / "cache",
            )
            
            all_documents = []
            total_phases = 1 + (1 if include_gdscript_ref else 0) + (1 if include_tutorials else 0)
            current_phase = 0
            
            # Phase 1: Core class reference
            if progress_callback:
                progress_callback("Class Reference", current_phase, total_phases)
            
            classes_to_load = PRIORITY_CLASSES[:max_classes] if max_classes else PRIORITY_CLASSES
            class_docs = await loader.load_documents(classes=classes_to_load)
            
            for doc in class_docs:
                doc.meta_data["source"] = "class_reference"
            
            all_documents.extend(class_docs)
            self._source_counts["class_reference"] = len(class_docs)
            current_phase += 1
            
            # Phase 2: GDScript language reference
            if include_gdscript_ref:
                if progress_callback:
                    progress_callback("GDScript Reference", current_phase, total_phases)
                
                gdscript_classes = GDSCRIPT_REFERENCE_CLASSES[:max_classes] if max_classes else GDSCRIPT_REFERENCE_CLASSES
                gdscript_docs = await loader.load_documents(classes=gdscript_classes)
                
                for doc in gdscript_docs:
                    doc.meta_data["source"] = "gdscript_reference"
                
                all_documents.extend(gdscript_docs)
                self._source_counts["gdscript_reference"] = len(gdscript_docs)
                current_phase += 1
            
            # Phase 3: Community tutorials (works for any version)
            if include_tutorials:
                if progress_callback:
                    progress_callback("Community Tutorials", current_phase, total_phases)
                
                tutorial_docs = await self._load_tutorials(
                    get_tutorials_for_version(self.version)
                )
                all_documents.extend(tutorial_docs)
                self._source_counts["tutorials"] = len(tutorial_docs)
            
            # Index all documents
            if all_documents:
                await self._index_documents(all_documents)
                self._loaded = True
                
                total_docs = sum(self._source_counts.values())
                logger.info(
                    f"Indexed {total_docs} documents for Godot {self.version}: "
                    f"{self._source_counts}"
                )
                return True
            else:
                logger.warning(f"No documents loaded for Godot {self.version}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to load enhanced knowledge: {e}")
            return False
        finally:
            self._indexing = False
    
    async def _clear_table(self) -> None:
        """Clear existing table for fresh indexing."""
        import shutil
        
        table_name = f"godot_enhanced_{self.version.replace('.', '_')}"
        table_dir = self.db_path / f"{table_name}.lance"
        
        if table_dir.exists():
            try:
                shutil.rmtree(table_dir)
                logger.info(f"Cleared existing table: {table_dir}")
            except Exception as e:
                logger.warning(f"Could not clear table: {e}")
    
    async def _load_tutorials(self, tutorials: list[dict]) -> list:
        """Fetch and parse tutorial pages.
        
        Args:
            tutorials: List of tutorial configs with name, url, type
            
        Returns:
            List of Document objects
        """
        from agno.knowledge.document import Document
        import httpx
        
        documents = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for tutorial in tutorials:
                try:
                    response = await client.get(tutorial["url"])
                    if response.status_code == 200:
                        # Extract text from HTML
                        content = self._extract_text_from_html(response.text)
                        
                        # Prepend with metadata for context
                        header = (
                            f"# {tutorial['name']}\n\n"
                            f"**Type:** {tutorial.get('type', 'tutorial')}\n"
                            f"**Description:** {tutorial.get('description', '')}\n\n"
                        )
                        
                        doc = Document(
                            content=header + content,
                            name=tutorial["name"],
                            meta_data={
                                "type": tutorial.get("type", "tutorial"),
                                "source": "tutorial",
                                "version": self.version,
                                "url": tutorial["url"],
                                "description": tutorial.get("description", ""),
                            },
                        )
                        documents.append(doc)
                        logger.debug(f"Loaded tutorial: {tutorial['name']}")
                        
                except Exception as e:
                    logger.warning(f"Failed to load tutorial {tutorial['name']}: {e}")
                
                # Small delay to avoid overwhelming the server
                await asyncio.sleep(0.1)
        
        return documents
    
    def _extract_text_from_html(self, html: str) -> str:
        """Extract meaningful text from HTML content.
        
        Basic extraction that removes scripts, styles, and HTML tags.
        """
        # Remove script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove navigation and footer elements
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        
        # Decode common HTML entities
        entities = {
            '&nbsp;': ' ',
            '&lt;': '<',
            '&gt;': '>',
            '&amp;': '&',
            '&quot;': '"',
            '&#39;': "'",
        }
        for entity, char in entities.items():
            text = text.replace(entity, char)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Limit length to avoid huge documents
        max_length = 10000
        if len(text) > max_length:
            text = text[:max_length] + "..."
        
        return text
    
    async def _index_documents(self, documents: list) -> None:
        """Insert documents into the vector database in batches.
        
        Uses small batches to reduce memory pressure.
        """
        content_hash = hashlib.md5(
            f"enhanced_{self.version}_{len(documents)}".encode()
        ).hexdigest()
        
        batch_size = 5
        total_batches = (len(documents) + batch_size - 1) // batch_size
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            batch_hash = f"{content_hash}_{i // batch_size}"
            
            await self.vector_db.async_insert(batch_hash, batch)
            logger.debug(f"Indexed batch {i // batch_size + 1}/{total_batches}")
    
    async def search(
        self,
        query: str,
        num_results: int = 5,
        source_filter: str | None = None,
    ) -> list[dict]:
        """Search across all knowledge sources.
        
        Uses hybrid search (semantic + keyword) for better results.
        
        Args:
            query: Natural language search query
            num_results: Maximum number of results to return
            source_filter: Optional filter by source type:
                - "class_reference": Official class docs
                - "gdscript_reference": GDScript language docs
                - "tutorial": Community tutorials
                
        Returns:
            List of relevant document chunks with content and metadata
        """
        # Auto-load if not indexed
        if not await self.is_indexed():
            logger.info(f"Auto-indexing Godot {self.version} enhanced documentation...")
            if not await self.load():
                return [{"error": "Failed to index documentation"}]
        
        try:
            # Fetch more results if we're filtering
            fetch_limit = num_results * 3 if source_filter else num_results
            
            results = await self.vector_db.async_search(query, limit=fetch_limit)
            
            # Filter by source if specified
            if source_filter:
                results = [
                    r for r in results
                    if r.meta_data.get("source") == source_filter
                ]
            
            return [
                {
                    "content": doc.content,
                    "metadata": doc.meta_data,
                    "name": doc.name,
                }
                for doc in results[:num_results]
            ]
            
        except Exception as e:
            logger.error(f"Enhanced knowledge search failed: {e}")
            return []
    
    def search_sync(self, query: str, num_results: int = 5) -> list[dict]:
        """Synchronous version of search (for non-async contexts)."""
        try:
            results = self.knowledge.search(query, max_results=num_results)
            return [
                {
                    "content": doc.content,
                    "metadata": doc.meta_data,
                    "name": doc.name,
                }
                for doc in results
            ]
        except Exception as e:
            logger.error(f"Enhanced knowledge search failed: {e}")
            return []


# Singleton cache for knowledge instances
_enhanced_knowledge_cache: dict[str, EnhancedGodotKnowledge] = {}


def get_enhanced_godot_knowledge(
    version: str = "4.5",
    db_path: Path | None = None,
) -> EnhancedGodotKnowledge:
    """Get a cached EnhancedGodotKnowledge instance for the specified version.
    
    Args:
        version: Godot version (e.g., "4.3", "4.2")
        db_path: Custom path for LanceDB storage
        
    Returns:
        EnhancedGodotKnowledge instance (cached per version)
    """
    cache_key = f"{version}:{db_path or 'default'}"
    
    if cache_key not in _enhanced_knowledge_cache:
        _enhanced_knowledge_cache[cache_key] = EnhancedGodotKnowledge(
            version=version,
            db_path=db_path,
        )
    
    return _enhanced_knowledge_cache[cache_key]
