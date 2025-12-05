from typing import Any, AsyncGenerator, Optional
from strands.models.openai import OpenAIModel
from strands.types.streaming import StreamEvent
from strands.types.content import Messages
import logging

logger = logging.getLogger(__name__)


class GodotyOpenRouterModel(OpenAIModel):
    """OpenRouter model with usage tracking that captures cost directly from API responses."""
    
    def __init__(self, api_key: str, model_id: str, site_url: str, app_name: str):
        super().__init__(
            client_args={
                "api_key": api_key,
                "base_url": "https://openrouter.ai/api/v1",
                "default_headers": {
                    "HTTP-Referer": site_url,
                    "X-Title": app_name,
                }
            },
            model_id=model_id,
            params={
                "stream_options": {"include_usage": True}
            }
        )
        self.model_id = model_id
        # Track accumulated usage for this model instance
        self._last_usage = None

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
                    cost = usage.get("cost", 0.0)  # OpenRouter provides cost directly
                    
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
