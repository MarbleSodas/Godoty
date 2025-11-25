"""
Multi-Agent Manager for Godot Assistant.

This module manages multi-agent sessions and orchestration using Strands Agents.
It handles:
- Session creation and persistence
- Multi-agent graph execution
- Message processing
- Workflow orchestration (Planning -> Execution)
"""

import logging
import os
import warnings
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Union, AsyncIterable

# Suppress LangGraph warning before importing strands
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from strands import Agent
from strands.multiagent.graph import Graph, GraphBuilder
from strands.session.file_session_manager import FileSessionManager

from .planning_agent import get_planning_agent
from .executor_agent import get_executor_agent
from .config import AgentConfig
from .db import ProjectDB

logger = logging.getLogger(__name__)


class WorkflowMetricsAccumulator:
    """
    Accumulates and aggregates metrics across planning and execution phases
    of multi-agent workflows.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.planning_metrics = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0
        }
        self.execution_metrics = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0
        }
        self.start_time = datetime.now()

    def add_planning_metrics(self, metrics: Dict[str, Any]) -> None:
        """Add metrics from the planning phase."""
        self.planning_metrics["input_tokens"] += metrics.get("input_tokens", 0)
        self.planning_metrics["output_tokens"] += metrics.get("output_tokens", 0)
        self.planning_metrics["total_tokens"] += metrics.get("total_tokens", 0)
        self.planning_metrics["cost"] += metrics.get("cost", 0.0)

    def add_execution_metrics(self, metrics: Dict[str, Any]) -> None:
        """Add metrics from the execution phase."""
        self.execution_metrics["input_tokens"] += metrics.get("input_tokens", 0)
        self.execution_metrics["output_tokens"] += metrics.get("output_tokens", 0)
        self.execution_metrics["total_tokens"] += metrics.get("total_tokens", 0)
        self.execution_metrics["cost"] += metrics.get("cost", 0.0)

    def get_aggregated_metrics(self) -> Dict[str, Any]:
        """Get aggregated workflow metrics."""
        total_tokens = self.planning_metrics["total_tokens"] + self.execution_metrics["total_tokens"]
        total_cost = self.planning_metrics["cost"] + self.execution_metrics["cost"]

        return {
            "workflow_id": self.session_id,
            "planning_tokens": self.planning_metrics["total_tokens"],
            "execution_tokens": self.execution_metrics["total_tokens"],
            "total_tokens": total_tokens,
            "planning_cost": self.planning_metrics["cost"],
            "execution_cost": self.execution_metrics["cost"],
            "total_cost": total_cost,
            "agent_types": ["planning", "execution"],
            "planning_metrics": self.planning_metrics,
            "execution_metrics": self.execution_metrics,
            "start_time": self.start_time.isoformat(),
            "completion_time": datetime.now().isoformat()
        }

    def reset(self) -> None:
        """Reset all metrics for a new workflow."""
        self.planning_metrics = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0
        }
        self.execution_metrics = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0
        }
        self.start_time = datetime.now()


class MultiAgentManager:
    """
    Manages multi-agent sessions and execution.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize the multi-agent manager.

        Args:
            storage_dir: Directory to store session files. Defaults to .godoty_sessions
        """
        self.storage_dir = storage_dir or os.path.join(os.getcwd(), ".godoty_sessions")
        os.makedirs(self.storage_dir, exist_ok=True)
        # Store graphs as a dict of dicts: session_id -> {"planning": Graph, "fast": Graph}
        self._active_graphs: Dict[str, Dict[str, Graph]] = {}
        # Store active asyncio tasks: session_id -> asyncio.Task
        self._active_tasks: Dict[str, asyncio.Task] = {}
        # Store workflow metrics accumulators: session_id -> WorkflowMetricsAccumulator
        self._workflow_metrics: Dict[str, WorkflowMetricsAccumulator] = {}
        logger.info(f"MultiAgentManager initialized with storage: {self.storage_dir}")

    def create_session(self, session_id: str, title: Optional[str] = None) -> str:
        """
        Create a new multi-agent session with both Planning and Fast execution graphs.

        Args:
            session_id: Unique session identifier
            title: Optional session title (e.g., first user message)

        Returns:
            Session ID
        """
        if session_id in self._active_graphs:
            logger.info(f"Session {session_id} already active")
            return session_id

        try:
            # Get agents
            planning_agent = get_planning_agent()
            executor_agent = get_executor_agent()
            
            # Create session manager
            session_manager = FileSessionManager(
                session_id=session_id,
                storage_dir=self.storage_dir
            )

            # --- Build Planning Graph ---
            # This graph contains the Planning Agent
            builder_planning = GraphBuilder()
            builder_planning.add_node(planning_agent.agent, "planner")
            builder_planning.set_entry_point("planner")
            builder_planning.set_session_manager(session_manager)
            builder_planning.set_max_node_executions(50)
            builder_planning.set_execution_timeout(300)
            planning_graph = builder_planning.build()

            # --- Build Fast Graph ---
            # This graph contains the Executor Agent
            builder_fast = GraphBuilder()
            builder_fast.add_node(executor_agent.agent, "executor")
            builder_fast.set_entry_point("executor")
            builder_fast.set_session_manager(session_manager)
            builder_fast.set_max_node_executions(50)
            builder_fast.set_execution_timeout(600) # Longer timeout for execution
            fast_graph = builder_fast.build()
            
            self._active_graphs[session_id] = {
                "planning": planning_graph,
                "fast": fast_graph
            }
            
            # Store session metadata
            metadata = {
                "title": title or f"Session {session_id}",
                "created_at": datetime.now().isoformat()
            }
            self._save_session_metadata(session_id, metadata)
            
            logger.info(f"Created session {session_id} with title: {title}")
            return session_id

        except Exception as e:
            logger.error(f"Failed to create session {session_id}: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session details.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session details or None if not found
        """
        # Check if session file exists even if not in memory
        session_path = os.path.join(self.storage_dir, f"{session_id}.json")
        if os.path.exists(session_path):
            metadata = self._load_session_metadata(session_id)
            return {
                "session_id": session_id,
                "path": session_path,
                "active": session_id in self._active_graphs,
                "is_running": session_id in self._active_tasks,
                "metadata": metadata
            }
        return None

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        List all available sessions.

        Returns:
            Dictionary of session_id to session details
        """
        sessions = {}
        if os.path.exists(self.storage_dir):
            for filename in os.listdir(self.storage_dir):
                if filename.endswith(".json") and not filename.endswith("_metadata.json"):
                    session_id = filename[:-5]
                    session = self.get_session(session_id)
                    # Filter hidden sessions
                    if session and not session.get("metadata", {}).get("is_hidden", False):
                        sessions[session_id] = session
        return sessions

    def hide_session(self, session_id: str) -> bool:
        """
        Hide a session from the list without deleting data.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if hidden, False otherwise
        """
        # Stop any running task
        self.stop_session(session_id)
        
        # Remove from active graphs
        if session_id in self._active_graphs:
            del self._active_graphs[session_id]
            
        # Update metadata
        metadata = self._load_session_metadata(session_id)
        metadata["is_hidden"] = True
        self._save_session_metadata(session_id, metadata)
        
        logger.info(f"Hidden session {session_id}")
        return True

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False otherwise
        """
        # Stop any running task first
        self.stop_session(session_id)

        # Remove from active graphs
        if session_id in self._active_graphs:
            del self._active_graphs[session_id]

        # Delete file
        session_path = os.path.join(self.storage_dir, f"{session_id}.json")
        if os.path.exists(session_path):
            try:
                os.remove(session_path)
                logger.info(f"Deleted session {session_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete session file {session_path}: {e}")
                return False
        return False
    
    def stop_session(self, session_id: str) -> bool:
        """
        Stop any running task for the session.

        Args:
            session_id: Session ID

        Returns:
            True if a task was stopped, False otherwise
        """
        if session_id in self._active_tasks:
            task = self._active_tasks[session_id]
            if not task.done():
                logger.info(f"Stopping task for session {session_id}")
                task.cancel()
                # Note: We don't remove from _active_tasks here as that's done in _create_task
                # when the task completes/cancels
                return True
        return False

    async def stop_session_async(self, session_id: str) -> bool:
        """
        Stop and await cancellation of any running task for the session.

        Args:
            session_id: Session ID

        Returns:
            True if a task was stopped, False otherwise
        """
        if session_id in self._active_tasks:
            task = self._active_tasks[session_id]
            if not task.done():
                logger.info(f"Stopping and awaiting cancellation for session {session_id}")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.debug(f"Task cancelled for session {session_id}")
                # Remove from active tasks
                if session_id in self._active_tasks:
                    del self._active_tasks[session_id]
                return True
        return False
    
    def _save_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """Save session metadata to a separate file."""
        metadata_path = os.path.join(self.storage_dir, f"{session_id}_metadata.json")
        try:
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata for session {session_id}: {e}")
    
    def _load_session_metadata(self, session_id: str) -> Dict[str, Any]:
        """Load session metadata from file."""
        metadata_path = os.path.join(self.storage_dir, f"{session_id}_metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load metadata for session {session_id}: {e}")
        
        return {
            "title": f"Session {session_id}",
            "created_at": datetime.now().isoformat()
        }

    async def process_message(self, session_id: str, message: str, project_path: Optional[str] = None, mode: str = "planning") -> Any:
        """
        Process a message in a session (non-streaming).

        Args:
            session_id: Session ID
            message: User message
            project_path: Optional project path for context
            mode: "planning" or "fast"

        Returns:
            Agent response
        """
        # We'll implement this by consuming the stream to ensure consistent logic
        response_text = ""
        async for event in self.process_message_stream(session_id, message, mode=mode, project_path=project_path):
            if event["type"] == "data" and "text" in event["data"]:
                response_text += event["data"]["text"]
            elif event["type"] == "error":
                raise Exception(event["data"].get("message", "Unknown error"))
        
        return response_text

    async def process_message_stream(
        self,
        session_id: str,
        message: str,
        mode: str = "planning",
        project_path: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Process a message in a session (streaming).

        Args:
            session_id: Session ID
            message: User message
            mode: Execution mode ("planning" or "fast")
            project_path: Optional project path for context

        Yields:
            Stream events
        """
        if session_id not in self._active_graphs:
            self._active_graphs[session_id] = self._create_graphs(session_id)

        # Setup executor agent with context
        try:
            executor_agent = get_executor_agent()
            if project_path:
                executor_agent.set_project_path(project_path)
            # Ensure session context is set for metrics
            executor_agent.start_session(session_id)
        except Exception as e:
            logger.warning(f"Failed to setup executor context: {e}")

        # Cancel existing task if any
        if session_id in self._active_tasks:
            task = self._active_tasks[session_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self._active_tasks[session_id]
        
        # Create new task tracking
        import asyncio
        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[session_id] = current_task

        graphs = self._active_graphs[session_id]

        # Initialize workflow metrics accumulator for planning mode
        if mode == "planning":
            self._workflow_metrics[session_id] = WorkflowMetricsAccumulator(session_id)

        try:
            # Import shared event utility
            from .event_utils import transform_strands_event, accumulate_workflow_metrics

            if mode == "fast":
                # --- Fast Mode: Execute directly (Bypass Graph) ---
                # This reduces overhead and allows direct interaction with the agent
                executor_agent = get_executor_agent()

                # Stream directly from the agent
                async for event in executor_agent.agent.stream_async(message):
                    # Transform event with execution agent type
                    transformed = transform_strands_event(event, agent_type="execution", session_id=session_id)
                    if transformed:
                        # Accumulate metrics if this is a metrics event
                        if transformed["type"] == "metrics":
                            accumulate_workflow_metrics(session_id, transformed, self, "execution")
                        yield transformed
                    
            else:
                # --- Planning Mode: Plan then Execute ---
                planning_graph = graphs["planning"]
                submitted_plan = None
                planning_output = []  # Collect text output to detect execution plan

                # 1. Run Planning Graph
                async for event in planning_graph.stream_async(message):
                    transformed = transform_strands_event(event, agent_type="planning", session_id=session_id)
                    if transformed:
                        # Accumulate metrics if this is a metrics event
                        if transformed["type"] == "metrics":
                            accumulate_workflow_metrics(session_id, transformed, self, "planning")
                        # yield transformed  <-- REMOVED (Handled below with filtering)

                        # Collect text output to detect execution plan
                        if transformed["type"] == "data" and "text" in transformed.get("data", {}):
                            text_chunk = transformed["data"]["text"]
                            planning_output.append(text_chunk)
                            
                            # Filter out execution plan from the stream
                            # We want to hide the raw JSON from the user but keep it for extraction
                            
                            # Check for start of plan
                            if "```execution-plan" in text_chunk:
                                # If the chunk contains the start, we might need to split it
                                parts = text_chunk.split("```execution-plan")
                                if parts[0]:
                                    # Yield the part before the plan
                                    transformed["data"]["text"] = parts[0]
                                    yield transformed
                                # The rest is part of the plan, don't yield
                                continue
                                
                            # Check if we are inside a plan block
                            # This is a simple heuristic: if we have seen the start but not the end
                            full_so_far = "".join(planning_output)
                            if "```execution-plan" in full_so_far:
                                # Check if the block is closed
                                # Count backticks or look for closing block
                                # A simple check: split by start, look at the last part
                                last_part = full_so_far.split("```execution-plan")[-1]
                                if "```" not in last_part:
                                    # We are inside the block, don't yield
                                    continue
                                elif text_chunk.strip() == "```":
                                     # This is the closing tag, don't yield
                                     continue
                                     
                            # If we are here, we are either not in a plan or the plan just finished
                            # If the plan just finished in this chunk, we might need to yield the part after
                            if "```execution-plan" in full_so_far and "```" in text_chunk:
                                # This chunk might contain the closing backticks
                                # If it's just backticks, we skipped it above.
                                # If it has content after, we should yield that.
                                pass 

                            yield transformed
                        else:
                            yield transformed

                # 2. Check if plan was provided in output
                full_output = "".join(planning_output)
                submitted_plan = self._extract_execution_plan(full_output)

                if submitted_plan:
                    # Notify frontend of plan creation with full step details
                    steps_data = submitted_plan.get("steps", [])
                    formatted_steps = []
                    if isinstance(steps_data, list):
                        for idx, step in enumerate(steps_data):
                            formatted_steps.append({
                                "id": f"step-{idx}",
                                "title": step.get("title", f"Step {idx + 1}"),
                                "description": step.get("description", ""),
                                "tool_calls": step.get("tool_calls", []),
                                "depends_on": step.get("depends_on", []),
                                "status": "pending"
                            })

                    # Persist plan to session metadata
                    try:
                        metadata = self._load_session_metadata(session_id)
                        metadata["current_plan"] = submitted_plan
                        self._save_session_metadata(session_id, metadata)
                    except Exception as e:
                        logger.error(f"Failed to persist plan to metadata: {e}")

                    yield {
                        "type": "plan_created",
                        "data": {
                            "title": submitted_plan.get("title", "Execution Plan"),
                            "description": submitted_plan.get("description", ""),
                            "steps": formatted_steps,
                            "step_count": len(formatted_steps)  # Keep for backward compatibility
                        }
                    }

                # 3. If plan submitted, Run Fast Graph (Executor)
                if submitted_plan:
                    logger.info("Executing submitted plan...")
                    fast_graph = graphs["fast"]

                    # Construct a prompt for the executor
                    plan_prompt = self._construct_executor_prompt(submitted_plan)

                    # Notify execution started
                    yield {
                        "type": "execution_started",
                        "data": {"message": "Starting execution of plan..."}
                    }

                    # Emit step_started for first step
                    if formatted_steps:
                        yield {
                            "type": "step_started",
                            "data": {
                                "step_index": 0,
                                "step_id": formatted_steps[0]["id"],
                                "title": formatted_steps[0]["title"],
                                "description": formatted_steps[0]["description"]
                            }
                        }

                    # Track tool completions to advance steps
                    tool_completion_count = 0
                    current_step_index = 0

                    async for event in fast_graph.stream_async(plan_prompt):
                        transformed = transform_strands_event(event, agent_type="execution", session_id=session_id)
                        if transformed:
                            # Accumulate metrics if this is a metrics event
                            if transformed["type"] == "metrics":
                                accumulate_workflow_metrics(session_id, transformed, self, "execution")
                            yield transformed

                            # Track tool completions to potentially advance to next step
                            if transformed.get("type") == "tool_result" or transformed.get("type") == "tool_completed":
                                tool_completion_count += 1

                                # Simple heuristic: advance to next step after each tool completion
                                next_step_index = min(tool_completion_count, len(formatted_steps) - 1)

                                if next_step_index > current_step_index and next_step_index < len(formatted_steps):
                                    # Mark previous step as completed
                                    yield {
                                        "type": "step_completed",
                                        "data": {
                                            "step_index": current_step_index,
                                            "step_id": formatted_steps[current_step_index]["id"],
                                            "status": "completed"
                                        }
                                    }

                                    # Start next step
                                    current_step_index = next_step_index
                                    yield {
                                        "type": "step_started",
                                        "data": {
                                            "step_index": current_step_index,
                                            "step_id": formatted_steps[current_step_index]["id"],
                                            "title": formatted_steps[current_step_index]["title"],
                                            "description": formatted_steps[current_step_index]["description"]
                                        }
                                    }

                    # Mark last step as completed
                    if formatted_steps and current_step_index < len(formatted_steps):
                        yield {
                            "type": "step_completed",
                            "data": {
                                "step_index": current_step_index,
                                "step_id": formatted_steps[current_step_index]["id"],
                                "status": "completed"
                            }
                        }

                    # Notify execution completed
                    yield {
                        "type": "execution_completed",
                        "data": {"message": "Plan execution completed."}
                    }

                # Emit aggregated workflow metrics for planning mode
                if mode == "planning" and session_id in self._workflow_metrics:
                    try:
                        # Get accumulated metrics from planning and execution phases
                        aggregated_metrics = self._workflow_metrics[session_id].get_aggregated_metrics()

                        # Persist workflow metrics to database if project_path is available
                        if project_path:
                            try:
                                db = ProjectDB(project_path)
                                db.record_workflow_metrics(session_id, aggregated_metrics)
                                logger.info(f"Persisted workflow metrics to database for {session_id}")
                            except Exception as db_error:
                                logger.error(f"Failed to persist workflow metrics to database: {db_error}")

                        # Emit workflow metrics complete event
                        yield {
                            "type": "workflow_metrics_complete",
                            "data": {
                                "workflow_id": session_id,
                                "metrics": aggregated_metrics,
                                "phase_breakdown": {
                                    "planning": self._workflow_metrics[session_id].planning_metrics,
                                    "execution": self._workflow_metrics[session_id].execution_metrics
                                }
                            }
                        }

                        logger.info(f"Emitted aggregated workflow metrics for {session_id}: "
                                 f"Total tokens: {aggregated_metrics['total_tokens']}, "
                                 f"Total cost: ${aggregated_metrics['total_cost']:.4f}")

                    except Exception as e:
                        logger.error(f"Failed to emit aggregated workflow metrics: {e}")

            # Track session-level metrics if enabled
            self._track_metrics(session_id, project_path)

        except asyncio.CancelledError:
            logger.info(f"Task cancelled for session {session_id}")
            yield {"type": "error", "data": {"message": "Operation cancelled by user"}}
            raise
        except Exception as e:
            logger.error(f"Error processing message stream in session {session_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield {"type": "error", "data": {"message": str(e)}}
        finally:
            # Cleanup task registration
            if session_id in self._active_tasks and self._active_tasks[session_id] == current_task:
                del self._active_tasks[session_id]

    def _extract_execution_plan(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract execution plan from planning agent output.

        Looks for ```execution-plan code blocks and parses the JSON.

        Args:
            text: The full text output from planning agent

        Returns:
            Parsed plan dictionary or None if not found
        """
        # Look for ```execution-plan ... ``` code block
        pattern = r'```execution-plan\s*\n(.*?)\n```'
        match = re.search(pattern, text, re.DOTALL)

        if match:
            plan_json = match.group(1)
            try:
                plan = json.loads(plan_json)
                logger.info(f"Extracted execution plan: {plan.get('title', 'Unknown')}")
                return plan
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse execution plan JSON: {e}")
                logger.error(f"Invalid JSON: {plan_json}")
                return None

        return None

    def _construct_executor_prompt(self, plan_data: Union[Dict, str]) -> str:
        """Construct a prompt for the executor from the plan data."""
        if isinstance(plan_data, str):
            return f"Execute this plan:\n{plan_data}"
            
        title = plan_data.get("title", "Execution Plan")
        description = plan_data.get("description", "")
        steps = plan_data.get("steps", [])
        
        prompt = f"Execute the following plan:\n\nTitle: {title}\nDescription: {description}\n\nSteps:\n"
        
        if isinstance(steps, list):
            for i, step in enumerate(steps, 1):
                step_title = step.get("title", "Untitled Step")
                step_desc = step.get("description", "")
                prompt += f"{i}. {step_title}\n   {step_desc}\n"
                
                tool_calls = step.get("tool_calls", [])
                if tool_calls:
                    prompt += "   Suggested tools:\n"
                    for tc in tool_calls:
                        name = tc.get("name")
                        params = tc.get("parameters", {})
                        prompt += f"   - {name}: {params}\n"
        
        return prompt

    def _track_metrics(self, session_id: str, project_id: Optional[str]):
        """Track session metrics."""
        try:
            from database import get_db_manager
            
            metrics_config = AgentConfig.get_metrics_config()
            if metrics_config.get("enabled", True):
                # We need to run this async, but we are in a sync method?
                # No, process_message_stream is async.
                # But we can't await here easily without making this method async
                # and we are calling it from an async generator.
                # We can just fire and forget or use a task.
                pass 
                # For now, skipping explicit metrics tracking call here as it requires async
                # and the agents track their own metrics per message.
        except Exception as e:
            logger.error(f"Failed to track session metrics: {e}")


# Global instance
_multi_agent_manager = None


def get_multi_agent_manager() -> MultiAgentManager:
    """Get the global multi-agent manager instance."""
    global _multi_agent_manager
    if _multi_agent_manager is None:
        _multi_agent_manager = MultiAgentManager()
    return _multi_agent_manager
