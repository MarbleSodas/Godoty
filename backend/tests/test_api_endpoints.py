"""
Tests for API endpoints.

Migrated from test_agent.py
Tests cover:
- Health check endpoint
- Configuration endpoint
- Plan generation (non-streaming)
- Plan generation (streaming)
- Conversation reset endpoint
"""
import pytest
import httpx
import json
from fastapi.testclient import TestClient
from main import create_app

# Create app for testing
app = create_app()

@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch

@pytest_asyncio.fixture
async def async_client():
    """Create an async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.fixture
def mock_planning_agent():
    """Mock the planning agent for API tests."""
    mock_agent = MagicMock()
    
    # Mock plan_async
    async def mock_plan_async(prompt):
        return {
            "plan": f"Mock plan for: {prompt}",
            "message_id": "mock_msg_123",
            "metrics": {"total_tokens": 10}
        }
    mock_agent.plan_async = mock_plan_async
    
    # Mock plan_stream
    async def mock_plan_stream(prompt):
        yield {"type": "start", "data": {"message": "Starting"}}
        yield {"type": "data", "data": {"text": "Mock "}}
        yield {"type": "data", "data": {"text": "plan"}}
        yield {"type": "end", "data": {"stop_reason": "end_turn"}}
    mock_agent.plan_stream = mock_plan_stream
    
    # Mock other methods
    mock_agent.reset_conversation = MagicMock()
    mock_agent.model = MagicMock()
    mock_agent.model.get_config.return_value = {"model_id": "mock-model"}
    mock_agent.tools = []
    mock_agent.conversation_manager = MagicMock()
    
    return mock_agent

@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_endpoint(async_client, mock_planning_agent):
    """Test the health check endpoint."""
    with patch("api.agent_routes.get_planning_agent", return_value=mock_planning_agent):
        response = await async_client.get("/api/agent/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'healthy'
        assert 'agent_ready' in data

@pytest.mark.integration
@pytest.mark.asyncio
async def test_config_endpoint(async_client, mock_planning_agent):
    """Test the config endpoint."""
    # Mock _ensure_mcp_initialized as it's called in config endpoint
    mock_planning_agent._ensure_mcp_initialized = MagicMock()
    async def mock_ensure(): pass
    mock_planning_agent._ensure_mcp_initialized.side_effect = mock_ensure
    
    with patch("api.agent_routes.get_planning_agent", return_value=mock_planning_agent):
        response = await async_client.get("/api/agent/config")
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'success'
        assert 'config' in data

@pytest.mark.integration
@pytest.mark.asyncio
async def test_plan_endpoint_non_streaming(async_client, mock_planning_agent):
    """Test simple plan generation (non-streaming)."""
    prompt = "Create a brief plan for implementing a health bar in a 2D game."
    
    with patch("api.agent_routes.get_planning_agent", return_value=mock_planning_agent):
        response = await async_client.post(
            "/api/agent/plan",
            json={
                "prompt": prompt,
                "reset_conversation": True
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'success'
        assert 'plan' in data
        assert isinstance(data['plan'], str)
        assert len(data['plan']) > 0

@pytest.mark.integration
@pytest.mark.asyncio
async def test_plan_endpoint_streaming(async_client, mock_planning_agent):
    """Test streaming plan generation."""
    prompt = "Create a simple plan for adding a pause menu to a game."
    
    events_received = []
    
    with patch("api.agent_routes.get_planning_agent", return_value=mock_planning_agent):
        async with async_client.stream(
            "POST",
            "/api/agent/plan/stream",
            json={
                "prompt": prompt,
                "reset_conversation": True
            }
        ) as response:
            assert response.status_code == 200
            
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                
                # Parse SSE format
                if line.startswith("event: "):
                    event_type = line[7:]
                    events_received.append(event_type)
                elif line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
    
    # Verify we received events
    assert len(events_received) > 0
    # Should have at least start/end events
    assert any("start" in e for e in events_received)

@pytest.mark.integration
@pytest.mark.asyncio
async def test_reset_endpoint(async_client, mock_planning_agent):
    """Test conversation reset."""
    with patch("api.agent_routes.get_planning_agent", return_value=mock_planning_agent):
        response = await async_client.post("/api/agent/reset")
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'success'
        assert 'message' in data

@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_running(async_client, mock_planning_agent):
    """Test that server is accessible."""
    with patch("api.agent_routes.get_planning_agent", return_value=mock_planning_agent):
        response = await async_client.get("/api/health")
        assert response.status_code == 200
