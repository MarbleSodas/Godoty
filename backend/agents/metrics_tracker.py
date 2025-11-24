"""
Metrics tracking module for token usage and cost calculation.

Provides utilities to extract metrics from API responses and calculate costs.
"""

import logging
import json
import asyncio
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class ModelPricing:
    """
    Model pricing information for cost calculation.
    
    Prices are in USD per 1M tokens.
    Source: OpenRouter pricing (should be updated periodically)
    """
    
    # Pricing table: model_id -> (prompt_price_per_1m, completion_price_per_1m)
    PRICING = {
        "openai/gpt-4-turbo": (10.0, 30.0),
        "openai/gpt-4": (30.0, 60.0),
        "openai/gpt-3.5-turbo": (0.5, 1.5),
        "anthropic/claude-3.5-sonnet": (3.0, 15.0),
        "anthropic/claude-3-opus": (15.0, 75.0),
        "anthropic/claude-3-sonnet": (3.0, 15.0),
        "anthropic/claude-3-haiku": (0.25, 1.25),
        "google/gemini-pro": (0.5, 1.5),
        "meta-llama/llama-3-70b-instruct": (0.9, 0.9),
        "openrouter/sherlock-dash-alpha": (0.1, 0.1),  # Estimated
        "minimax/minimax-m2": (0.5, 0.5),  # Estimated
    }
    
    DEFAULT_PRICING = (1.0, 2.0)  # Default if model not found
    
    @classmethod
    def get_pricing(cls, model_id: str) -> Tuple[float, float]:
        """
        Get pricing for a model.
        
        Args:
            model_id: Model identifier
            
        Returns:
            Tuple of (prompt_price_per_1m, completion_price_per_1m)
        """
        return cls.PRICING.get(model_id, cls.DEFAULT_PRICING)
    
    @classmethod
    def calculate_cost(
        cls,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """
        Calculate estimated cost for token usage.
        
        Args:
            model_id: Model identifier
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            
        Returns:
            Estimated cost in USD
        """
        prompt_price, completion_price = cls.get_pricing(model_id)
        
        prompt_cost = (prompt_tokens / 1_000_000) * prompt_price
        completion_cost = (completion_tokens / 1_000_000) * completion_price
        
        return prompt_cost + completion_cost


class TokenMetricsTracker:
    """
    Tracks token usage and costs from API responses.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize metrics tracker.
        
        Args:
            api_key: OpenRouter API key for querying generation endpoint
        """
        self.api_key = api_key
        self._client = None
        if api_key:
            self._client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {api_key}"}
            )
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
    
    def extract_metrics_from_response(
        self,
        response: Dict[str, Any],
        model_id: str
    ) -> Dict[str, Any]:
        """
        Extract metrics from OpenRouter API response.
        
        Args:
            response: OpenRouter API response dictionary
            model_id: Model ID used for the request
            
        Returns:
            Dictionary containing extracted metrics
        """
        usage = response.get("usage", {})
        
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        
        # Calculate estimated cost
        estimated_cost = ModelPricing.calculate_cost(
            model_id,
            prompt_tokens,
            completion_tokens
        )
        
        # Extract actual cost if available from OpenRouter usage accounting
        actual_cost = usage.get("cost")
        if actual_cost is None:
             # Sometimes might be nested or named differently, but OpenRouter docs say 'cost' in usage.
             pass
        
        # Extract generation ID if available
        generation_id = response.get("id")
        
        # Extract stop reason
        choices = response.get("choices", [])
        stop_reason = None
        if choices:
            stop_reason = choices[0].get("finish_reason")
        
        metrics = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": estimated_cost,
            "actual_cost": actual_cost,
            "generation_id": generation_id,
            "stop_reason": stop_reason,
            "model_id": model_id,
        }
        
        logger.debug(f"Extracted metrics: {metrics}")
        return metrics
    
    def extract_metrics_from_strands_result(
        self,
        result: Any,
        model_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract metrics from Strands AgentResult.
        
        Args:
            result: AgentResult from Strands agent
            model_id: Model ID used
            
        Returns:
            Dictionary containing extracted metrics or None
        """
        try:
            # Try to extract from metrics attribute
            if hasattr(result, 'metrics') and result.metrics:
                accumulated_usage = getattr(result.metrics, 'accumulated_usage', {})
                
                if accumulated_usage:
                    prompt_tokens = accumulated_usage.get('inputTokens', 0)
                    completion_tokens = accumulated_usage.get('outputTokens', 0)
                    total_tokens = accumulated_usage.get('totalTokens', 0)
                    
                    estimated_cost = ModelPricing.calculate_cost(
                        model_id,
                        prompt_tokens,
                        completion_tokens
                    )
                    
                    return {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "estimated_cost": estimated_cost,
                        "model_id": model_id,
                    }
            
            # Try to extract from raw usage data
            if hasattr(result, 'usage') and result.usage:
                usage = result.usage
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                
                estimated_cost = ModelPricing.calculate_cost(
                    model_id,
                    prompt_tokens,
                    completion_tokens
                )
                
                return {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost": estimated_cost,
                    "model_id": model_id,
                }
            
            logger.warning("No metrics found in AgentResult")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting metrics from AgentResult: {e}")
            return None
    
    def extract_metrics_from_stream_event(
        self,
        event: Dict[str, Any],
        model_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract metrics from streaming event.
        
        Args:
            event: Streaming event dictionary
            model_id: Model ID used
            
        Returns:
            Dictionary containing extracted metrics or None
        """
        # Check if this is a metadata event with usage
        if "metadata" in event:
            metadata = event["metadata"]
            usage = metadata.get("usage", {})
            
            if usage:
                prompt_tokens = usage.get("inputTokens", 0)
                completion_tokens = usage.get("outputTokens", 0)
                total_tokens = usage.get("totalTokens", 0)
                
                estimated_cost = ModelPricing.calculate_cost(
                    model_id,
                    prompt_tokens,
                    completion_tokens
                )
                
                return {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost": estimated_cost,
                    "model_id": model_id,
                }
        
        # Check if this is a result event with metrics
        if "result" in event:
            result = event["result"]
            if hasattr(result, 'metrics'):
                return self.extract_metrics_from_strands_result(result, model_id)
        
        return None
    
    async def query_generation_stats(
        self,
        generation_id: str,
        delay_ms: int = 1000
    ) -> Optional[Dict[str, Any]]:
        """
        Query OpenRouter /api/v1/generation endpoint for precise costs.
        
        Args:
            generation_id: Generation ID from response
            delay_ms: Delay in milliseconds before querying (default 1000ms)
            
        Returns:
            Dictionary with native token counts and actual cost, or None
        """
        if not self._client or not generation_id:
            return None
        
        try:
            # Wait for the recommended delay
            await asyncio.sleep(delay_ms / 1000.0)
            
            url = f"https://openrouter.ai/api/v1/generation?id={generation_id}"
            response = await self._client.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract precise metrics
            native_prompt_tokens = data.get("data", {}).get("native_tokens_prompt", 0)
            native_completion_tokens = data.get("data", {}).get("native_tokens_completion", 0)
            total_cost = data.get("data", {}).get("total_cost", 0.0)
            
            logger.info(
                f"Retrieved generation stats for {generation_id}: "
                f"{native_prompt_tokens} prompt, {native_completion_tokens} completion, "
                f"${total_cost} cost"
            )
            
            return {
                "native_prompt_tokens": native_prompt_tokens,
                "native_completion_tokens": native_completion_tokens,
                "native_total_tokens": native_prompt_tokens + native_completion_tokens,
                "actual_cost": total_cost,
            }
            
        except httpx.HTTPError as e:
            logger.error(f"Failed to query generation stats: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error querying generation stats: {e}")
            return None
    
    def count_tool_calls(self, result: Any) -> int:
        """
        Count tool calls in a result.
        
        Args:
            result: AgentResult or response dictionary
            
        Returns:
            Number of tool calls
        """
        count = 0
        
        try:
            # Check if result has message with content
            if hasattr(result, 'message'):
                content = result.message.get('content', [])
                if isinstance(content, list):
                    count = sum(1 for block in content if 'toolUse' in block)
            
            # Check if it's a dict response
            elif isinstance(result, dict):
                choices = result.get('choices', [])
                for choice in choices:
                    message = choice.get('message', {})
                    tool_calls = message.get('tool_calls', [])
                    count += len(tool_calls)
        
        except Exception as e:
            logger.error(f"Error counting tool calls: {e}")
        
        return count

    def extract_tool_stats(self, result: Any) -> Dict[str, int]:
        """
        Extract tool usage statistics (calls and errors) from AgentResult.
        
        Args:
            result: AgentResult from Strands agent
            
        Returns:
            Dictionary with 'call_count' and 'error_count'
        """
        stats = {"call_count": 0, "error_count": 0}
        
        try:
            # Try to extract from metrics attribute (Strands specific)
            if hasattr(result, 'metrics') and result.metrics:
                # Assuming result.metrics.tool_metrics is a dict of ToolMetrics
                tool_metrics = getattr(result.metrics, 'tool_metrics', {})
                
                for _, metric in tool_metrics.items():
                    stats["call_count"] += getattr(metric, 'call_count', 0)
                    stats["error_count"] += getattr(metric, 'error_count', 0)
                    
            # Fallback: Manual counting if metrics not available/populated
            # (This is harder for errors without specific result inspection)
            elif hasattr(result, 'steps'):
                # If we have access to execution steps
                for step in result.steps:
                    if step.tool_calls:
                        stats["call_count"] += len(step.tool_calls)
                        # Check results for errors?
                        # This depends on Strands internal structure
                        pass
            
            # Ensure call_count is at least what we counted before if we use fallback
            if stats["call_count"] == 0:
                stats["call_count"] = self.count_tool_calls(result)

        except Exception as e:
            logger.error(f"Error extracting tool stats: {e}")
            
        return stats
