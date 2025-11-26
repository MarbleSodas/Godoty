"""
Executor Agent Implementation

This module provides the executor agent that uses OpenRouter and Strands
to execute plans and perform actions in Godot.
"""

import logging
import warnings
import uuid
import asyncio
import os
from typing import Optional, AsyncIterable, Dict, Any, List

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager

from context.engine import ContextEngine
from .db import ProjectDB
from .models import OpenRouterModel
from .config import AgentConfig
from .metrics_tracker import TokenMetricsTracker
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
        project_path: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the executor agent.

        Args:
            api_key: OpenRouter API key (defaults to config)
            model_id: Model ID to use (defaults to config)
            project_path: Path to the Godot project (for metrics/db)
            **kwargs: Additional configuration options
        """
        # Get configuration
        config = AgentConfig.get_executor_openrouter_config()
        model_config = AgentConfig.get_model_config()

        # Initialize state
        self.db: Optional[ProjectDB] = None
        self.current_session_id: Optional[str] = None
        
        if project_path:
            self.set_project_path(project_path)

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
            self.model = OpenRouterModel(
                api_key_value, 
                metrics_callback=self._metrics_callback,
                **model_config
            )
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

        # Initialize Context Engine
        # Repo root is 3 levels up: backend/agents/executor_agent.py -> backend/agents -> backend -> Root
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.context_engine = ContextEngine(repo_root)

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
        
        # Initialize metrics tracker
        self.metrics_tracker = TokenMetricsTracker(api_key=api_key_value)

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

    def set_project_path(self, project_path: str):
        """Set the project path and initialize the database."""
        try:
            self.db = ProjectDB(project_path)
            logger.info(f"ProjectDB initialized for path: {project_path}")
        except Exception as e:
            logger.error(f"Failed to initialize ProjectDB: {e}")

    def _metrics_callback(self, cost: float, tokens: int, model_name: str):
        """Callback for recording metrics from the model."""
        if self.db and self.current_session_id:
            try:
                self.db.record_metric(self.current_session_id, cost, tokens, model_name)
            except Exception as e:
                logger.error(f"Failed to record metric: {e}")

    def start_session(self, session_id: Optional[str] = None):
        """Start a new session or continue an existing one."""
        if not session_id:
            session_id = str(uuid.uuid4())
        
        self.current_session_id = session_id
        logger.info(f"Session started: {session_id}")
        return session_id

    def restore_session(self, session_id: str):
        """Re-hydrate Strands agent from stored history"""
        if not self.db:
            logger.warning("Cannot restore session: DB not initialized")
            return
            
        session_data = self.db.get_session(session_id)
        if not session_data:
            logger.warning(f"Session {session_id} not found")
            return

        self.current_session_id = session_id
        
        # Rebuild Strands memory
        # Assuming Strands ConversationManager has a way to add messages
        # If not, we might need to manually manipulate internal state or use specific API
        # For SlidingWindowConversationManager, it likely stores messages in a list
        # We'll need to verify this assumption or check available methods via introspection in a real scenario
        # Here we attempt to restore if compatible methods exist
        
        try:
            history = session_data.get("chat_history", [])
            # Clear current history if needed?
            # self.conversation_manager.history.clear() 
            
            for msg in history:
                # Adapt message format if needed
                role = msg.get("role")
                content = msg.get("content")
                if role and content:
                    self.conversation_manager.add_message(
                        role=role,
                        content=content
                    )
            logger.info(f"Restored session {session_id} with {len(history)} messages")
        except Exception as e:
            logger.error(f"Error restoring session history: {e}")

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

    def _prepare_agent_with_context(self, prompt: str):
        """
        Inject dynamic context into the agent's system prompt.
        """
        try:
            # Get context from engine
            context = self.context_engine.get_context_for_prompt(prompt)
            
            # Combine with base prompt
            base_prompt = AgentConfig.EXECUTOR_AGENT_SYSTEM_PROMPT
            enhanced_prompt = f"{base_prompt}\n\n{context}"
            
            # Recreate agent with new system prompt but same history
            self.agent = Agent(
                model=self.model,
                tools=self.tools,
                system_prompt=enhanced_prompt,
                conversation_manager=self.conversation_manager
            )
            # Restore state references that might be lost on recreation if Agent class doesn't persist them automatically
            # (Assuming Agent class handles this or we rely on conversation_manager)
            
        except Exception as e:
            logger.error(f"Failed to inject context: {e}")
            # Continue with existing agent if context fails

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

        # Inject context
        self._prepare_agent_with_context(message)

        logger.info(f"Executor agent processing message: {message[:100]}...")

        # Generate message ID for metrics
        message_id = str(uuid.uuid4())

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
            total_actual_cost = 0.0
            total_estimated_cost = 0.0
            last_model_id = self.model.get_config().get("model_id", "unknown")

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
                        accumulated_metrics["outputTokens"] += usage.get("outputTokens", 0)
                        accumulated_metrics["totalTokens"] += usage.get("totalTokens", 0)

                    # Collect cost and model info from messageStop
                    if "messageStop" in event:
                        stop_event = event["messageStop"]
                        usage = stop_event.get("usage", {})
                        
                        # Capture cost if available
                        cost = usage.get("actual_cost")
                        if cost is not None:
                            total_actual_cost += float(cost)
                            # If actual cost is available, use it for estimate too
                            total_estimated_cost += float(cost)
                        
                        # Capture model ID
                        if "model_id" in stop_event:
                            last_model_id = stop_event["model_id"]
                        elif "model_id" in event:
                            last_model_id = event["model_id"]

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

            # Save Session History
            if self.db and self.current_session_id:
                try:
                    # Retrieve history from conversation manager
                    # Attempt to get history using common methods
                    if hasattr(self.conversation_manager, 'get_history'):
                        if asyncio.iscoroutinefunction(self.conversation_manager.get_history):
                            history = await self.conversation_manager.get_history()
                        else:
                            history = self.conversation_manager.get_history()
                    elif hasattr(self.conversation_manager, 'messages'):
                         history = self.conversation_manager.messages
                    else:
                         history = []

                    # Serialize history
                    serialized_history = []
                    for msg in history:
                         # Handle both object and dict representations
                         role = getattr(msg, 'role', msg.get('role') if isinstance(msg, dict) else None)
                         content = getattr(msg, 'content', msg.get('content') if isinstance(msg, dict) else None)
                         
                         if role and content is not None:
                             serialized_history.append({
                                 "role": role,
                                 "content": content
                             })
                    
                    self.db.save_session(self.current_session_id, serialized_history)
                    logger.info(f"Saved session {self.current_session_id}")
                except Exception as e:
                    logger.error(f"Failed to save session history: {e}")

            # Save metrics to database (Legacy - Commented out to favor ProjectDB)
            # try:
            #     from database import get_db_manager
            #     db_manager = get_db_manager()
            #     
            #     await db_manager.create_message_metrics(
            #         message_id=message_id,
            #         model_id=last_model_id,
            #         prompt_tokens=accumulated_metrics["inputTokens"],
            #         completion_tokens=accumulated_metrics["outputTokens"],
            #         total_tokens=accumulated_metrics["totalTokens"],
            #         estimated_cost=total_estimated_cost,
            #         actual_cost=total_actual_cost if total_actual_cost > 0 else None,
            #         response_time_ms=int(execution_time * 1000),
            #         tool_calls_count=len(tool_calls),
            #         stop_reason="completed"
            #     )
            #     logger.info(f"Persisted executor metrics for message {message_id}")
            # except Exception as e:
            #     logger.error(f"Failed to save executor metrics: {e}")

            # Emit metrics event
            yield {
                "type": "metrics",
                "data": {
                    "execution_time_seconds": round(execution_time, 2),
                    "cycles": cycle_count,
                    "tool_calls": len(tool_calls),
                    "tools_used": tools_used,
                    "token_usage": accumulated_metrics,
                    "avg_tool_duration": round(total_tool_duration / len(tool_calls), 3) if tool_calls else 0,
                    "actual_cost": total_actual_cost,
                    "model_id": last_model_id
                }
            }

            logger.info(f"Execution complete: {cycle_count} cycles, {len(tool_calls)} tool calls, {execution_time:.2f}s")

    async def run(self, message: str) -> Any:
        """Run the agent with a message."""
        # Inject context
        self._prepare_agent_with_context(message)
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


async def close_executor_agent():
    """Close the executor agent singleton instance."""
    global _executor_agent_instance

    if _executor_agent_instance is not None:
        await _executor_agent_instance.close()
        _executor_agent_instance = None