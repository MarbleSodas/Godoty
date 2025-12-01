"""
Configuration API routes.

Provides endpoints for managing agent configuration including:
- Available models
- Current model selection
- API key management (secure)
- Agent parameters (temperature, max_tokens)
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.config import AgentConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["configuration"])


# Pydantic Models
class AvailableModel(BaseModel):
    """Model information for frontend display."""
    id: str
    name: str
    provider: str


class ConfigResponse(BaseModel):
    """Complete configuration response."""
    available_models: List[AvailableModel]
    current_model: str
    temperature: float
    max_tokens: int
    has_api_key: bool
    api_key_source: str  # "environment" or "user_override"
    metrics_enabled: bool


class ConfigUpdateRequest(BaseModel):
    """Configuration update request."""
    model: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)


class ConfigUpdateResponse(BaseModel):
    """Configuration update response."""
    success: bool
    message: str


# Helper Functions
def _extract_provider(model_id: str) -> str:
    """Extract provider name from model ID."""
    provider_map = {
        "google/": "Google",
        "x-ai/": "xAI",
        "anthropic/": "Anthropic",
        "minimax/": "Minimax",
        "openai/": "OpenAI",
        "z-ai/": "Zhipu AI",
        "meta-llama/": "Meta"
    }

    for prefix, provider in provider_map.items():
        if model_id.startswith(prefix):
            return provider

    # Default: capitalize first part before slash
    if "/" in model_id:
        return model_id.split("/")[0].capitalize()
    return "Unknown"


def _get_api_key_source() -> str:
    """Determine the source of the API key."""
    import os

    # Check if key is from environment or config file
    env_key = os.getenv("OPENROUTER_API_KEY", "")
    current_key = AgentConfig._openrouter_api_key

    if not current_key:
        return "none"
    elif current_key == env_key:
        return "environment"
    else:
        return "user_override"


# API Endpoints
@router.get("/config", response_model=ConfigResponse)
async def get_config():
    """
    Get current agent configuration.

    Returns:
        ConfigResponse: Complete configuration including available models,
                       current settings, and API key status (without exposing the key)
    """
    try:
        # Build available models list
        available_models = []
        for name, model_id in AgentConfig.ALLOWED_MODELS.items():
            available_models.append(AvailableModel(
                id=model_id,
                name=name,
                provider=_extract_provider(model_id)
            ))

        # Get current configuration
        model_config = AgentConfig.get_model_config()

        # Determine API key status (NEVER expose the actual key)
        has_api_key = bool(AgentConfig._openrouter_api_key)
        api_key_source = _get_api_key_source()

        # Build response
        response = ConfigResponse(
            available_models=available_models,
            current_model=model_config["planning_model"],
            temperature=model_config["temperature"],
            max_tokens=model_config["max_tokens"],
            has_api_key=has_api_key,
            api_key_source=api_key_source,
            metrics_enabled=AgentConfig.ENABLE_METRICS_TRACKING
        )

        logger.info(
            f"Configuration retrieved: model={response.current_model}, "
            f"has_key={has_api_key}, source={api_key_source}"
        )

        return response

    except Exception as e:
        logger.error(f"Error retrieving configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration: {str(e)}")


@router.post("/config", response_model=ConfigUpdateResponse)
async def update_config(request: ConfigUpdateRequest):
    """
    Update agent configuration.

    Args:
        request: Configuration update request with optional fields

    Returns:
        ConfigUpdateResponse: Success status and message

    Raises:
        HTTPException: If validation fails or update errors occur
    """
    try:
        # Validate model if provided
        if request.model:
            allowed_model_ids = list(AgentConfig.ALLOWED_MODELS.values())
            if request.model not in allowed_model_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid model '{request.model}'. Must be one of: {', '.join(allowed_model_ids)}"
                )

        # Update configuration
        # Note: AgentConfig.update_config() handles both planning and executor models
        # For now, we're treating them as the same since the frontend uses a single model selection
        update_kwargs = {}

        if request.model:
            update_kwargs["planning_model"] = request.model
            update_kwargs["executor_model"] = request.model  # Keep in sync

        if request.api_key is not None:
            update_kwargs["api_key"] = request.api_key
            # Log with masked key for security
            if request.api_key:
                logger.info(f"API key updated: {request.api_key[:8]}...")
            else:
                logger.info("API key cleared")

        # Update the configuration
        AgentConfig.update_config(**update_kwargs)

        # Update temperature and max_tokens if provided
        # Note: These are class variables, not saved to config file currently
        # Consider if you want to persist these or keep them as environment-only
        if request.temperature is not None:
            AgentConfig.AGENT_TEMPERATURE = request.temperature
            logger.info(f"Temperature updated to {request.temperature}")

        if request.max_tokens is not None:
            AgentConfig.AGENT_MAX_TOKENS = request.max_tokens
            logger.info(f"Max tokens updated to {request.max_tokens}")

        return ConfigUpdateResponse(
            success=True,
            message="Configuration updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")
