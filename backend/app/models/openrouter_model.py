"""
Custom OpenRouter model provider for Strands integration.

Extends Strands OpenAI model to work with OpenRouter API while maintaining
compatibility with Strands framework patterns.
"""

import logging
from typing import Any, Dict, List, Optional, AsyncGenerator

from openai import OpenAI, AsyncOpenAI
from strands.models.openai import OpenAIModel

from app.config import settings

logger = logging.getLogger(__name__)


class StrandsOpenRouterModel(OpenAIModel):
    """
    Custom OpenRouter model provider extending Strands OpenAI model.

    Provides OpenRouter-specific functionality including:
    - Custom headers for OpenRouter ecosystem
    - Proper token usage tracking
    - Cost calculation integration
    - Error handling for OpenRouter-specific responses
    """

    def __init__(self, model_id: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        """
        Initialize OpenRouter model provider.

        Args:
            model_id: OpenRouter model identifier (defaults to DEFAULT_GODOTY_MODEL)
            api_key: OpenRouter API key (defaults to environment variable)
            **kwargs: Additional model parameters
        """
        # Use defaults from settings if not provided
        self.model_id = model_id or settings.default_godoty_model
        self.api_key = api_key or settings.openrouter_api_key

        # Initialize OpenRouter clients with custom configuration
        client_args = {
            "api_key": self.api_key,
            "base_url": settings.openrouter_base_url,
            "default_headers": settings.openrouter_headers,
            "timeout": settings.openrouter_timeout,
        }

        # Initialize OpenAI-compatible clients
        self.client = OpenAI(**client_args)
        self.async_client = AsyncOpenAI(**client_args)

        # Initialize parent OpenAI model
        super().__init__(
            model=self.model_id,
            api_key=self.api_key,
            base_url=settings.openrouter_base_url,
            default_headers=settings.openrouter_headers,
            params={"stream_options": {"include_usage": True}},
            **kwargs
        )

        logger.info(f"Initialized OpenRouter model: {self.model_id}")

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion with OpenRouter-specific handling.

        Extends the base streaming to include:
        - Proper usage token extraction
        - OpenRouter-specific error handling
        - Cost calculation metadata

        Args:
            messages: List of chat messages
            **kwargs: Additional completion parameters

        Yields:
            Stream event dictionaries compatible with Strands
        """
        try:
            # Ensure stream options are set for usage tracking
            kwargs["stream_options"] = {"include_usage": True}

            # Call OpenAI-compatible streaming
            async for chunk in super().stream_chat_completion(messages, **kwargs):
                # Add OpenRouter-specific metadata if available
                if chunk.get("type") == "metadata" and "usage" in chunk:
                    usage = chunk["usage"]
                    logger.debug(f"Token usage: {usage}")

                yield chunk

        except Exception as e:
            logger.error(f"OpenRouter streaming error: {e}")
            # Convert to Strands-compatible error event
            yield {
                "type": "error",
                "error": {
                    "type": "openrouter_error",
                    "message": str(e),
                    "recoverable": True
                }
            }

    async def get_model_pricing(self) -> Dict[str, float]:
        """
        Get current pricing information for the model from OpenRouter.

        Returns:
            Dictionary with prompt and completion token costs per 1M tokens
        """
        try:
            # This would integrate with OpenRouter pricing API
            # For now, return default pricing structure
            return {
                "prompt_cost_per_1m": 0.0,  # Will be populated from API
                "completion_cost_per_1m": 0.0,
                "currency": "USD"
            }
        except Exception as e:
            logger.warning(f"Failed to fetch pricing: {e}")
            # Return default fallback pricing
            return {
                "prompt_cost_per_1m": 0.001,  # $1 per 1M tokens
                "completion_cost_per_1m": 0.002,  # $2 per 1M tokens
                "currency": "USD"
            }

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Calculate cost based on token usage.

        Args:
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens used

        Returns:
            Total cost in USD
        """
        # Use default pricing (will be enhanced with real pricing API)
        prompt_cost = (prompt_tokens / 1_000_000) * 0.001
        completion_cost = (completion_tokens / 1_000_000) * 0.002
        return prompt_cost + completion_cost

    def validate_model_id(self, model_id: str) -> bool:
        """
        Validate if a model ID is supported by OpenRouter.

        Args:
            model_id: Model identifier to validate

        Returns:
            True if model is valid, False otherwise
        """
        # Basic validation - can be enhanced with OpenRouter model list API
        return "/" in model_id and len(model_id) > 0