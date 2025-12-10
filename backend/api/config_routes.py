"""
Configuration API routes.
Provides endpoints for managing application configuration.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from config_manager import get_config

router = APIRouter(prefix="/api/config", tags=["config"])

class ConfigUpdate(BaseModel):
    """Model for configuration updates."""
    openrouter_api_key: Optional[str] = None
    default_model: Optional[str] = None
    app_settings: Optional[Dict[str, Any]] = None

class ConfigResponse(BaseModel):
    """Model for configuration response."""
    openrouter_api_key_set: bool = Field(..., description="Whether API key is configured")
    default_model: str
    app_settings: Dict[str, Any]
    is_configured: bool = Field(..., description="Whether app is fully configured")

class ConfigUpdateResponse(BaseModel):
    """Model for configuration update response."""
    success: bool
    message: str
    config: Optional[ConfigResponse] = None

@router.get("/status", response_model=ConfigResponse)
async def get_config_status():
    """
    Get current configuration status (API key is masked).
    """
    config = get_config()

    return ConfigResponse(
        openrouter_api_key_set=bool(config.openrouter_api_key.strip()),
        default_model=config.default_model,
        app_settings=config.get('app_settings', {}),
        is_configured=config.is_configured
    )

@router.get("/", response_model=Dict[str, Any])
async def get_full_config():
    """
    Get full configuration (includes masked API key for display).
    """
    config = get_config()
    full_config = config.get_all()

    # Mask API key for security
    if full_config.get('openrouter_api_key'):
        key = full_config['openrouter_api_key']
        if len(key) > 8:
            full_config['openrouter_api_key'] = key[:4] + '*' * (len(key) - 8) + key[-4:]
        else:
            full_config['openrouter_api_key'] = '*' * len(key)

    return full_config

@router.post("/", response_model=ConfigUpdateResponse)
async def update_config(updates: ConfigUpdate):
    """
    Update configuration values.
    """
    config = get_config()

    try:
        # Update individual fields if provided
        if updates.openrouter_api_key is not None:
            config.openrouter_api_key = updates.openrouter_api_key

        if updates.default_model is not None:
            config.default_model = updates.default_model

        if updates.app_settings is not None:
            current_settings = config.get('app_settings', {})
            current_settings.update(updates.app_settings)
            config.set('app_settings', current_settings)

        # Get updated status
        status = ConfigResponse(
            openrouter_api_key_set=bool(config.openrouter_api_key.strip()),
            default_model=config.default_model,
            app_settings=config.get('app_settings', {}),
            is_configured=config.is_configured
        )

        return ConfigUpdateResponse(
            success=True,
            message="Configuration updated successfully",
            config=status
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")

@router.post("/reset", response_model=ConfigUpdateResponse)
async def reset_config():
    """
    Reset configuration to defaults.
    """
    config = get_config()

    try:
        config.reset_to_defaults()

        status = ConfigResponse(
            openrouter_api_key_set=False,
            default_model=config.default_model,
            app_settings=config.get('app_settings', {}),
            is_configured=False
        )

        return ConfigUpdateResponse(
            success=True,
            message="Configuration reset to defaults",
            config=status
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset configuration: {str(e)}")

@router.get("/models", response_model=Dict[str, Any])
async def get_available_models():
    """
    Get list of available OpenRouter models.
    """
    # Popular models list - can be expanded
    models = {
        "recommended": [
            {
                "id": "x-ai/grok-2-1212",
                "name": "Grok 2 (Latest)",
                "provider": "xAI",
                "context_length": 131072,
                "pricing": {"prompt": 0.000002, "completion": 0.00001}
            },
            {
                "id": "anthropic/claude-3.5-sonnet",
                "name": "Claude 3.5 Sonnet",
                "provider": "Anthropic",
                "context_length": 200000,
                "pricing": {"prompt": 0.000003, "completion": 0.000015}
            },
            {
                "id": "openai/gpt-4-turbo",
                "name": "GPT-4 Turbo",
                "provider": "OpenAI",
                "context_length": 128000,
                "pricing": {"prompt": 0.00001, "completion": 0.00003}
            }
        ],
        "free": [
            {
                "id": "x-ai/grok-2-1212:free",
                "name": "Grok 2 (Free)",
                "provider": "xAI",
                "context_length": 131072,
                "pricing": {"prompt": 0, "completion": 0}
            },
            {
                "id": "google/gemini-2.0-flash-exp:free",
                "name": "Gemini 2.0 Flash (Free)",
                "provider": "Google",
                "context_length": 1000000,
                "pricing": {"prompt": 0, "completion": 0}
            }
        ],
        "budget": [
            {
                "id": "google/gemini-flash-1.5",
                "name": "Gemini 1.5 Flash",
                "provider": "Google",
                "context_length": 1000000,
                "pricing": {"prompt": 0.000000075, "completion": 0.0000003}
            },
            {
                "id": "anthropic/claude-3-haiku",
                "name": "Claude 3 Haiku",
                "provider": "Anthropic",
                "context_length": 200000,
                "pricing": {"prompt": 0.00000025, "completion": 0.00000125}
            }
        ]
    }

    return models
