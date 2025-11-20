"""
End-to-end integration test for metrics tracking.

This test verifies the complete flow from API call to metrics persistence.

Run with: pytest backend/tests/test_metrics_integration.py -v -s
"""

import pytest
import asyncio
from agents import PlanningAgent
from database import get_db_manager
from agents.config import AgentConfig


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires valid API key and may incur costs")
class TestMetricsIntegration:
    """End-to-end integration tests for metrics tracking."""
    
    async def test_full_metrics_flow(self, tmp_path):
        """Test complete flow from agent call to metrics storage and retrieval."""
        # Setup test database
        db_path = str(tmp_path / "test_metrics.db")
        db_manager = get_db_manager(db_path=db_path)
        await db_manager.initialize()
        
        # Create planning agent with metrics enabled
        agent = PlanningAgent()
        
        try:
            # Make a simple planning request
            result = await agent.plan_async(
                prompt="Create a simple 2D player controller in Godot",
                session_id="test_session_001",
                project_id="test_project_001"
            )
            
            # Verify result structure
            assert isinstance(result, dict)
            assert "plan" in result
            assert "message_id" in result
            assert result["message_id"] is not None
            
            # Verify metrics were tracked
            if result.get("metrics"):
                metrics = result["metrics"]
                assert metrics["total_tokens"] > 0
                assert metrics["estimated_cost"] > 0
                
                # Retrieve stored metrics from database
                message_id = result["message_id"]
                stored_metrics = await db_manager.get_message_metrics(message_id)
                
                assert stored_metrics is not None
                assert stored_metrics.message_id == message_id
                assert stored_metrics.total_tokens > 0
                assert stored_metrics.estimated_cost > 0
                
                # Verify session metrics were created
                session_metrics = await db_manager.get_session_metrics("test_session_001")
                assert session_metrics is not None
                assert session_metrics.message_count >= 1
                
                # Verify project metrics were created
                project_metrics = await db_manager.get_project_metrics("test_project_001")
                assert project_metrics is not None
                assert project_metrics.session_count >= 1
                
                print(f"\\n✅ Metrics tracked successfully:")
                print(f"   Message ID: {message_id}")
                print(f"   Total tokens: {stored_metrics.total_tokens}")
                print(f"   Estimated cost: ${stored_metrics.estimated_cost:.4f}")
                print(f"   Session messages: {session_metrics.message_count}")
                print(f"   Project sessions: {project_metrics.session_count}")
            
        finally:
            await agent.close()
            await db_manager.close()
    
    async def test_metrics_disabled(self):
        """Test that disabling metrics doesn't break functionality."""
        # Temporarily disable metrics
        original_value = AgentConfig.ENABLE_METRICS_TRACKING
        AgentConfig.ENABLE_METRICS_TRACKING = False
        
        try:
            agent = PlanningAgent()
            
            # Agent should still work without metrics
            result = await agent.plan_async("Simple test prompt")
            
            # Should still return dict format
            assert isinstance(result, dict)
            assert "plan" in result
            
            # Metrics should be None when disabled
            assert result.get("metrics") is None
            
            await agent.close()
            
        finally:
            AgentConfig.ENABLE_METRICS_TRACKING = original_value


@pytest.mark.asyncio
class TestMetricsAPI:
    """Test metrics API endpoints."""
    
    async def test_api_endpoints_exist(self):
        """Verify that all metrics API endpoints are defined."""
        from api.metrics_routes import router
        
        routes = [route.path for route in router.routes]
        
        assert "/api/metrics/message/{message_id}" in routes
        assert "/api/metrics/session/{session_id}" in routes
        assert "/api/metrics/session/{session_id}/summary" in routes
        assert "/api/metrics/project/{project_id}" in routes
        assert "/api/metrics/project/{project_id}/summary" in routes
        assert "/api/metrics/projects" in routes


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
