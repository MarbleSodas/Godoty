"""
Executor Agent for Godot Assistant.

An executor agent that works directly with structured plans
from the planning agent, without complex parsing or validation.
"""

import asyncio
import logging
from typing import Any, Dict, AsyncIterable, Optional, List

from .execution_models import ExecutionPlan, StreamEvent
from .execution_engine import ExecutionEngine
from .models.openrouter import OpenRouterModel
from .config import AgentConfig

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """Executor agent for executing structured plans."""

    def __init__(self):
        """Initialize the executor agent."""
        self.execution_engine = ExecutionEngine()

        # Initialize OpenRouter model with executor configuration
        openrouter_config = AgentConfig.get_executor_openrouter_config()
        model_config = AgentConfig.get_model_config()

        try:
            self.model = OpenRouterModel(
                api_key=openrouter_config["api_key"],
                model_id=openrouter_config["model_id"],
                app_name=openrouter_config["app_name"],
                app_url=openrouter_config["app_url"],
                temperature=model_config["temperature"],
                max_tokens=model_config["max_tokens"]
            )
            self.fallback_model = None
            logger.info(f"Executor agent initialized with model: {openrouter_config['model_id']}")
        except Exception as e:
            logger.error(f"Failed to initialize primary executor model: {e}")
            self.model = None
            self.fallback_model = None

    def _get_fallback_model(self) -> Optional[OpenRouterModel]:
        """Initialize fallback model if needed."""
        if self.fallback_model is None and AgentConfig.EXECUTOR_FALLBACK_MODEL:
            try:
                fallback_config = AgentConfig.get_executor_openrouter_config()
                fallback_config["model_id"] = AgentConfig.EXECUTOR_FALLBACK_MODEL

                model_config = AgentConfig.get_model_config()
                self.fallback_model = OpenRouterModel(
                    api_key=fallback_config["api_key"],
                    model_id=fallback_config["model_id"],
                    app_name=fallback_config["app_name"],
                    app_url=fallback_config["app_url"],
                    temperature=model_config["temperature"],
                    max_tokens=model_config["max_tokens"]
                )
                logger.info(f"Executor fallback model initialized: {AgentConfig.EXECUTOR_FALLBACK_MODEL}")
            except Exception as e:
                logger.error(f"Failed to initialize fallback executor model: {e}")
                self.fallback_model = None

        return self.fallback_model

    async def execute_with_fallback(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute model inference with fallback support.

        Args:
            messages: Conversation messages
            system_prompt: Optional system prompt

        Returns:
            Model response with content and tool calls
        """
        # Try primary model first
        if self.model:
            try:
                logger.debug("Attempting executor inference with primary model")
                return await self.model.complete(
                    messages=messages,
                    system_prompt=system_prompt
                )
            except Exception as e:
                logger.warning(f"Primary executor model failed: {e}")

        # Try fallback model
        fallback = self._get_fallback_model()
        if fallback:
            try:
                logger.debug("Attempting executor inference with fallback model")
                return await fallback.complete(
                    messages=messages,
                    system_prompt=system_prompt
                )
            except Exception as e:
                logger.error(f"Fallback executor model also failed: {e}")

        # If both models fail, return error response
        logger.error("All executor models failed")
        return {
            "message": {
                "content": [{"text": "Executor models are currently unavailable"}],
                "role": "assistant"
            },
            "stop_reason": "error"
        }

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncIterable[StreamEvent]:
        """
        Execute a plan with streaming events.

        Args:
            plan: Structured execution plan
            context: Optional execution context

        Yields:
            StreamEvent objects
        """
        logger.info(f"Starting execution of plan: {plan.title}")

        try:
            async for event in self.execution_engine.execute_plan(plan, context):
                yield event
        except Exception as e:
            logger.error(f"Plan execution failed: {e}")
            yield StreamEvent(
                type="execution_error",
                data={"error": str(e)}
            )

    def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get execution status."""
        state = self.execution_engine.get_execution_status(execution_id)
        if state:
            return {
                "execution_id": state.execution_id,
                "status": state.status.value,
                "current_step": state.current_step,
                "completed_steps": state.completed_steps,
                "failed_steps": state.failed_steps,
                "started_at": state.started_at.isoformat()
            }
        return None

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel an execution."""
        return await self.execution_engine.cancel_execution(execution_id)

    def list_active_executions(self) -> List[Dict[str, Any]]:
        """List active executions."""
        executions = []
        for state in self.execution_engine.list_active_executions():
            executions.append({
                "execution_id": state.execution_id,
                "plan_title": state.plan.title,
                "status": state.status.value,
                "started_at": state.started_at.isoformat()
            })
        return executions


# Global instance
_executor_agent = None


def get_executor_agent() -> ExecutorAgent:
    """Get the global executor agent instance."""
    global _executor_agent
    if _executor_agent is None:
        _executor_agent = ExecutorAgent()
    return _executor_agent