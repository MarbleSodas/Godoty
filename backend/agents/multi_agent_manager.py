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
import time
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
        # Store project paths per session for database persistence
        self._session_project_paths: Dict[str, str] = {}
        logger.info(f"MultiAgentManager initialized with storage: {self.storage_dir}")

    def create_session(self, session_id: str, title: Optional[str] = None, project_path: Optional[str] = None) -> str:
        """
        Create a new multi-agent session with shared conversation context.

        In planning mode, both the planning and executor agents share the same
        FileSessionManager, allowing the executor to read the full planning
        conversation without explicit plan extraction.

        In fast mode, the executor works independently without a planning phase.

        Args:
            session_id: Unique session identifier
            title: Optional session title (e.g., first user message)
            project_path: Optional project path for database storage

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

            # --- Build Executor Graph ---
            # This graph contains the Executor Agent
            # Uses the SAME session_manager as planning graph for shared conversation context
            builder_executor = GraphBuilder()
            builder_executor.add_node(executor_agent.agent, "executor")
            builder_executor.set_entry_point("executor")
            builder_executor.set_session_manager(session_manager)  # Shared session!
            builder_executor.set_max_node_executions(50)
            builder_executor.set_execution_timeout(600)  # Longer timeout for execution
            executor_graph = builder_executor.build()

            self._active_graphs[session_id] = {
                "planning": planning_graph,
                "executor": executor_graph,
                "shared_session": session_manager  # Store reference for debugging/access
            }

            # Process title if provided (e.g., from user prompt)
            processed_title = title
            if title and len(title) > 50:
                # Clean up the title for display
                processed_title = title.strip()
                # Replace newlines with spaces
                processed_title = ' '.join(processed_title.split())
                # Truncate to reasonable length for title
                if len(processed_title) > 50:
                    processed_title = processed_title[:50] + "..."

            # Store session metadata
            metadata = {
                "title": processed_title or f"Session {session_id}",
                "created_at": datetime.now().isoformat()
            }
            self._save_session_metadata(session_id, metadata)

            # NEW: Also save session to database if project_path is provided
            if project_path:
                try:
                    db = ProjectDB(project_path)
                    # Initialize session with empty chat history
                    db.save_session(session_id, [])
                    logger.info(f"Saved session {session_id} to database for project: {project_path}")
                except Exception as db_error:
                    logger.error(f"Failed to save session {session_id} to database: {db_error}")
                    # Don't fail session creation if database save fails

            # Store project path for this session for later use
            if project_path:
                self._session_project_paths[session_id] = project_path

            logger.info(f"Created session {session_id} with title: {processed_title}")
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

            # If no meaningful title in metadata, try to get from conversation
            title = metadata.get("title")
            if not title or title == f"Session {session_id}":
                first_message = self.get_first_user_message(session_id)
                if first_message:
                    # Clean up the content for display
                    title = first_message.strip()
                    # Replace newlines with spaces
                    title = ' '.join(title.split())
                    # Truncate to reasonable length for title
                    if len(title) > 50:
                        title = title[:50] + "..."
                    # Update metadata with the extracted title
                    metadata["title"] = title
                    self._save_session_metadata(session_id, metadata)

            return {
                "session_id": session_id,
                "path": session_path,
                "active": session_id in self._active_graphs,
                "is_running": session_id in self._active_tasks,
                "metadata": metadata
            }
        return None

    def get_session_chat_history(self, session_id: str) -> List[Dict[str, str]]:
        """
        Extract chat history from FileSessionManager format.

        Args:
            session_id: Session ID

        Returns:
            List of messages in format: [{"role": "user", "content": "..."}, ...]
        """
        try:
            session_path = os.path.join(self.storage_dir, f"session_{session_id}", "session.json")
            if not os.path.exists(session_path):
                logger.debug(f"Session file not found: {session_path}")
                return []

            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            # Try different possible keys for messages
            messages = []
            if "messages" in session_data:
                messages = session_data["messages"]
            elif "conversation" in session_data:
                messages = session_data["conversation"]

            # Transform to simple role/content format with metadata preservation
            chat_history = []
            for msg in messages:
                if isinstance(msg, dict) and "role" in msg:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    if role and content:
                        chat_history.append({
                            "role": role,
                            "content": content,
                            # Preserve metadata fields if present
                            "id": msg.get("id"),
                            "timestamp": msg.get("timestamp"),
                            "tokens": msg.get("tokens"),
                            "promptTokens": msg.get("promptTokens"),
                            "completionTokens": msg.get("completionTokens"),
                            "cost": msg.get("cost"),
                            "modelName": msg.get("modelName"),
                            "generationTimeMs": msg.get("generationTimeMs"),
                            "toolCalls": msg.get("toolCalls"),
                            "plan": msg.get("plan"),
                            "events": msg.get("events"),
                            "workflowMetrics": msg.get("workflowMetrics")
                        })

            logger.debug(f"Loaded {len(chat_history)} messages for session {session_id}")
            return chat_history
        except Exception as e:
            logger.error(f"Failed to load chat history for {session_id}: {e}")
            return []

    async def _save_user_message_immediate(self, session_id: str, user_message: str):
        """Immediately save user message to FileSessionManager."""
        try:
            # Get the shared session for this session_id
            if session_id in self._active_graphs:
                shared_session = self._active_graphs[session_id]["shared_session"]

                # Add user message to session immediately
                await shared_session.add_message({
                    "role": "user",
                    "content": user_message,
                    "timestamp": datetime.now().isoformat(),
                    "id": f"user-{int(time.time() * 1000)}"
                })

                logger.info(f"Saved user message immediately for session {session_id}")

        except Exception as e:
            logger.error(f"Failed to save user message immediately: {e}")

    async def _save_assistant_response_complete(self, session_id: str):
        """Save complete assistant response to FileSessionManager and sync to ProjectDB."""
        try:
            # FileSessionManager already has the conversation (handled by Strands)
            # Now sync chat history to ProjectDB for session listing
            if hasattr(self, '_session_project_paths') and session_id in self._session_project_paths:
                project_path = self._session_project_paths[session_id]

                # Get complete chat history from FileSessionManager
                chat_history = await self.get_session_chat_history(session_id)

                # Update ProjectDB session metadata (for session listing)
                db = ProjectDB(project_path)
                db.save_session(session_id, chat_history)

                logger.info(f"Synced complete session {session_id} to ProjectDB")

        except Exception as e:
            logger.error(f"Failed to save assistant response: {e}")

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
        """
        Load session metadata from file with backwards compatibility.

        Handles migration from old structured plan format to conversation-based format.
        """
        metadata_path = os.path.join(self.storage_dir, f"{session_id}_metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)

                # Migration: Remove old plan structure if present
                if "current_plan" in metadata:
                    logger.info(f"Migrating session {session_id} from structured plan format")
                    # Convert to summary for reference
                    plan = metadata.pop("current_plan")
                    if isinstance(plan, dict):
                        metadata["legacy_plan_title"] = plan.get("title", "")
                        metadata["migrated_from_structured"] = True

                return metadata
            except Exception as e:
                logger.error(f"Failed to load metadata for session {session_id}: {e}")

        return {
            "title": f"Session {session_id}",
            "created_at": datetime.now().isoformat()
        }

    def update_session_title(self, session_id: str, title: str) -> None:
        """
        Update the session title in metadata.

        Args:
            session_id: Session ID
            title: New title for the session
        """
        metadata = self._load_session_metadata(session_id)
        metadata["title"] = title
        metadata["title_updated_at"] = datetime.now().isoformat()
        self._save_session_metadata(session_id, metadata)
        logger.info(f"Updated title for session {session_id}: {title}")

    def get_first_user_message(self, session_id: str) -> Optional[str]:
        """
        Extract the first user message from session conversation.

        Args:
            session_id: Session ID

        Returns:
            First user message content or None if not found
        """
        try:
            session_path = os.path.join(self.storage_dir, f"session_{session_id}", "session.json")
            if not os.path.exists(session_path):
                logger.warning(f"Session file not found for {session_id}")
                return None

            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            messages = []
            if "messages" in session_data:
                messages = session_data["messages"]
            elif "conversation" in session_data:
                messages = session_data["conversation"]

            # Find first user message
            for message in messages:
                if isinstance(message, dict) and message.get("role") == "user":
                    content = message.get("content", "")
                    if content:
                        return content

        except Exception as e:
            logger.error(f"Failed to extract first user message for session {session_id}: {e}")

        return None

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

        # Track project path for this session if provided
        if project_path:
            self._session_project_paths[session_id] = project_path

        # Save user message immediately to prevent data loss
        await self._save_user_message_immediate(session_id, message)

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
                # --- Fast Mode: Direct execution with session support ---
                # Uses the executor graph with its own independent session
                logger.info(f"Fast mode execution for session {session_id}")

                # Get executor graph (which has its own session context)
                executor_graph = graphs["executor"]

                # Stream from executor graph
                async for event in executor_graph.stream_async(message):
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

                        # Collect text output to detect plan completion
                        if transformed["type"] == "data" and "text" in transformed.get("data", {}):
                            text_chunk = transformed["data"]["text"]
                            planning_output.append(text_chunk)

                        # Forward all events to frontend (no filtering needed)
                        yield transformed

                # 2. Check if plan was discussed in output
                full_output = "".join(planning_output)
                plan_info = self._detect_plan_completion(full_output)

                if plan_info:
                    # Planning completed, prepare for execution
                    logger.info("Plan discussion completed, preparing execution...")

                    # Generate execution context from planning conversation
                    context_summary = self._generate_execution_context(session_id)

                    # Emit plan_created event (derived from conversation heuristics)
                    yield {
                        "type": "plan_created",
                        "data": {
                            "title": plan_info.get("title", "Execution Plan"),
                            "description": plan_info.get("description", "Based on planning discussion"),
                            "steps": [],  # No structured steps in pure conversation mode
                            "step_count": plan_info.get("step_count", 0),
                            "is_conversational": True
                        }
                    }

                # 3. If plan discussed, run executor graph
                if plan_info:
                    logger.info("Executing plan based on conversation...")
                    executor_graph = graphs["executor"]

                    # Create execution message with conversation context
                    execution_message = f"""Execute the plan we discussed:

{context_summary}

Please proceed with implementation."""

                    # Notify execution started
                    yield {
                        "type": "execution_started",
                        "data": {"message": "Starting execution based on plan..."}
                    }

                    # Track execution phases dynamically based on tool categories
                    execution_phases = []  # Track major operations
                    tool_call_count = 0

                    async for event in executor_graph.stream_async(execution_message):
                        transformed = transform_strands_event(event, agent_type="execution", session_id=session_id)
                        if transformed:
                            # Accumulate metrics if this is a metrics event
                            if transformed["type"] == "metrics":
                                accumulate_workflow_metrics(session_id, transformed, self, "execution")

                            # Track major operations as "steps" dynamically
                            if transformed.get("type") == "tool_use":
                                tool_name = transformed.get("data", {}).get("tool_name", "")

                                # Group related tools into phases
                                phase_name = self._categorize_tool_phase(tool_name)

                                if phase_name and phase_name not in execution_phases:
                                    # Entering a new execution phase
                                    execution_phases.append(phase_name)

                                    # Emit dynamic step started
                                    yield {
                                        "type": "step_started",
                                        "data": {
                                            "step_index": len(execution_phases) - 1,
                                            "step_id": f"phase-{len(execution_phases)}",
                                            "title": phase_name,
                                            "description": f"Executing {phase_name.lower()} operations"
                                        }
                                    }

                            # Forward event to frontend
                            yield transformed

                            # Track tool completions
                            if transformed.get("type") == "tool_result":
                                tool_call_count += 1

                    # Mark final phase complete
                    if execution_phases:
                        yield {
                            "type": "step_completed",
                            "data": {
                                "step_index": len(execution_phases) - 1,
                                "step_id": f"phase-{len(execution_phases)}",
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
            # Save complete session to ProjectDB after processing
            try:
                await self._save_assistant_response_complete(session_id)
            except Exception as e:
                logger.error(f"Failed to save session completion: {e}")

            # Cleanup task registration
            if session_id in self._active_tasks and self._active_tasks[session_id] == current_task:
                del self._active_tasks[session_id]

    def _generate_execution_context(self, session_id: str) -> str:
        """
        Generate execution context from planning conversation.

        Returns key messages from planning session:
        - Original user request
        - Final plan summary from planning agent
        - Critical decisions or constraints

        Args:
            session_id: Session ID to extract context from

        Returns:
            Formatted context summary string
        """
        try:
            # Load session from FileSessionManager
            session_path = os.path.join(self.storage_dir, f"session_{session_id}", "session.json")
            if not os.path.exists(session_path):
                logger.warning(f"Session file not found for {session_id}")
                return "No planning context available."

            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            # Extract messages from session
            # Strands FileSessionManager stores messages in a specific format
            messages = []
            if "messages" in session_data:
                messages = session_data["messages"]
            elif "conversation" in session_data:
                messages = session_data["conversation"]

            if not messages:
                logger.warning(f"No messages found in session {session_id}")
                return "No planning context available."

            # Extract key messages:
            # 1. First user message (original request)
            # 2. Last 2-3 assistant messages (final plan)
            context_parts = []

            # Find first user message
            first_user = next((m for m in messages if m.get("role") == "user"), None)
            if first_user:
                content = first_user.get("content", "")
                context_parts.append(f"Original Request: {content}")

            # Find last few assistant messages
            assistant_messages = [m for m in messages if m.get("role") == "assistant"]
            for msg in assistant_messages[-2:]:
                content = msg.get("content", "")
                # Truncate if too long to prevent context overflow
                if len(content) > 800:
                    content = content[:800] + "..."
                context_parts.append(f"Plan: {content}")

            return "\n\n".join(context_parts)

        except Exception as e:
            logger.error(f"Failed to generate execution context: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return "Context extraction failed."

    def _detect_plan_completion(self, conversation_text: str) -> Optional[Dict[str, Any]]:
        """
        Analyze planning conversation to detect when plan is ready.

        Uses heuristics to identify when planning agent has completed the plan:
        - Mentions execution, steps, or plan
        - Has structured sections (##, numbered lists)
        - Discusses tools and implementation

        Args:
            conversation_text: Full text from planning conversation

        Returns:
            Plan summary dict for frontend event, or None if incomplete
        """
        text_lower = conversation_text.lower()

        # Heuristics for plan completion
        indicators = [
            "execution steps" in text_lower,
            "step 1" in text_lower or "1." in conversation_text,
            "i recommend" in text_lower,
            "we should" in text_lower,
            "execution plan" in text_lower,
            "## execution" in text_lower,
            "## objective" in text_lower
        ]

        if sum(indicators) >= 2:
            # Extract rough step count from text
            step_count = max(
                conversation_text.count("\n1."),
                conversation_text.count("Step 1"),
                conversation_text.count("**1.")
            )

            # Try to extract title from headers
            title = "Execution Plan"
            if "## Objective" in conversation_text:
                # Extract objective as title
                lines = conversation_text.split("\n")
                for i, line in enumerate(lines):
                    if "## Objective" in line and i + 1 < len(lines):
                        title = lines[i + 1].strip()[:100]
                        break

            return {
                "title": title,
                "description": "Plan created from conversation",
                "steps": [],  # No structured steps in pure conversation mode
                "step_count": max(step_count, 1),
                "is_conversational": True
            }

        return None

    def _categorize_tool_phase(self, tool_name: str) -> Optional[str]:
        """
        Categorize tools into execution phases for dynamic step tracking.

        Maps individual tool calls to higher-level execution phases,
        allowing the system to emit step_started/step_completed events
        even without a structured plan.

        Args:
            tool_name: Name of the tool being called

        Returns:
            Phase name string, or None if tool doesn't map to a known phase
        """
        phase_mapping = {
            "Scene Creation": ["create_scene", "open_scene"],
            "Node Management": ["create_node", "delete_node", "modify_node_property", "reparent_node"],
            "File Operations": ["write_file", "read_file", "delete_file", "modify_gdscript_method", "add_gdscript_method"],
            "Scene Analysis": ["analyze_scene_tree", "inspect_scene_file", "search_nodes", "get_project_overview"],
            "Testing & Validation": ["play_scene", "stop_playing", "capture_visual_context", "get_debug_output", "capture_editor_viewport"]
        }

        for phase, tools in phase_mapping.items():
            if tool_name in tools:
                return phase

        return None

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
