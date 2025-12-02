"""
Model Management Service

Handles fetching and managing available models from OpenRouter API.
Provides model validation and default model management functionality.
"""

from typing import List, Dict, Any, Optional
import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class ModelService:
    """Service for managing AI models from OpenRouter API."""

    def __init__(self):
        self.openrouter_base_url = "https://openrouter.ai/api/v1"
        self._cached_models: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_ttl = 3600  # Cache models for 1 hour

    async def get_available_models(self) -> List[Dict[str, Any]]:
        """
        Fetch available models from OpenRouter API with caching.

        Returns:
            List of model dictionaries with id, name, description, etc.
        """
        import time

        # Check cache first
        if (self._cached_models and self._cache_timestamp and
            time.time() - self._cache_timestamp < self._cache_ttl):
            logger.debug("Using cached model list")
            return self._cached_models

        try:
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.app_url if settings.app_url else "http://localhost:8000",
                "X-Title": "Godoty"
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.openrouter_base_url}/models",
                    headers=headers
                )
                response.raise_for_status()

                data = response.json()

                if "data" not in data or not isinstance(data["data"], list):
                    raise ValueError("Invalid response format from OpenRouter API")

                # Transform models to our format
                models = []
                for model in data["data"]:
                    transformed_model = {
                        "id": model["id"],
                        "name": model["name"],
                        "description": model.get("description", ""),
                        "pricing": model.get("pricing", {}),
                        "context_length": model.get("context_length", 0)
                    }
                    models.append(transformed_model)

                # Cache the results
                self._cached_models = models
                self._cache_timestamp = time.time()

                logger.info(f"Successfully fetched {len(models)} models from OpenRouter")
                return models

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching models: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Failed to fetch models: HTTP {e.response.status_code}")
        except httpx.TimeoutException:
            logger.error("Timeout fetching models from OpenRouter")
            raise Exception("Request timeout while fetching models")
        except Exception as e:
            logger.error(f"Error fetching models: {str(e)}")
            raise Exception(f"Failed to fetch models: {str(e)}")

    async def validate_model_id(self, model_id: str) -> bool:
        """
        Validate if a model ID exists in the available models.

        Args:
            model_id: The model ID to validate

        Returns:
            True if model exists, False otherwise
        """
        try:
            models = await self.get_available_models()
            return any(model["id"] == model_id for model in models)
        except Exception as e:
            logger.error(f"Error validating model ID {model_id}: {str(e)}")
            return False

    async def get_model_details(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific model.

        Args:
            model_id: The model ID to get details for

        Returns:
            Model details dictionary or None if not found
        """
        try:
            models = await self.get_available_models()
            for model in models:
                if model["id"] == model_id:
                    return model
            return None
        except Exception as e:
            logger.error(f"Error getting model details for {model_id}: {str(e)}")
            return None

    async def set_default_model(self, model_id: str) -> bool:
        """
        Set the default model (validation only - actual config update happens elsewhere).

        Args:
            model_id: The model ID to set as default

        Returns:
            True if model is valid and can be set, False otherwise
        """
        try:
            is_valid = await self.validate_model_id(model_id)
            if is_valid:
                logger.info(f"Default model validated: {model_id}")
                return True
            else:
                logger.warning(f"Invalid model ID attempted: {model_id}")
                return False
        except Exception as e:
            logger.error(f"Error setting default model {model_id}: {str(e)}")
            return False

    def get_fallback_models(self) -> List[Dict[str, Any]]:
        """
        Get fallback models when API is unavailable.

        Returns:
            List of basic fallback model dictionaries
        """
        return [
            {
                "id": "x-ai/grok-4.1-fast:free",
                "name": "Grok 4.1 Fast (Free)",
                "description": "Fast and free model from xAI",
                "pricing": {"prompt": 0, "completion": 0},
                "context_length": 8192
            },
            {
                "id": "anthropic/claude-3.5-sonnet",
                "name": "Claude 3.5 Sonnet",
                "description": "Advanced reasoning model from Anthropic",
                "pricing": {"prompt": 0.003, "completion": 0.015},
                "context_length": 200000
            },
            {
                "id": "openai/gpt-4o",
                "name": "GPT-4o",
                "description": "Multimodal model from OpenAI",
                "pricing": {"prompt": 0.005, "completion": 0.015},
                "context_length": 128000
            }
        ]

    def clear_cache(self) -> None:
        """Clear the model cache."""
        self._cached_models = None
        self._cache_timestamp = None
        logger.info("Model cache cleared")