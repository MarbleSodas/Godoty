from typing import Any, AsyncGenerator, Optional, List, Dict
from strands.models.openai import OpenAIModel
from strands.types.streaming import StreamEvent
from strands.types.content import Messages
import logging

logger = logging.getLogger(__name__)

class GodotyOpenRouterModel(OpenAIModel):
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
            # Enable OpenRouter usage accounting for accurate cost tracking
            params={
                "stream_options": {"include_usage": True}  # This enables usage tracking in streaming responses
            }
        )
        self.model_id = model_id

    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list] = None,
        system_prompt: Optional[str] = None,
        *,
        tool_choice: Optional[Any] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
          
        # We wrap the parent stream to inspect events
        async for event in super().stream(messages, tool_specs, system_prompt, tool_choice=tool_choice, **kwargs):
            yield event
              
            # Check for metrics event with usage data
            # OpenRouter will include cost in usage when usage accounting is enabled
            if "metrics" in event:
                usage = event["metrics"].get("usage", {})
                if usage:
                    # Extract cost directly from OpenRouter response
                    # This is more accurate than local calculation
                    cost = usage.get("cost")
                    
                    if cost is not None:
                        # Inject cost into the event for downstream processing
                        event["metrics"]["openrouter_cost"] = float(cost)
                        logger.debug(f"OpenRouter cost: ${cost:.6f} for {usage.get('prompt_tokens', 0)} in / {usage.get('completion_tokens', 0)} out")
                    else:
                        # Log warning if cost is missing (e.g., free models)
                        logger.warning(f"No cost data from OpenRouter for model {self.model_id}, defaulting to $0.00")
                        event["metrics"]["openrouter_cost"] = 0.0
