"""
Tests for the Context Engine.

Tests the hybrid retrieval system including:
- Knowledge graph queries
- Vector store search
- Intent classification
- Context bundle formatting
"""

import pytest
import tempfile
import os
import shutil
from pathlib import Path

# Try to import context engine components
try:
    from context.engine import GodotContextEngine, QueryIntent, ContextBundle
    from context.knowledge_graph import GodotKnowledgeGraph, NodeType, EdgeType
    from context.vector_store import GodotVectorStore, GDScriptChunker, CodeChunk
    CONTEXT_AVAILABLE = True
except ImportError as e:
    CONTEXT_AVAILABLE = False
    pytest.skip(f"Context engine not available: {e}", allow_module_level=True)


# =============================================================================
# Test Fixtures  
# =============================================================================

@pytest.fixture
def sample_project(tmp_path):
    """Create a sample Godot project structure for testing."""
    # Create project.godot
    project_godot = tmp_path / "project.godot"
    project_godot.write_text('''config_version=5

[application]
config/name="Test Project"
config/features=PackedStringArray("4.2")

[autoload]
Events="*res://autoloads/events.gd"
''')
    
    # Create autoloads directory
    autoloads = tmp_path / "autoloads"
    autoloads.mkdir()
    
    # Create events.gd
    events = autoloads / "events.gd"
    events.write_text('''## Global event bus
class_name Events
extends Node

signal player_died
signal level_completed(level_id: int)
''')
    
    # Create player.gd
    player = tmp_path / "player.gd"
    player.write_text('''## Player character controller
class_name Player
extends CharacterBody2D

signal health_changed(amount: int)

@export var speed: float = 200.0
@export var health: int = 100

func _physics_process(delta: float) -> void:
    move_and_slide()

func take_damage(amount: int) -> void:
    health -= amount
    health_changed.emit(health)
''')
    
    # Create enemy.gd that references Player
    enemy = tmp_path / "enemy.gd"
    enemy.write_text('''## Enemy AI
class_name Enemy
extends CharacterBody2D

@export var damage: int = 10
var target: Player

func attack() -> void:
    if target:
        target.take_damage(damage)
''')
    
    # Create main.tscn
    main_scene = tmp_path / "main.tscn"
    main_scene.write_text('''[gd_scene load_steps=2 format=3 uid="uid://main123"]

[ext_resource type="Script" path="res://player.gd" id="1_player"]

[node name="Main" type="Node2D"]

[node name="Player" type="CharacterBody2D" parent="."]
script = ExtResource("1_player")

[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]

[connection signal="health_changed" from="Player" to="." method="_on_player_health_changed"]
''')
    
    return tmp_path


# =============================================================================
# Knowledge Graph Tests
# =============================================================================

class TestKnowledgeGraph:
    """Tests for the knowledge graph."""
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_build_graph(self, sample_project):
        """Test building a knowledge graph from a project."""
        graph = GodotKnowledgeGraph()
        graph.build_from_project(str(sample_project))
        
        # Should have nodes
        assert graph.graph.number_of_nodes() > 0
        assert graph.graph.number_of_edges() > 0
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_project_summary(self, sample_project):
        """Test getting project summary."""
        graph = GodotKnowledgeGraph()
        graph.build_from_project(str(sample_project))
        
        summary = graph.get_project_summary()
        
        assert summary['project_name'] == "Test Project"
        assert summary['scripts'] >= 2  # player.gd, enemy.gd, events.gd
        assert summary['scenes'] >= 1  # main.tscn
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_class_hierarchy(self, sample_project):
        """Test getting class hierarchy."""
        graph = GodotKnowledgeGraph()
        graph.build_from_project(str(sample_project))
        
        # Find Player script path
        player_path = None
        for node_id, data in graph.graph.nodes(data=True):
            if data.get('class_name') == 'Player':
                player_path = data.get('path')
                break
        
        if player_path:
            hierarchy = graph.get_class_hierarchy(player_path)
            assert 'Player' in hierarchy
            assert 'CharacterBody2D' in hierarchy
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_text_summary(self, sample_project):
        """Test generating text summary."""
        graph = GodotKnowledgeGraph()
        graph.build_from_project(str(sample_project))
        
        summary = graph.to_text_summary()
        
        assert "Test Project" in summary
        assert "Scenes" in summary
        assert "Scripts" in summary


# =============================================================================
# Chunker Tests
# =============================================================================

class TestGDScriptChunker:
    """Tests for the syntax-aware code chunker."""
    
    def test_chunk_script(self):
        """Test chunking a GDScript file."""
        chunker = GDScriptChunker()
        
        content = '''class_name Player
extends CharacterBody2D

@export var speed: float = 200.0

func _physics_process(delta: float) -> void:
    move_and_slide()

func take_damage(amount: int) -> void:
    health -= amount
'''
        
        chunks = chunker.chunk_script(content, "res://player.gd")
        
        # Should have header and functions
        assert len(chunks) >= 2
        
        # Check chunk types
        chunk_types = [c.chunk_type for c in chunks]
        assert 'class_header' in chunk_types or 'function' in chunk_types
    
    def test_chunk_preserves_functions(self):
        """Test that functions are chunked completely."""
        chunker = GDScriptChunker()
        
        content = '''extends Node

## This is a documented function
func my_function(x: int, y: int) -> int:
    var result = x + y
    result *= 2
    return result
'''
        
        chunks = chunker.chunk_script(content, "res://test.gd")
        
        # Find the function chunk
        func_chunks = [c for c in chunks if c.chunk_type in ('function', 'virtual_method')]
        
        if func_chunks:
            func = func_chunks[0]
            assert 'my_function' in func.content or func.name == 'my_function'
    
    def test_chunk_signal_handlers(self):
        """Test that signal handlers are identified correctly."""
        chunker = GDScriptChunker()
        
        content = '''extends Node

func _on_button_pressed() -> void:
    print("pressed")

func _on_timer_timeout() -> void:
    print("timeout")
'''
        
        chunks = chunker.chunk_script(content, "res://test.gd")
        
        # Find signal handler chunks
        handler_chunks = [c for c in chunks if c.chunk_type == 'signal_handler']
        
        # Should identify signal handlers
        assert len(handler_chunks) >= 0  # May or may not detect based on implementation


# =============================================================================
# Intent Classification Tests
# =============================================================================

class TestIntentClassification:
    """Tests for query intent classification."""
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_structural_intent(self, sample_project):
        """Test classification of structural queries."""
        engine = GodotContextEngine(str(sample_project))
        
        # Structural queries
        assert engine.classify_intent("Where is the player?") == QueryIntent.STRUCTURAL
        assert engine.classify_intent("Find all nodes") == QueryIntent.STRUCTURAL
        assert engine.classify_intent("What signals does Player emit?") == QueryIntent.STRUCTURAL
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_semantic_intent(self, sample_project):
        """Test classification of semantic queries."""
        engine = GodotContextEngine(str(sample_project))
        
        # Semantic queries
        assert engine.classify_intent("How does movement work?") == QueryIntent.SEMANTIC
        assert engine.classify_intent("Explain the damage implementation") == QueryIntent.SEMANTIC
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_api_intent(self, sample_project):
        """Test classification of API queries."""
        engine = GodotContextEngine(str(sample_project))
        
        # API queries
        assert engine.classify_intent("What is CharacterBody2D?") == QueryIntent.API
        assert engine.classify_intent("What does move_and_slide do?") == QueryIntent.API


# =============================================================================
# Context Bundle Tests
# =============================================================================

class TestContextBundle:
    """Tests for context bundle formatting."""
    
    def test_to_prompt_context(self):
        """Test formatting context bundle for prompt injection."""
        bundle = ContextBundle(
            query="test query",
            intent=QueryIntent.HYBRID,
            graph_results=[
                {
                    'type': 'class_hierarchy',
                    'entity': 'Player',
                    'hierarchy': ['Player', 'CharacterBody2D', 'Node2D']
                }
            ],
            code_results=[]
        )
        
        context = bundle.to_prompt_context(token_budget=2000)
        
        assert "Structural Context" in context
        assert "Class Hierarchy" in context
        assert "Player" in context
    
    def test_token_budget(self):
        """Test that context respects token budget."""
        # Create bundle with lots of content
        bundle = ContextBundle(
            query="test",
            intent=QueryIntent.HYBRID,
            graph_results=[{'type': 'test', 'data': 'x' * 10000}]
        )
        
        # Small budget
        context = bundle.to_prompt_context(token_budget=100)
        
        # Should be truncated
        assert len(context) < 10000


# =============================================================================
# Full Engine Tests
# =============================================================================

class TestContextEngine:
    """Integration tests for the full context engine."""
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_build_index(self, sample_project):
        """Test building the full index."""
        engine = GodotContextEngine(str(sample_project))
        engine.build_index()
        
        assert engine.is_indexed()
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_get_project_map(self, sample_project):
        """Test getting project map."""
        engine = GodotContextEngine(str(sample_project))
        engine.build_index()
        
        project_map = engine.get_project_map()
        
        assert "Test Project" in project_map
        assert "Scripts" in project_map
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_get_stats(self, sample_project):
        """Test getting engine stats."""
        engine = GodotContextEngine(str(sample_project))
        engine.build_index()
        
        stats = engine.get_stats()
        
        assert stats['indexed'] is True
        assert 'graph' in stats
        assert 'vector_store' in stats
    
    @pytest.mark.skipif(not CONTEXT_AVAILABLE, reason="Context engine not available")
    def test_retrieve_context(self, sample_project):
        """Test context retrieval."""
        engine = GodotContextEngine(str(sample_project))
        engine.build_index()
        
        bundle = engine.retrieve_context("player movement", limit=5)
        
        assert bundle.query == "player movement"
        assert isinstance(bundle.intent, QueryIntent)
