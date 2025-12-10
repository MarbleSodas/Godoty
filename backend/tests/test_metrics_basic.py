"""
Basic tests for metrics tracking infrastructure.

Run with: pytest backend/tests/test_metrics_basic.py -v
"""

import pytest
import asyncio
from database.models import Base, MessageMetrics, SessionMetrics, ProjectMetrics
from database.db_manager import DatabaseManager
from agents.metrics_tracker import TokenMetricsTracker


class TestTokenMetricsTracker:
    """Test token metrics tracker."""
    
    def test_extract_metrics_from_response(self):
        """Test extracting metrics from OpenRouter response."""
        tracker = TokenMetricsTracker()
        
        response = {
            "id": "gen_123",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            },
            "choices": [{
                "finish_reason": "stop"
            }]
        }
        
        metrics = tracker.extract_metrics_from_response(response, "openai/gpt-4-turbo")
        
        assert metrics["prompt_tokens"] == 100
        assert metrics["completion_tokens"] == 50
        assert metrics["total_tokens"] == 150
        assert metrics["generation_id"] == "gen_123"
        assert metrics["stop_reason"] == "stop"
        # Without explicit cost from OpenRouter, should default to 0.0
        assert metrics["estimated_cost"] == 0.0

    def test_extract_metrics_from_response_with_cost(self):
        """Test extracting metrics from OpenRouter response with provided cost."""
        tracker = TokenMetricsTracker()
        
        response = {
            "id": "gen_123",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "cost": 0.05  # Explicit cost
            },
            "choices": [{
                "finish_reason": "stop"
            }]
        }
        
        metrics = tracker.extract_metrics_from_response(response, "openai/gpt-4-turbo")
        
        assert metrics["prompt_tokens"] == 100
        assert metrics["completion_tokens"] == 50
        assert metrics["total_tokens"] == 150
        assert metrics["estimated_cost"] == 0.05
        assert metrics["actual_cost"] == 0.05



@pytest.mark.asyncio
class TestDatabaseManager:
    """Test database manager operations."""
    
    async def test_database_initialization(self, tmp_path):
        """Test database initialization."""
        db_path = str(tmp_path / "test_metrics.db")
        db_manager = DatabaseManager(db_path=db_path)
        
        await db_manager.initialize()
        
        # Verify tables were created
        assert db_manager.engine is not None
        
        await db_manager.close()
    
    async def test_create_message_metrics(self, tmp_path):
        """Test creating message metrics."""
        db_path = str(tmp_path / "test_metrics.db")
        db_manager = DatabaseManager(db_path=db_path)
        await db_manager.initialize()
        
        metrics = await db_manager.create_message_metrics(
            message_id="msg_test_001",
            model_id="openai/gpt-4-turbo",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost=0.0025
        )
        
        assert metrics.message_id == "msg_test_001"
        assert metrics.prompt_tokens == 100
        assert metrics.completion_tokens == 50
        
        await db_manager.close()
    
    async def test_get_message_metrics(self, tmp_path):
        """Test retrieving message metrics."""
        db_path = str(tmp_path / "test_metrics.db")
        db_manager = DatabaseManager(db_path=db_path)
        await db_manager.initialize()
        
        # Create metrics
        await db_manager.create_message_metrics(
            message_id="msg_test_002",
            model_id="openai/gpt-4-turbo",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost=0.0025
        )
        
        # Retrieve metrics
        metrics = await db_manager.get_message_metrics("msg_test_002")
        
        assert metrics is not None
        assert metrics.message_id == "msg_test_002"
        
        await db_manager.close()
    
    async def test_session_metrics(self, tmp_path):
        """Test session metrics creation and retrieval."""
        db_path = str(tmp_path / "test_metrics.db")
        db_manager = DatabaseManager(db_path=db_path)
        await db_manager.initialize()
        
        # Create session
        session = await db_manager.get_or_create_session_metrics("session_001")
        assert session.session_id == "session_001"
        
        # Update session with message metrics
        await db_manager.update_session_metrics(
            session_id="session_001",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost=0.0025,
            model_id="openai/gpt-4-turbo"
        )
        
        # Retrieve session
        session = await db_manager.get_session_metrics("session_001")
        assert session.total_prompt_tokens == 100
        assert session.total_completion_tokens == 50
        assert session.message_count == 1
        
        await db_manager.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
