"""
Tests for configuration API endpoints.

Tests cover:
- GET /api/agent/config - Retrieve configuration
- POST /api/agent/config - Update configuration
- Model validation
- API key security
- Error handling
"""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock
from main import create_app
from agents.config import AgentConfig

# Create app for testing
app = create_app()


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client():
    """Create an async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def reset_config():
    """Reset configuration to default values after test."""
    # Store original values
    original_planning = AgentConfig._planning_model
    original_executor = AgentConfig._executor_model
    original_key = AgentConfig._openrouter_api_key
    original_temp = AgentConfig.AGENT_TEMPERATURE
    original_tokens = AgentConfig.AGENT_MAX_TOKENS

    yield

    # Restore original values
    AgentConfig._planning_model = original_planning
    AgentConfig._executor_model = original_executor
    AgentConfig._openrouter_api_key = original_key
    AgentConfig.AGENT_TEMPERATURE = original_temp
    AgentConfig.AGENT_MAX_TOKENS = original_tokens


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_config_success(async_client):
    """Test GET /api/agent/config returns all required fields."""
    response = await async_client.get("/api/agent/config")
    assert response.status_code == 200

    data = response.json()

    # Check all required fields exist
    assert "available_models" in data
    assert "current_model" in data
    assert "temperature" in data
    assert "max_tokens" in data
    assert "has_api_key" in data
    assert "api_key_source" in data
    assert "metrics_enabled" in data

    # Validate available_models structure
    assert isinstance(data["available_models"], list)
    assert len(data["available_models"]) == 9  # Should match ALLOWED_MODELS count

    for model in data["available_models"]:
        assert "id" in model
        assert "name" in model
        assert "provider" in model


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_config_models_structure(async_client):
    """Test that available models have correct structure."""
    response = await async_client.get("/api/agent/config")
    assert response.status_code == 200

    data = response.json()
    models = data["available_models"]

    # Check specific models exist
    model_ids = [m["id"] for m in models]
    assert "anthropic/claude-sonnet-4.5" in model_ids
    assert "anthropic/claude-opus-4.5" in model_ids
    assert "x-ai/grok-4.1-fast" in model_ids
    assert "x-ai/grok-4.1-fast:free" in model_ids
    assert "google/gemini-3-pro-preview" in model_ids

    # Check provider extraction works
    sonnet = next(m for m in models if m["id"] == "anthropic/claude-sonnet-4.5")
    assert sonnet["provider"] == "Anthropic"
    assert sonnet["name"] == "Sonnet 4.5"

    # Check new models
    opus = next(m for m in models if m["id"] == "anthropic/claude-opus-4.5")
    assert opus["provider"] == "Anthropic"
    assert opus["name"] == "Opus 4.5"

    grok_free = next(m for m in models if m["id"] == "x-ai/grok-4.1-fast:free")
    assert grok_free["provider"] == "xAI"
    assert grok_free["name"] == "Grok 4.1 Fast (Free)"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_config_api_key_not_exposed(async_client):
    """Test that API key is never exposed in response."""
    response = await async_client.get("/api/agent/config")
    assert response.status_code == 200

    data = response.json()

    # Should NOT contain actual api_key field
    assert "api_key" not in data
    assert "openrouter_api_key" not in data

    # Should contain boolean has_api_key instead
    assert "has_api_key" in data
    assert isinstance(data["has_api_key"], bool)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_config_valid_model(async_client, reset_config):
    """Test POST /api/agent/config with valid model."""
    response = await async_client.post(
        "/api/agent/config",
        json={"model": "anthropic/claude-sonnet-4.5"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "message" in data

    # Verify the model was updated
    assert AgentConfig._planning_model == "anthropic/claude-sonnet-4.5"
    assert AgentConfig._executor_model == "anthropic/claude-sonnet-4.5"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_config_invalid_model(async_client):
    """Test POST /api/agent/config with invalid model."""
    response = await async_client.post(
        "/api/agent/config",
        json={"model": "invalid/model-name"}
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_config_temperature_validation(async_client):
    """Test temperature validation (must be 0.0-2.0)."""
    # Test temperature too high
    response = await async_client.post(
        "/api/agent/config",
        json={"temperature": 3.0}
    )
    assert response.status_code == 422  # Pydantic validation error

    # Test temperature too low
    response = await async_client.post(
        "/api/agent/config",
        json={"temperature": -0.5}
    )
    assert response.status_code == 422

    # Test valid temperature
    response = await async_client.post(
        "/api/agent/config",
        json={"temperature": 1.0}
    )
    assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_config_max_tokens_validation(async_client):
    """Test max_tokens validation (must be 1-32000)."""
    # Test tokens too high
    response = await async_client.post(
        "/api/agent/config",
        json={"max_tokens": 50000}
    )
    assert response.status_code == 422

    # Test tokens too low
    response = await async_client.post(
        "/api/agent/config",
        json={"max_tokens": 0}
    )
    assert response.status_code == 422

    # Test valid tokens
    response = await async_client.post(
        "/api/agent/config",
        json={"max_tokens": 2000}
    )
    assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_config_api_key_update(async_client, reset_config):
    """Test API key update via POST."""
    test_key = "sk-test-key-12345"

    response = await async_client.post(
        "/api/agent/config",
        json={"api_key": test_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Verify key was updated (but not exposed in response)
    assert AgentConfig._openrouter_api_key == test_key

    # Verify GET still doesn't expose the key
    get_response = await async_client.get("/api/agent/config")
    get_data = get_response.json()
    assert "api_key" not in get_data
    assert get_data["has_api_key"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_config_multiple_fields(async_client, reset_config):
    """Test updating multiple configuration fields at once."""
    response = await async_client.post(
        "/api/agent/config",
        json={
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.5,
            "max_tokens": 3000
        }
    )

    assert response.status_code == 200

    # Verify all updates applied
    assert AgentConfig._planning_model == "anthropic/claude-haiku-4.5"
    assert AgentConfig.AGENT_TEMPERATURE == 0.5
    assert AgentConfig.AGENT_MAX_TOKENS == 3000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_config_empty_body(async_client):
    """Test POST with empty body (should succeed but change nothing)."""
    original_model = AgentConfig._planning_model

    response = await async_client.post(
        "/api/agent/config",
        json={}
    )

    assert response.status_code == 200
    # Model should remain unchanged
    assert AgentConfig._planning_model == original_model


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_key_source_detection(async_client, reset_config):
    """Test that api_key_source correctly identifies environment vs override."""
    import os

    # Case 1: Environment key
    env_key = os.getenv("OPENROUTER_API_KEY", "")
    if env_key:
        AgentConfig._openrouter_api_key = env_key
        response = await async_client.get("/api/agent/config")
        data = response.json()
        assert data["api_key_source"] == "environment"

    # Case 2: User override
    AgentConfig._openrouter_api_key = "sk-override-key"
    response = await async_client.get("/api/agent/config")
    data = response.json()
    assert data["api_key_source"] == "user_override"

    # Case 3: No key
    AgentConfig._openrouter_api_key = ""
    response = await async_client.get("/api/agent/config")
    data = response.json()
    assert data["api_key_source"] == "none"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_config_persistence(async_client, reset_config):
    """Test that configuration changes persist via save_config."""
    # Update model
    await async_client.post(
        "/api/agent/config",
        json={"model": "minimax/minimax-m2"}
    )

    # Verify it persisted by checking the class variable
    assert AgentConfig._planning_model == "minimax/minimax-m2"

    # Verify it shows in GET
    response = await async_client.get("/api/agent/config")
    data = response.json()
    assert data["current_model"] == "minimax/minimax-m2"


@pytest.mark.integration
def test_config_routes_registered(client):
    """Test that config routes are properly registered with the app."""
    # Check GET endpoint exists
    response = client.get("/api/agent/config")
    assert response.status_code == 200

    # Check POST endpoint exists
    response = client.post("/api/agent/config", json={})
    assert response.status_code == 200
