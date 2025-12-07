from typing import Any, AsyncGenerator, Optional
from strands.models.openai import OpenAIModel
from strands.types.streaming import StreamEvent
from strands.types.content import Messages
import logging

logger = logging.getLogger(__name__)


class GodotyOpenRouterModel(OpenAIModel):
    """
    OpenRouter model with usage tracking that captures cost directly from API responses.
    
    Supports two modes:
    - Direct mode: Requests go directly to OpenRouter (default, for development)
    - Proxy mode: Requests route through Supabase Edge Function for monetization
    """
    
    def __init__(
        self, 
        api_key: str, 
        model_id: str, 
        site_url: str, 
        app_name: str,
        use_proxy: bool = False,
        proxy_url: Optional[str] = None,
        proxy_token: Optional[str] = None
    ):
        """
        Initialize the OpenRouter model.
        
        Args:
            api_key: OpenRouter API key (used in direct mode)
            model_id: Model identifier (e.g., 'anthropic/claude-3.5-sonnet')
            site_url: Application URL for OpenRouter attribution
            app_name: Application name for OpenRouter attribution
            use_proxy: If True, route through Supabase proxy for billing
            proxy_url: Supabase Edge Function URL for proxy mode
            proxy_token: Supabase JWT token for proxy authentication
        """
        self.use_proxy = use_proxy
        self.proxy_token = proxy_token
        
        # Determine base URL and headers based on mode
        if use_proxy and proxy_url:
            # Proxy mode: route through Supabase Edge Function
            base_url = proxy_url
            # In proxy mode, we use a dummy API key since auth is via JWT
            effective_api_key = "proxy-auth"
            headers = {}  # Auth header added per-request
            logger.info(f"[MODEL] Proxy mode enabled, routing to: {proxy_url}")
        else:
            # Direct mode: connect directly to OpenRouter
            base_url = "https://openrouter.ai/api/v1"
            effective_api_key = api_key
            headers = {
                "HTTP-Referer": site_url,
                "X-Title": app_name,
            }
            logger.info("[MODEL] Direct mode, connecting to OpenRouter")
        
        super().__init__(
            client_args={
                "api_key": effective_api_key,
                "base_url": base_url,
                "default_headers": headers
            },
            model_id=model_id,
            params={
                "stream_options": {"include_usage": True}
            }
        )
        self.model_id = model_id
        # Track accumulated usage for this model instance
        self._last_usage = None
    
    def update_proxy_token(self, token: str):
        """Update the proxy authentication token."""
        self.proxy_token = token
        logger.debug("[MODEL] Proxy token updated")

    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list] = None,
        system_prompt: Optional[str] = None,
        *,
        tool_choice: Optional[Any] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream with OpenRouter usage tracking injected into events."""
        
        self._last_usage = None
        
        # If in proxy mode, inject the auth header
        if self.use_proxy and self.proxy_token:
            # The OpenAI client should use this header for requests
            if hasattr(self, '_client') and self._client:
                self._client.default_headers["Authorization"] = f"Bearer {self.proxy_token}"
        
        async for event in super().stream(messages, tool_specs, system_prompt, tool_choice=tool_choice, **kwargs):
            # Check if this event contains usage data from OpenRouter
            # The OpenAI SDK puts usage in the 'usage' field of the chunk
            if isinstance(event, dict):
                # Check for usage in different possible locations
                usage = None
                
                # Check for direct usage field (from OpenRouter with include_usage)
                if "usage" in event:
                    usage = event["usage"]
                
                # Check in messageStop event
                elif "messageStop" in event:
                    usage = event.get("messageStop", {}).get("usage")
                
                # Check for metadata.usage (some SDK versions)
                elif "metadata" in event and isinstance(event["metadata"], dict):
                    usage = event["metadata"].get("usage")
                
                if usage and isinstance(usage, dict):
                    # Store the usage data
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
                    # OpenRouter provides cost directly, also check for total_cost
                    cost = usage.get("cost", usage.get("total_cost", 0.0))
                    
                    self._last_usage = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "cost": cost,
                        "model_id": self.model_id
                    }
                    
                    logger.info(f"[OPENROUTER] Usage captured: {prompt_tokens} in, {completion_tokens} out, cost=${cost:.6f}")
                    
                    # Inject usage into the event for downstream processing
                    event["openrouter_usage"] = self._last_usage
            
            yield event
        
        # After stream completes, yield a final metrics event if we have usage data
        if self._last_usage:
            logger.info(f"[OPENROUTER] Final usage: {self._last_usage}")
            yield {
                "openrouter_metrics": self._last_usage
            }

