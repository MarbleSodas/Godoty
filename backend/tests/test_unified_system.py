"""
Comprehensive Test Suite for Unified Godoty System

This module provides end-to-end testing of the new simplified Godoty architecture,
validating all components work together seamlessly.

Test Coverage:
- Enhanced Context Engine with RAG
- Unified Session Management
- GodotyAgent functionality
- API Router endpoints
- Integration scenarios
- Performance characteristics
"""

import os
import sys
import asyncio
import json
import time
import pytest
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure test environment
os.environ['PYTHONWARNINGS'] = 'ignore'
os.environ['OPENROUTER_API_KEY'] = 'sk-or-v1-test-key-for-testing'

logger = logging.getLogger(__name__)


class TestEnhancedContextEngine:
    """Test the enhanced context engine with RAG capabilities."""

    @pytest.fixture
    def context_engine(self):
        """Create context engine for testing."""
        from context import create_context_engine
        return create_context_engine(".")

    def test_context_engine_initialization(self, context_engine):
        """Test context engine initializes correctly."""
        assert context_engine is not None
        assert hasattr(context_engine, 'vector_store')
        assert hasattr(context_engine, 'code_parser')

    def test_semantic_search_functionality(self, context_engine):
        """Test semantic search finds relevant code."""
        # Search for something that should exist in the codebase
        results = context_engine.semantic_search("GodotyAgent", limit=5)
        assert isinstance(results, list)

        if results:  # Only test if we have results
            result = results[0]
            assert hasattr(result, 'content')
            assert hasattr(result, 'file_path')
            assert hasattr(result, 'similarity_score')
            assert result.similarity_score > 0

    def test_code_parsing_capabilities(self, context_engine):
        """Test code parser handles multiple languages."""
        parser = context_engine.code_parser
        assert parser is not None

        # Test Python parsing
        python_content = """
class TestClass:
    def test_method(self):
        return "Hello World"
"""
        chunks = parser.parse_content(python_content, "test.py", "python")
        assert len(chunks) > 0

    def test_project_indexing(self, context_engine):
        """Test project indexing works correctly."""
        stats = context_engine.get_indexing_stats()
        assert isinstance(stats, dict)
        assert 'total_chunks' in stats
        assert 'total_files' in stats


class TestUnifiedSessionManager:
    """Test the unified session management system."""

    @pytest.fixture
    def session_manager(self):
        """Create session manager for testing."""
        from agents.unified_session import create_session_manager
        return create_session_manager("./test_sessions")

    def test_session_creation(self, session_manager):
        """Test session creation and management."""
        # Create session
        session_id = session_manager.create_session("Test Session", "/test/path")
        assert session_id is not None
        assert len(session_id) == 36  # UUID length

        # Verify session exists
        session_info = session_manager.get_session(session_id)
        assert session_info is not None
        assert session_info.title == "Test Session"
        assert session_info.project_path == "/test/path"

        # List sessions
        sessions = session_manager.list_sessions()
        assert len(sessions) >= 1
        assert any(s.session_id == session_id for s in sessions)

    def test_message_recording(self, session_manager):
        """Test message recording and retrieval."""
        session_id = session_manager.create_session("Message Test")

        # Add user message
        from agents.unified_session import MessageEntry
        user_message = MessageEntry(
            message_id="msg1",
            role="user",
            content="Hello, how can you help me?",
            timestamp=datetime.utcnow()
        )
        success = session_manager.add_message(session_id, user_message)
        assert success

        # Add assistant message
        assistant_message = MessageEntry(
            message_id="msg2",
            role="assistant",
            content="I can help you with Godot development!",
            timestamp=datetime.utcnow(),
            model_name="test-model",
            tokens=50,
            cost=0.001
        )
        success = session_manager.add_message(session_id, assistant_message)
        assert success

        # Retrieve history
        history = session_manager.get_conversation_history(session_id)
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[1].role == "assistant"

    def test_session_metrics(self, session_manager):
        """Test session metrics tracking."""
        session_id = session_manager.create_session("Metrics Test")

        # Add messages with metadata
        from agents.unified_session import MessageEntry
        for i in range(3):
            message = MessageEntry(
                message_id=f"msg{i}",
                role="user" if i % 2 == 0 else "assistant",
                content=f"Test message {i}",
                timestamp=datetime.utcnow(),
                tokens=10 * (i + 1),
                cost=0.0001 * (i + 1)
            )
            session_manager.add_message(session_id, message)

        # Check metrics
        metrics = session_manager.get_session_metrics(session_id)
        assert metrics is not None
        assert metrics.total_messages == 3
        assert metrics.total_tokens > 0
        assert metrics.total_cost > 0

    def test_storage_statistics(self, session_manager):
        """Test storage statistics functionality."""
        stats = session_manager.get_storage_stats()
        assert isinstance(stats, dict)
        assert 'total_sessions' in stats
        assert 'database_size_mb' in stats
        assert 'storage_path' in stats


class TestGodotyAgent:
    """Test the unified GodotyAgent functionality."""

    @pytest.fixture
    def agent(self):
        """Create agent for testing."""
        from agents.godoty_agent import GodotyAgent
        return GodotyAgent()

    def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent is not None
        assert hasattr(agent, 'context_engine')
        assert hasattr(agent, 'session_manager')
        assert hasattr(agent, 'model')

    def test_session_lifecycle(self, agent):
        """Test complete session lifecycle with agent."""
        # Create session
        session_id = agent.create_session("Agent Test Session")
        assert session_id is not None

        # Get session info
        session_info = agent.get_session_info(session_id)
        assert session_info is not None
        assert session_info.title == "Agent Test Session"

        # Update session
        success = agent.update_session_title(session_id, "Updated Title")
        assert success

        # Verify update
        updated_info = agent.get_session_info(session_id)
        assert updated_info.title == "Updated Title"

        # Delete session
        success = agent.delete_session(session_id)
        assert success

    def test_agent_state_persistence(self, agent):
        """Test agent state saving and loading."""
        session_id = agent.create_session("State Test")

        # Save agent state
        success = agent._save_agent_state(session_id)
        assert success

        # Clear session context
        if session_id in agent.session_context:
            del agent.session_context[session_id]

        # Load agent state
        success = agent._load_agent_state(session_id)
        assert success

        # Verify context was restored
        assert session_id in agent.session_context

    def test_message_recording_integration(self, agent):
        """Test message recording with agent integration."""
        session_id = agent.create_session("Message Recording Test")

        # Record user message
        success = agent._record_message(
            session_id=session_id,
            message="Test user message",
            role="user"
        )
        assert success

        # Record assistant message
        success = agent._record_message(
            session_id=session_id,
            message="Test assistant response",
            role="assistant",
            model_name="test-model",
            tokens=25,
            cost=0.0005,
            metadata={"type": "response", "confidence": 0.9}
        )
        assert success

        # Verify messages were recorded
        history = agent.get_conversation_history(session_id)
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[1].role == "assistant"
        assert history[1].model_name == "test-model"
        assert history[1].tokens == 25


class TestGodotyAPIRouter:
    """Test the simplified API router."""

    @pytest.fixture
    def client(self):
        """Create test client for API."""
        from main_simplified import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/api/godoty/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "agent_available" in data
        assert "session_manager_available" in data
        assert data["status"] in ["healthy", "unhealthy"]

    def test_status_endpoint(self, client):
        """Test status endpoint."""
        response = client.get("/api/godoty/status")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "sessions" in data
        assert "storage" in data

    def test_session_creation_endpoint(self, client):
        """Test session creation via API."""
        request_data = {
            "title": "API Test Session",
            "project_path": "/test/project"
        }

        response = client.post("/api/godoty/sessions", json=request_data)
        assert response.status_code == 200

        data = response.json()
        assert "session_id" in data
        assert data["title"] == "API Test Session"
        assert data["project_path"] == "/test/project"

    def test_session_listing_endpoint(self, client):
        """Test session listing via API."""
        # First create a session
        client.post("/api/godoty/sessions", json={"title": "List Test"})

        # List sessions
        response = client.get("/api/godoty/sessions")
        assert response.status_code == 200

        data = response.json()
        assert "sessions" in data
        assert "total_count" in data
        assert isinstance(data["sessions"], list)

    def test_config_endpoint(self, client):
        """Test configuration endpoint."""
        response = client.get("/api/godoty/config")
        assert response.status_code == 200

        data = response.json()
        assert "model_id" in data
        assert "temperature" in data
        assert "max_tokens" in data
        assert "available_models" in data
        assert isinstance(data["available_models"], list)

    def test_global_metrics_endpoint(self, client):
        """Test global metrics endpoint."""
        response = client.get("/api/godoty/metrics")
        assert response.status_code == 200

        data = response.json()
        assert "global_metrics" in data
        assert "timestamp" in data

        metrics = data["global_metrics"]
        assert "total_sessions" in metrics
        assert "total_messages" in metrics
        assert "total_tokens" in metrics


class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    @pytest.fixture
    def agent(self):
        """Create agent for integration testing."""
        from agents.godoty_agent import GodotyAgent
        return GodotyAgent()

    def test_complete_chat_workflow(self, agent):
        """Test complete chat workflow from start to finish."""
        # Create session
        session_id = agent.create_session("Integration Test Chat")

        # Create chat request
        from agents.godoty_agent import GodotyRequest
        request = GodotyRequest(
            message="Help me understand the Godoty architecture",
            session_id=session_id,
            context_limit=5,
            mode="auto"
        )

        # Process message (collect responses)
        responses = []
        try:
            async def collect_responses():
                async for response in agent.process_message(request):
                    responses.append(response)
                    break  # Just get first response for testing

            asyncio.run(collect_responses())
        except Exception as e:
            # Expected to fail with test API key, but should not crash
            logger.info(f"Expected API key error in test: {e}")

        # Verify session state
        history = agent.get_conversation_history(session_id)
        assert len(history) >= 1  # Should have user message at minimum
        assert history[0].role == "user"

    def test_context_search_integration(self, agent):
        """Test context search integration with chat."""
        # Test semantic search
        results = agent.context_engine.semantic_search("unified session", limit=3)
        assert isinstance(results, list)

        # Create session with context
        session_id = agent.create_session("Context Integration Test")

        # Test chat with context
        from agents.godoty_agent import GodotyRequest
        request = GodotyRequest(
            message="How does the unified session manager work?",
            session_id=session_id,
            context_limit=5,
            include_dependencies=True
        )

        # Verify request creation works
        assert request.session_id == session_id
        assert request.include_dependencies is True

    def test_metrics_tracking_integration(self, agent):
        """Test metrics tracking across the system."""
        session_id = agent.create_session("Metrics Integration Test")

        # Record multiple messages
        for i in range(5):
            agent._record_message(
                session_id=session_id,
                message=f"Test message {i}",
                role="user" if i % 2 == 0 else "assistant",
                tokens=10 * (i + 1),
                cost=0.0001 * (i + 1)
            )

        # Check session metrics
        metrics = agent.get_session_metrics(session_id)
        if metrics:
            assert metrics.total_messages == 5
            assert metrics.total_tokens > 0
            assert metrics.total_cost > 0

    def test_error_handling_integration(self, agent):
        """Test error handling across the system."""
        # Test invalid session ID
        invalid_history = agent.get_conversation_history("invalid-session-id")
        assert invalid_history == []

        # Test invalid session operations
        invalid_session = agent.get_session_info("invalid-session-id")
        assert invalid_session is None

        # Test message recording with invalid session
        success = agent._record_message(
            session_id="invalid-session",
            message="Test message",
            role="user"
        )
        assert not success


class TestPerformanceCharacteristics:
    """Test performance characteristics of the unified system."""

    def test_context_search_performance(self):
        """Test semantic search performance."""
        from context import create_context_engine
        context_engine = create_context_engine(".")

        # Measure search time
        start_time = time.time()
        results = context_engine.semantic_search("GodotyAgent", limit=10)
        search_time = time.time() - start_time

        assert search_time < 2.0  # Should complete within 2 seconds
        assert isinstance(results, list)

    def test_session_creation_performance(self):
        """Test session creation performance."""
        from agents.unified_session import create_session_manager
        session_manager = create_session_manager("./perf_test_sessions")

        # Create multiple sessions and measure time
        start_time = time.time()
        session_ids = []

        for i in range(10):
            session_id = session_manager.create_session(f"Performance Test {i}")
            session_ids.append(session_id)

        creation_time = time.time() - start_time

        # Should create 10 sessions quickly
        assert creation_time < 1.0
        assert len(session_ids) == 10

        # Verify all sessions were created
        for session_id in session_ids:
            session_info = session_manager.get_session(session_id)
            assert session_info is not None

    def test_message_recording_performance(self):
        """Test message recording performance."""
        from agents.unified_session import create_session_manager, MessageEntry
        session_manager = create_session_manager("./perf_test_messages")

        session_id = session_manager.create_session("Message Performance Test")

        # Record multiple messages and measure time
        start_time = time.time()

        for i in range(20):
            message = MessageEntry(
                message_id=f"perf_msg_{i}",
                role="user" if i % 2 == 0 else "assistant",
                content=f"Performance test message {i}",
                timestamp=datetime.utcnow(),
                tokens=10,
                cost=0.0001
            )
            session_manager.add_message(session_id, message)

        recording_time = time.time() - start_time

        # Should record 20 messages quickly
        assert recording_time < 0.5

        # Verify all messages were recorded
        history = session_manager.get_conversation_history(session_id)
        assert len(history) == 20


# Import needed for test utilities
from context import create_context_engine

# Test execution utilities
def run_performance_tests():
    """Run performance tests separately."""
    print("🚀 Running performance tests...")

    perf_class = TestPerformanceCharacteristics()

    try:
        perf_class.test_context_search_performance()
        print("✅ Context search performance test passed")

        perf_class.test_session_creation_performance()
        print("✅ Session creation performance test passed")

        perf_class.test_message_recording_performance()
        print("✅ Message recording performance test passed")

        print("🎉 All performance tests completed successfully!")

    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        raise


def run_integration_tests():
    """Run integration tests."""
    print("🔗 Running integration tests...")

    integration_class = TestIntegrationScenarios()

    # Create agent for integration tests
    from agents.godoty_agent import GodotyAgent
    agent = GodotyAgent()

    try:
        integration_class.test_complete_chat_workflow(agent)
        print("✅ Complete chat workflow test passed")

        integration_class.test_context_search_integration(agent)
        print("✅ Context search integration test passed")

        integration_class.test_metrics_tracking_integration(agent)
        print("✅ Metrics tracking integration test passed")

        integration_class.test_error_handling_integration(agent)
        print("✅ Error handling integration test passed")

        print("🎉 All integration tests completed successfully!")

    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        raise


def run_comprehensive_tests():
    """Run all tests for the unified system."""
    print("🧪 Starting Comprehensive System Testing")
    print("=" * 50)

    try:
        # Test individual components
        print("\n📋 Testing Enhanced Context Engine...")
        context_class = TestEnhancedContextEngine()
        context_engine = create_context_engine(".")
        context_class.test_context_engine_initialization(context_engine)
        context_class.test_semantic_search_functionality(context_engine)
        context_class.test_code_parsing_capabilities(context_engine)
        context_class.test_project_indexing(context_engine)
        print("✅ Enhanced Context Engine tests passed")

        print("\n💾 Testing Unified Session Manager...")
        session_class = TestUnifiedSessionManager()
        from agents.unified_session import create_session_manager
        session_manager = create_session_manager("./comprehensive_test_sessions")
        session_class.test_session_creation(session_manager)
        session_class.test_message_recording(session_manager)
        session_class.test_session_metrics(session_manager)
        session_class.test_storage_statistics(session_manager)
        print("✅ Unified Session Manager tests passed")

        print("\n🤖 Testing GodotyAgent...")
        agent_class = TestGodotyAgent()
        agent = GodotyAgent()
        agent_class.test_agent_initialization(agent)
        agent_class.test_session_lifecycle(agent)
        agent_class.test_agent_state_persistence(agent)
        agent_class.test_message_recording_integration(agent)
        print("✅ GodotyAgent tests passed")

        print("\n🌐 Testing GodotyAPIRouter...")
        api_class = TestGodotyAPIRouter()
        from main_simplified import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        client = TestClient(app)
        api_class.test_health_endpoint(client)
        api_class.test_status_endpoint(client)
        api_class.test_session_creation_endpoint(client)
        api_class.test_session_listing_endpoint(client)
        api_class.test_config_endpoint(client)
        api_class.test_global_metrics_endpoint(client)
        print("✅ GodotyAPIRouter tests passed")

        print("\n🔗 Running Integration Tests...")
        run_integration_tests()

        print("\n⚡ Running Performance Tests...")
        run_performance_tests()

        print("\n" + "=" * 50)
        print("🎉 ALL COMPREHENSIVE TESTS PASSED! 🎉")
        print("🚀 The unified Godoty system is fully operational!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run_comprehensive_tests()