"""
Executor Agent Implementation

This module provides the executor agent that uses OpenRouter and Strands
to execute plans and perform actions in Godot.
"""

import logging
import warnings
from typing import Optional, AsyncIterable, Dict, Any, List

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager

from .models import OpenRouterModel
from .config import AgentConfig
from .tools import (
    # Godot control tools
    open_scene,
    play_scene,
    stop_playing,
    # Godot manipulation tools
    create_node,
    delete_node,
    modify_node_property,
    reparent_node,
    select_nodes,
    create_scene,
    # Godot context/debug tools
    get_project_overview,
    analyze_scene_tree,
    capture_visual_context,
    capture_editor_viewport,
    capture_game_viewport,
    get_debug_output,
    inspect_scene_file,
    search_nodes,
    # File tools
    write_file,
    delete_file,
    modify_gdscript_method,
    add_gdscript_method,
    remove_gdscript_method,
    modify_project_setting,
    # File system tools (read access)
    read_file,
    list_files,
    search_codebase,
)
# Import ExecutionPlan for compatibility if needed, though we are moving to LLM-driven execution
from .execution_models import ExecutionPlan, StreamEvent

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    Executor agent that implements plans and performs actions.
    
    This agent uses OpenRouter models via Strands Agents framework to:
    - Execute structured plans
    - Perform direct actions in Godot
    - Manage files and resources
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the executor agent.

        Args:
            api_key: OpenRouter API key (defaults to config)
            model_id: Model ID to use (defaults to config)
            **kwargs: Additional configuration options
        """
        # Get configuration
        config = AgentConfig.get_executor_openrouter_config()
        model_config = AgentConfig.get_model_config()

        # Override with provided values
        api_key_value = api_key if api_key else config["api_key"]
        if model_id:
            model_config["model_id"] = model_id
        else:
            model_config["model_id"] = config["model_id"]

        # Add app name and URL to model config
        model_config["app_name"] = config.get("app_name", "Godot-Assistant")
        model_config["app_url"] = config.get("app_url", "http://localhost:8000")

        # Merge additional config
        model_config.update(kwargs)

        # Initialize OpenRouter model
        try:
            self.model = OpenRouterModel(api_key_value, **model_config)
            logger.info(f"Initialized Executor model: {model_config.get('model_id')}")
        except Exception as e:
            logger.error(f"Failed to initialize executor model: {e}")
            # Try fallback model
            if AgentConfig.EXECUTOR_FALLBACK_MODEL:
                logger.info(f"Attempting fallback executor model: {AgentConfig.EXECUTOR_FALLBACK_MODEL}")
                model_config['model_id'] = AgentConfig.EXECUTOR_FALLBACK_MODEL
                self.model = OpenRouterModel(api_key_value, **model_config)
            else:
                raise

        # Define tools for the agent using wrapper functions
        self.tools = [
            # Godot control tools
            open_scene,
            play_scene,
            stop_playing,
            # Godot manipulation tools
            create_node,
            delete_node,
            modify_node_property,
            reparent_node,
            select_nodes,
            create_scene,
            # Godot context/debug tools
            get_project_overview,
            analyze_scene_tree,
            capture_visual_context,
            capture_editor_viewport,
            capture_game_viewport,
            get_debug_output,
            inspect_scene_file,
            search_nodes,
            # File tools
            write_file,
            delete_file,
            modify_gdscript_method,
            add_gdscript_method,
            remove_gdscript_method,
            modify_project_setting,
            # Read access
            read_file,
            list_files,
            search_codebase,
        ]

        # Initialize conversation manager
        self.conversation_manager = SlidingWindowConversationManager(
            window_size=20,
            should_truncate_results=True
        )

        # Create Strands agent
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=AgentConfig.EXECUTOR_AGENT_SYSTEM_PROMPT,
            conversation_manager=self.conversation_manager
        )

        # Initialize agent state for context persistence
        self._initialize_state()

        logger.info("Executor agent initialized successfully")

    def _initialize_state(self):
        """
        Initialize agent state with default values for context persistence.

        Agent state provides key-value storage for stateful information that
        persists across tool calls and execution cycles.
        """
        # Project context
        self.agent.state.set("project_path", None)
        self.agent.state.set("active_scene", None)

        # Operation tracking
        self.agent.state.set("operation_history", [])

        # Tool metrics tracking
        self.agent.state.set("tool_metrics", {})

        # Execution context
        self.agent.state.set("last_error", None)
        self.agent.state.set("error_count", 0)

        logger.debug("Agent state initialized")

    async def execute_plan(
        self,
        plan: Any,
        collect_metrics: bool = True
    ) -> AsyncIterable[Any]:
        """
        Execute a plan by streaming from the underlying Strands agent.

        Args:
            plan: ExecutionPlan object, dict, or string message
            collect_metrics: Whether to collect and emit metrics (default: True)

        Yields:
            Stream events from the agent, including final metrics event
        """
        # Convert plan to string message if needed
        if isinstance(plan, str):
            message = plan
        elif hasattr(plan, 'title') and hasattr(plan, 'steps'):
            # It's an ExecutionPlan object
            message = f"Execute the following plan:\n\nTitle: {plan.title}\nDescription: {plan.description}\n\nSteps:\n"
            for i, step in enumerate(plan.steps, 1):
                message += f"{i}. {step.title}\n   {step.description}\n"
                if step.tool_calls:
                    message += "   Suggested tools:\n"
                    for tc in step.tool_calls:
                        message += f"   - {tc.name}: {tc.parameters}\n"
        elif isinstance(plan, dict):
            message = f"Execute the following plan:\n{str(plan)}"
        else:
            message = str(plan)

        logger.info(f"Executor agent processing message: {message[:100]}...")

        # Initialize metrics tracking if requested
        if collect_metrics:
            import time
            start_time = time.time()
            cycle_count = 0
            tool_calls = []
            accumulated_metrics = {
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0
            }

        # Stream from the Strands agent
        try:
            async for event in self.agent.stream_async(message):
                # Track lifecycle events for metrics
                if collect_metrics:
                    # Track event loop cycles
                    if "start_event_loop" in event:
                        cycle_count += 1
                        # Emit cycle start event for frontend tracking
                        yield {
                            "type": "cycle_start",
                            "data": {"cycle": cycle_count}
                        }

                    # Track tool usage
                    if "contentBlockStart" in event:
                        start_data = event["contentBlockStart"].get("start", {})
                        if "toolUse" in start_data:
                            tool_use = start_data["toolUse"]
                            tool_call = {
                                "tool": tool_use.get("name"),
                                "id": tool_use.get("toolUseId"),
                                "timestamp": time.time()
                            }
                            tool_calls.append(tool_call)

                    # Track tool completion
                    if "toolResult" in event:
                        tool_result = event["toolResult"]
                        tool_id = tool_result.get("toolUseId")
                        # Find the corresponding tool call and add completion time
                        for tc in tool_calls:
                            if tc.get("id") == tool_id:
                                tc["completion_time"] = time.time()
                                tc["duration"] = tc["completion_time"] - tc["timestamp"]
                                break

                    # Collect token metrics from metadata
                    if "metadata" in event:
                        usage = event["metadata"].get("usage", {})
                        accumulated_metrics["inputTokens"] += usage.get("inputTokens", 0)
                        accumulated_metrics["outputTokens"] += usage.get("outputTokens", 0)
                        accumulated_metrics["totalTokens"] += usage.get("totalTokens", 0)

                # Forward all events
                yield event

        except asyncio.CancelledError:
            logger.info("Execution cancelled by user")
            # Emit cancellation event
            yield {
                "type": "cancelled",
                "data": {"message": "Execution cancelled by user"}
            }
            raise

        # Emit final metrics if requested
        if collect_metrics:
            execution_time = time.time() - start_time

            # Calculate tool statistics
            tools_used = {}
            total_tool_duration = 0
            for tc in tool_calls:
                tool_name = tc.get("tool")
                duration = tc.get("duration", 0)

                if tool_name not in tools_used:
                    tools_used[tool_name] = {
                        "count": 0,
                        "total_duration": 0,
                        "avg_duration": 0
                    }

                tools_used[tool_name]["count"] += 1
                tools_used[tool_name]["total_duration"] += duration
                total_tool_duration += duration

            # Calculate averages
            for tool_name in tools_used:
                tool_stats = tools_used[tool_name]
                tool_stats["avg_duration"] = tool_stats["total_duration"] / tool_stats["count"]

            # Store metrics in agent state
            self.agent.state.set("tool_metrics", {
                "last_execution": {
                    "timestamp": start_time,
                    "duration": execution_time,
                    "cycles": cycle_count,
                    "tool_calls": len(tool_calls),
                    "tools_used": tools_used,
                    "token_usage": accumulated_metrics
                }
            })

            # Emit metrics event
            yield {
                "type": "metrics",
                "data": {
                    "execution_time_seconds": round(execution_time, 2),
                    "cycles": cycle_count,
                    "tool_calls": len(tool_calls),
                    "tools_used": tools_used,
                    "token_usage": accumulated_metrics,
                    "avg_tool_duration": round(total_tool_duration / len(tool_calls), 3) if tool_calls else 0
                }
            }

            logger.info(f"Execution complete: {cycle_count} cycles, {len(tool_calls)} tool calls, {execution_time:.2f}s")

    async def run(self, message: str) -> Any:
        """Run the agent with a message."""
        return await self.agent.invoke_async(message)
        
    async def close(self):
        """Close the agent and cleanup resources."""
        if hasattr(self.model, 'close'):
            await self.model.close()
        logger.info("Executor agent closed")


# Singleton instance
_executor_agent_instance: Optional[ExecutorAgent] = None


def get_executor_agent() -> ExecutorAgent:
    """
    Get or create the executor agent singleton instance.

    Returns:
        ExecutorAgent instance
    """
    global _executor_agent_instance

    if _executor_agent_instance is None:
        _executor_agent_instance = ExecutorAgent()

    return _executor_agent_instance