from typing import Any, AsyncGenerator, Optional, List, Dict, Callable
from strands.models.openai import OpenAIModel
from strands.types.streaming import StreamEvent
from strands.types.content import Messages
from .pricing import PricingService
import logging

logger = logging.getLogger(__name__)

class GodotyOpenRouterModel(OpenAIModel):
    def __init__(
        self,
        api_key: str,
        model_id: str,
        site_url: str,
        app_name: str,
        metrics_callback: Optional[Callable] = None,
        **kwargs
    ):
        # Store model_id and metrics callback for cost tracking
        self.model_id = model_id
        self.metrics_callback = metrics_callback

        # Construct the client arguments for the underlying OpenAI client
        client_args = {
            "api_key": api_key,
            "base_url": "https://openrouter.ai/api/v1",
            "default_headers": {
                "HTTP-Referer": site_url,
                "X-Title": app_name,
            }
        }

        # Merge any other client_args passed in kwargs
        if "client_args" in kwargs:
            client_args.update(kwargs.pop("client_args"))

        # Initialize the parent class with the configured client
        super().__init__(
            client_args=client_args,
            model_id=model_id,
            # Critical: This param tells OpenAI/OpenRouter to send usage data
            params={"stream_options": {"include_usage": True}},
            **kwargs
        )

    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[List] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        usage_received = False  # Track if usage data arrives

        # We wrap the parent stream to inspect events
        async for event in super().stream(messages, tool_specs, system_prompt, **kwargs):
            yield event

            # Check for metrics event
            # Note: Strands SDK structure puts usage in "metrics" key of the event
            if "metrics" in event:
                usage = event["metrics"].get("usage", {})
                if usage:
                    usage_received = True
                    input_tok = usage.get("prompt_tokens", 0)
                    output_tok = usage.get("completion_tokens", 0)

                    # Priority 1: Use actual_cost from OpenRouter if available
                    actual_cost = usage.get("cost")
                    if actual_cost is not None:
                        cost = float(actual_cost)
                        logger.debug(f"Using actual cost from OpenRouter: ${cost:.6f}")
                    else:
                        # Priority 2: Calculate via PricingService as fallback
                        cost = PricingService.calculate_cost(
                            self.model_id, input_tok, output_tok
                        )
                        logger.debug(f"Calculated cost via PricingService: ${cost:.6f}")

                    # Inject Cost into the event
                    # We mutate the dictionary to bubble up the cost
                    event["metrics"]["godoty_cost"] = cost
                    logger.debug(f"Total: {input_tok} input + {output_tok} output = {input_tok + output_tok} tokens")

                    # Invoke metrics callback if provided
                    if self.metrics_callback:
                        try:
                            self.metrics_callback(
                                cost=cost,
                                tokens=input_tok + output_tok,
                                model_name=self.model_id,
                                prompt_tokens=input_tok,
                                completion_tokens=output_tok
                            )
                        except Exception as e:
                            logger.error(f"Metrics callback failed: {e}", exc_info=True)

        # Validation: Warn if no usage data was received
        if not usage_received:
            logger.warning(
                f"No usage data received for model {self.model_id}. "
                "Verify stream_options.include_usage is configured correctly."
            )

    async def execute(
        self,
        messages: Messages,
        tool_specs: Optional[List] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute model request and return complete response as string.

        This method collects all chunks from stream() and returns them as a single string.
        Provides a simple interface for non-streaming use cases while maintaining
        compatibility with the existing streaming infrastructure.
        """
        response_parts = []

        # Collect all content chunks from stream
        async for event in self.stream(messages, tool_specs, system_prompt, **kwargs):
            if "content" in event:
                response_parts.append(event["content"])

        # Return complete response
        return "".join(response_parts)
