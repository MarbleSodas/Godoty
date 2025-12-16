"""Tests for the Godot knowledge base and LSP modules."""

import asyncio
import pytest
from pathlib import Path


class TestGodotDocsKnowledge:
    """Tests for GodotDocsKnowledge class."""

    def test_import(self):
        """Test that knowledge module imports correctly."""
        from app.knowledge import GodotDocsKnowledge, get_godot_knowledge
        assert GodotDocsKnowledge is not None
        assert get_godot_knowledge is not None

    def test_get_godot_knowledge_caching(self):
        """Test that get_godot_knowledge returns cached instances."""
        from app.knowledge import get_godot_knowledge
        
        kb1 = get_godot_knowledge("4.3")
        kb2 = get_godot_knowledge("4.3")
        kb3 = get_godot_knowledge("4.2")
        
        assert kb1 is kb2  # Same version = same instance
        assert kb1 is not kb3  # Different version = different instance

    def test_knowledge_init(self):
        """Test basic knowledge initialization."""
        from app.knowledge import GodotDocsKnowledge
        
        kb = GodotDocsKnowledge(version="4.3")
        assert kb.version == "4.3"
        assert not kb.is_loaded


class TestGDScriptLSPClient:
    """Tests for GDScriptLSPClient class."""

    def test_import(self):
        """Test that LSP client imports correctly."""
        from app.knowledge import GDScriptLSPClient, get_lsp_client
        assert GDScriptLSPClient is not None
        assert get_lsp_client is not None

    def test_client_init(self):
        """Test basic client initialization."""
        from app.knowledge import GDScriptLSPClient
        
        client = GDScriptLSPClient(host="127.0.0.1", port=6005)
        assert client.host == "127.0.0.1"
        assert client.port == 6005
        assert not client.is_connected

    def test_get_lsp_client_singleton(self):
        """Test that get_lsp_client returns a singleton."""
        from app.knowledge import get_lsp_client
        
        client1 = get_lsp_client()
        client2 = get_lsp_client()
        
        assert client1 is client2


class TestGodotDocsLoader:
    """Tests for GodotDocsLoader class."""

    def test_import(self):
        """Test that loader imports correctly."""
        from app.knowledge.godot_docs_loader import GodotDocsLoader
        assert GodotDocsLoader is not None

    def test_loader_init(self):
        """Test loader initialization with version."""
        from app.knowledge.godot_docs_loader import GodotDocsLoader
        
        loader = GodotDocsLoader(version="4.3")
        assert loader.version == "4.3"
        assert loader._tag == "4.3-stable"


class TestKnowledgeTools:
    """Tests for knowledge-related agent tools."""

    def test_tools_import(self):
        """Test that knowledge tools are exported."""
        from app.agents.tools import (
            query_godot_docs,
            get_symbol_info,
            get_code_completions,
        )
        assert callable(query_godot_docs)
        assert callable(get_symbol_info)
        assert callable(get_code_completions)
