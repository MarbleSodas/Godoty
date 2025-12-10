"""
Godoty OpenRouter Model Factory.

This module provides the model factory for creating OpenRouter models
compatible with Agno agents, supporting both direct and Supabase proxy modes.
"""

from typing import Optional, Dict, Any
import logging

from agno.models.openrouter import OpenRouter

logger = logging.getLogger(__name__)


class GodotyOpenRouterConfig:
    """Configuration for the Godoty OpenRouter model."""
    
    def __init__(
        self,
        api_key: str,
        model_id: str,
        app_name: str = "Godoty",
        use_proxy: bool = False,
        proxy_url: Optional[str] = None,
        proxy_token: Optional[str] = None,
    ):
        """
        Initialize OpenRouter configuration.
        
        Args:
            api_key: OpenRouter API key (used in direct mode)
            model_id: Model identifier (e.g., 'anthropic/claude-3.5-sonnet')
            app_name: Application name for OpenRouter attribution
            use_proxy: If True, route through Supabase proxy for billing
            proxy_url: Supabase Edge Function URL for proxy mode
            proxy_token: Supabase JWT token for proxy authentication
        """
        self.api_key = api_key
        self.model_id = model_id
        self.app_name = app_name
        self.use_proxy = use_proxy
        self.proxy_url = proxy_url
        self.proxy_token = proxy_token


def create_godoty_model(config: GodotyOpenRouterConfig) -> OpenRouter:
    """
    Create an Agno OpenRouter model with Godoty configuration.
    
    Supports two modes:
    - Direct mode: Requests go directly to OpenRouter (default, for development)
    - Proxy mode: Requests route through Supabase Edge Function for monetization
    
    Metrics (input_tokens, output_tokens, cost) are automatically captured
    by Agno from OpenRouter API responses and available in RunResponse.metrics.
    
    Args:
        config: GodotyOpenRouterConfig with model settings
        
    Returns:
        Configured OpenRouter model instance
    """
    # Build extra headers based on mode
    extra_headers: Dict[str, str] = {}
    
    if config.use_proxy and config.proxy_url:
        # Proxy mode: route through Supabase Edge Function
        base_url = config.proxy_url
        # In proxy mode, auth is via JWT in Authorization header
        api_key = "proxy-auth"  # Placeholder, actual auth via header
        if config.proxy_token:
            extra_headers["Authorization"] = f"Bearer {config.proxy_token}"
        logger.info(f"[MODEL] Proxy mode enabled, routing to: {config.proxy_url}")
    else:
        # Direct mode: connect directly to OpenRouter
        base_url = "https://openrouter.ai/api/v1"
        api_key = config.api_key
        logger.info("[MODEL] Direct mode, connecting to OpenRouter")
    
    # Create Agno OpenRouter model
    model = OpenRouter(
        id=config.model_id,
        api_key=api_key,
        base_url=base_url,
        app_name=config.app_name,
        extra_headers=extra_headers if extra_headers else None,
    )
    
    # Store config reference for token refresh
    model._godoty_config = config  # type: ignore
    
    return model


def update_model_proxy_token(model: OpenRouter, token: str) -> OpenRouter:
    """
    Update the proxy authentication token on an existing model.
    
    Since Agno models are typically stateless per-run, this creates
    a new model instance with the updated token.
    
    Args:
        model: Existing OpenRouter model
        token: New Supabase JWT token
        
    Returns:
        New OpenRouter model with updated token
    """
    config = getattr(model, '_godoty_config', None)
    if config is None:
        logger.warning("[MODEL] No Godoty config found on model, cannot update token")
        return model
    
    # Update config with new token
    config.proxy_token = token
    
    # Create new model with updated config
    return create_godoty_model(config)


# Backwards compatibility alias
GodotyOpenRouterModel = OpenRouter

