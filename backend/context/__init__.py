"""
Enhanced RAG Context Module

This module provides advanced RAG capabilities for the Godoty project including:
- Vector embeddings with sentence-transformers
- Multi-language code parsing
- Fast similarity search with FAISS
- Semantic code understanding
"""

from .enhanced_engine import EnhancedContextEngine, CodeChunk, SearchResult, create_context_engine
from .code_parser import CodeParser, ParsedElement
from .vector_store import VectorStore, VectorMetadata, SearchQuery, SearchResult, create_vector_store

__all__ = [
    'EnhancedContextEngine',
    'CodeChunk',
    'SearchResult',
    'create_context_engine',
    'CodeParser',
    'ParsedElement',
    'VectorStore',
    'VectorMetadata',
    'SearchQuery',
    'create_vector_store'
]

__version__ = '1.0.0'
__author__ = 'Godoty Development Team'