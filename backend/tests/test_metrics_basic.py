"""
Basic tests for metrics tracking infrastructure.

Run with: pytest backend/tests/test_metrics_basic.py -v
"""

import pytest
import asyncio
from database.models import Base, MessageMetrics, SessionMetrics, ProjectMetrics
from database.db_manager import DatabaseManager
from agents.metrics_tracker import ModelPricing, TokenMetricsTracker


class TestModelPricing:
    """Test model pricing calculations."""
    
    def test_get_pricing(self):
        """Test getting pricing for known model."""
        prompt_price, completion_price = ModelPricing.get_pricing("openai/gpt-4-turbo")
        assert prompt_price == 10.0
        assert completion_price == 30.0
    
    def test_get_pricing_unknown_model(self):
        """Test getting pricing for unknown model returns default."""
        prompt_price, completion_price = ModelPricing.get_pricing("unknown/model")
        assert prompt_price == 1.0
        assert completion_price == 2.0
    
    def test_calculate_cost(self):
        """Test cost calculation."""
        cost = ModelPricing.calculate_cost(
            "openai/gpt-4-turbo",
            prompt_tokens=1000,
            completion_tokens=500
        )
        # 1000 tokens * $10/1M + 500 tokens * $30/1M = $0.01 + $0.015 = $0.025
        assert cost == pytest.approx(0.025)


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
        assert metrics["estimated_cost"] > 0


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
