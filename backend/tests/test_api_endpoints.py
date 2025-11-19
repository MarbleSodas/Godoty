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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_endpoint():
    """Test the health check endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/api/agent/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'healthy'
        assert 'agent_ready' in data
        assert 'model' in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_config_endpoint():
    """Test the config endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/api/agent/config")
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'success'
        assert 'config' in data
        assert 'model_id' in data['config']
        assert 'tools' in data['config']
        assert isinstance(data['config']['tools'], list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_plan_endpoint_non_streaming():
    """Test simple plan generation (non-streaming)."""
    prompt = "Create a brief plan for implementing a health bar in a 2D game."
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://localhost:8000/api/agent/plan",
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
async def test_plan_endpoint_streaming():
    """Test streaming plan generation."""
    prompt = "Create a simple plan for adding a pause menu to a game."
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        events_received = []
        
        async with client.stream(
            "POST",
            "http://localhost:8000/api/agent/plan/stream",
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
async def test_reset_endpoint():
    """Test conversation reset."""
    async with httpx.AsyncClient() as client:
        response = await client.post("http://localhost:8000/api/agent/reset")
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'success'
        assert 'message' in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_running():
    """Test that server is accessible."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get("http://localhost:8000/api/health")
        assert response.status_code == 200
