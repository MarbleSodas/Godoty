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

from agents.planning_agent import get_planning_agent
from agents.config import AgentConfig
from agents.db import ProjectDB
from agents.global_sequence_manager import GlobalSequenceManager
from agents.streaming_metrics_tracker import StreamingMetricsTracker
from agents.metrics_buffer import MetricsBuffer
from agents.event_utils import handle_session_cancellation, recover_session_metrics

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

        # Initialize GlobalSequenceManager for proper message ordering across agents
        self.global_sequence_manager = GlobalSequenceManager(self.storage_dir)

        # Initialize StreamingMetricsTracker for partial metrics collection
        self.streaming_metrics_tracker = StreamingMetricsTracker()

        # Initialize MetricsBuffer for recovery on cancellation
        self.metrics_buffer = MetricsBuffer(self.storage_dir)

        # Register recovery callback with metrics buffer
        self.metrics_buffer.register_recovery_callback(self._recover_metrics_callback)

        # Store graphs as a dict of dicts: session_id -> {"planning": Graph, "fast": Graph}
        self._active_graphs: Dict[str, Dict[str, Graph]] = {}
        # Store active asyncio tasks: session_id -> asyncio.Task
        self._active_tasks: Dict[str, asyncio.Task] = {}
        # Store workflow metrics accumulators: session_id -> WorkflowMetricsAccumulator
        self._workflow_metrics: Dict[str, WorkflowMetricsAccumulator] = {}
        # Store project paths per session for database persistence
        self._session_project_paths: Dict[str, str] = {}
        # Store agent IDs per session for sequence tracking
        self._session_agent_ids: Dict[str, Dict[str, str]] = {}  # session_id -> {agent_type: agent_id}
        # Store active tracking sessions for metrics
        self._active_tracking_sessions: Dict[str, str] = {}  # session_id -> model_name

        logger.info(f"MultiAgentManager initialized with storage: {self.storage_dir}")
        logger.info("GlobalSequenceManager initialized for cross-agent message ordering")
        logger.info("StreamingMetricsTracker and MetricsBuffer initialized for partial metrics handling")

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
            # Get planning agent
            planning_agent = get_planning_agent()

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

            # Explicitly initialize planning agent with session manager to enable message persistence
            session_manager.initialize(planning_agent.agent)
            logger.info(f"Connected planning agent to session manager for session {session_id}")

            # CRITICAL: Register session manager hooks directly with planning agent
            # This fixes the core issue where Graph execution bypasses normal hook registration
            planning_agent.agent.hooks.add_hook(session_manager)

            # Verify hook registration is successful
            planning_hooks_registered = planning_agent.agent.hooks.has_callbacks()
            logger.info(f"Planning hook registration status: {planning_hooks_registered}")

            # Track planning agent ID for sequence management
            planning_agent_id = getattr(planning_agent.agent, 'agent_id', f"planning_{session_id}")

            self._session_agent_ids[session_id] = {
                "planning": planning_agent_id
            }

            self._active_graphs[session_id] = {
                "planning": planning_graph,
                "shared_session": session_manager,  # Store reference for debugging/access
                "agent_ids": {
                    "planning": planning_agent_id
                }
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

            # Initialize session in database (use default path if none provided)
            try:
                # Use provided project_path or default to current working directory
                db_project_path = project_path or os.getcwd()
                db = ProjectDB(db_project_path)
                # Initialize session metadata (chat history in FileSessionManager)
                db.save_session(session_id)
                logger.info(f"Initialized session {session_id} in database for project: {db_project_path}")
            except Exception as db_error:
                logger.error(f"Failed to initialize session {session_id} in database: {db_error}")
                # Don't fail session creation if database save fails

            # Store project path for this session for later use
            self._session_project_paths[session_id] = db_project_path

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
        try:
            # Check if session exists in FileSessionManager structure
            session_dir = os.path.join(self.storage_dir, f"session_{session_id}")
            session_path = os.path.join(session_dir, "session.json")

            # Also check for legacy flat file structure
            legacy_session_path = os.path.join(self.storage_dir, f"{session_id}.json")

            if os.path.exists(session_path):
                logger.debug(f"Found session directory structure for {session_id}")
                actual_session_path = session_path
            elif os.path.exists(legacy_session_path):
                logger.debug(f"Found legacy session file for {session_id}")
                actual_session_path = legacy_session_path
            else:
                logger.debug(f"Session not found: {session_id}")
                return None

            # Load session metadata
            metadata = self._load_session_metadata(session_id)

            # If no meaningful title in metadata, try to get from conversation
            title = metadata.get("title")
            if not title or title == f"Session {session_id}":
                try:
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
                        logger.debug(f"Extracted title from first message: {title}")
                except Exception as e:
                    logger.warning(f"Failed to extract title from conversation for session {session_id}: {e}")
                    # Keep default title if extraction fails
                    metadata["title"] = metadata.get("title", f"Session {session_id}")

            return {
                "session_id": session_id,
                "path": actual_session_path,
                "active": session_id in self._active_graphs,
                "is_running": session_id in self._active_tasks,
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None

    def get_session_chat_history(self, session_id: str, format: str = "openai") -> List[Dict[str, Any]]:
        """
        Extract chat history from FileSessionManager using global sequence ordering.

        This method uses the GlobalSequenceManager to ensure proper chronological
        ordering of messages across planning and execution agents.

        Args:
            session_id: Session ID
            format: Output format ("openai" for role/content, "full" for complete data)

        Returns:
            List of messages in proper chronological order
        """
        try:
            # First try to get ordered messages from GlobalSequenceManager
            ordered_messages = self.global_sequence_manager.get_ordered_messages(session_id)

            if ordered_messages:
                # We have sequence information, use it
                logger.debug(f"Using global sequence ordering for session {session_id}")
                return self._format_ordered_messages(ordered_messages, format)

            # Fallback to traditional method for backward compatibility
            logger.debug(f"No global sequence data for session {session_id}, using fallback method")

            # Use FileSessionManager to load messages properly
            session_manager = FileSessionManager(
                session_id=session_id,
                storage_dir=self.storage_dir
            )

            # Check if session exists
            session_dir = os.path.join(self.storage_dir, f"session_{session_id}")
            if not os.path.exists(session_dir):
                logger.debug(f"Session directory not found: {session_dir}")
                return []

            # Load session metadata to get agent IDs
            session_data = session_manager.read_session(session_id)
            if not session_data:
                logger.debug(f"Session data not found for {session_id}")
                return []

            # Get all agents for this session
            # Session dataclass doesn't contain agent_ids, start with empty list
            agent_ids = []
            if not agent_ids:
                # Try to discover agent directories
                agents_dir = os.path.join(session_dir, "agents")
                if os.path.exists(agents_dir):
                    agent_ids = [d.replace("agent_", "") for d in os.listdir(agents_dir)
                               if d.startswith("agent_")]

            # Collect messages from all agents
            agent_messages = {}
            for agent_id in agent_ids:
                try:
                    # Use list_messages API to get all messages for this agent
                    messages = session_manager.list_messages(
                        session_id=session_id,
                        agent_id=agent_id,
                        offset=0,
                        limit=1000  # Large limit to get all messages
                    )

                    # Store messages by agent for reconstruction
                    agent_messages[agent_id] = []
                    for msg in messages:
                        if isinstance(msg, dict) and "role" in msg:
                            agent_messages[agent_id].append(msg)

                except Exception as e:
                    logger.error(f"Failed to load messages for agent {agent_id}: {e}")
                    continue

            # Use GlobalSequenceManager to reconstruct order
            reconstructed_messages = self.global_sequence_manager.reconstruct_session_order(
                session_id, agent_messages
            )

            # Format and return messages
            if format == "openai":
                return self._format_messages_openai(reconstructed_messages)
            else:
                return reconstructed_messages

        except Exception as e:
            logger.error(f"Failed to load chat history for {session_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _format_ordered_messages(self, ordered_messages: List[Dict[str, Any]], format: str) -> List[Dict[str, Any]]:
        """
        Format messages from GlobalSequenceManager into the requested format.

        Args:
            ordered_messages: Messages with global sequence ordering
            format: Output format ("openai" or "full")

        Returns:
            Formatted messages
        """
        formatted_messages = []

        for msg_info in ordered_messages:
            # For now, we need to load the actual message content from FileSessionManager
            # In a future enhancement, we could store the full message content in the sequence manager
            try:
                session_manager = FileSessionManager(
                    session_id=msg_info["session_id"],
                    storage_dir=self.storage_dir
                )

                messages = session_manager.list_messages(
                    session_id=msg_info["session_id"],
                    agent_id=msg_info["agent_id"],
                    offset=0,
                    limit=1000
                )

                # Find the specific message by timestamp or other criteria
                for msg in messages:
                    if isinstance(msg, dict):
                        msg_timestamp = msg.get("timestamp") or msg.get("created_at", 0)
                        if abs(msg_timestamp - msg_info["timestamp"]) < 1:  # Within 1 second
                            if format == "openai":
                                formatted_msg = self._convert_message_to_openai(msg)
                                formatted_msg["global_sequence"] = msg_info["global_sequence"]
                                formatted_messages.append(formatted_msg)
                            else:
                                msg["global_sequence"] = msg_info["global_sequence"]
                                formatted_messages.append(msg)
                            break

            except Exception as e:
                logger.error(f"Failed to format message {msg_info}: {e}")
                continue

        return formatted_messages

    def _format_messages_openai(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert messages to OpenAI format (role/content).

        Args:
            messages: Raw messages from FileSessionManager

        Returns:
            Messages in OpenAI format
        """
        openai_messages = []

        for msg in messages:
            if isinstance(msg, dict) and "role" in msg:
                role = msg.get("role")
                content = msg.get("content", "")

                # Handle different content formats
                if isinstance(content, list):
                    # Content is array of content blocks
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    content = "\n".join(text_parts)
                elif not isinstance(content, str):
                    content = str(content)

                if role and content:
                    openai_msg = {
                        "role": role,
                        "content": content,
                        # Preserve metadata if present
                        "id": msg.get("id"),
                        "timestamp": msg.get("timestamp") or msg.get("created_at"),
                        "tokens": msg.get("tokens"),
                        "cost": msg.get("cost"),
                        "model_name": msg.get("model_name")
                    }
                    openai_messages.append(openai_msg)

        return openai_messages

    def _convert_message_to_openai(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a single message to OpenAI format.

        Args:
            msg: Raw message

        Returns:
            Message in OpenAI format
        """
        role = msg.get("role")
        content = msg.get("content", "")

        # Handle different content formats
        if isinstance(content, list):
            # Content is array of content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)
        elif not isinstance(content, str):
            content = str(content)

        return {
            "role": role,
            "content": content,
            # Preserve metadata if present
            "id": msg.get("id"),
            "timestamp": msg.get("timestamp") or msg.get("created_at"),
            "tokens": msg.get("tokens"),
            "cost": msg.get("cost"),
            "model_name": msg.get("model_name")
        }


    async def _save_assistant_response_complete(self, session_id: str):
        """Mark session completion (FileSessionManager handles persistence automatically)."""
        try:
            # FileSessionManager already has the conversation (handled by Strands hooks)
            # No need to manually sync - Strands persists via session manager hooks
            logger.info(f"Session {session_id} complete (persisted by FileSessionManager)")

        except Exception as e:
            logger.error(f"Failed to mark session completion: {e}")

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        List all available sessions.

        Returns:
            Dictionary of session_id to session details
        """
        sessions = {}

        try:
            if not os.path.exists(self.storage_dir):
                logger.warning(f"Storage directory does not exist: {self.storage_dir}")
                return sessions

            logger.info(f"Scanning for sessions in: {self.storage_dir}")

            # Look for session directories (FileSessionManager structure)
            for item_name in os.listdir(self.storage_dir):
                item_path = os.path.join(self.storage_dir, item_name)

                # Check if this is a session directory
                if os.path.isdir(item_path) and item_name.startswith("session_"):
                    # Extract session ID from directory name
                    session_id = item_name[8:]  # Remove "session_" prefix
                    logger.debug(f"Found session directory: {item_name} -> session_id: {session_id}")

                    session = self.get_session(session_id)
                    # Filter hidden sessions
                    if session and not session.get("metadata", {}).get("is_hidden", False):
                        sessions[session_id] = session
                    else:
                        logger.debug(f"Skipping hidden or invalid session: {session_id}")

                # Also check for legacy flat session files
                elif (os.path.isfile(item_path) and
                      item_name.endswith(".json") and
                      not item_name.endswith("_metadata.json")):
                    session_id = item_name[:-5]  # Remove .json extension
                    logger.debug(f"Found legacy session file: {item_name} -> session_id: {session_id}")

                    session = self.get_session(session_id)
                    # Filter hidden sessions
                    if session and not session.get("metadata", {}).get("is_hidden", False):
                        sessions[session_id] = session

            logger.info(f"Found {len(sessions)} visible sessions")
            return sessions

        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
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

        # Strands session manager handles message persistence automatically via hooks
        # No need to manually save - messages are persisted as they're added to the conversation

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

        # Initialize metrics tracking for this session
        self._active_tracking_sessions[session_id] = "unknown"  # Will be updated when we know the model

        try:
            # Import shared event utility
            from agents.event_utils import transform_strands_event, accumulate_workflow_metrics

            if mode == "fast":
                # --- Fast Mode: Direct execution with planning agent ---
                # Simplified fast mode uses planning agent for immediate tool execution
                logger.info(f"Fast mode execution for session {session_id}")

                # Get planning graph for direct execution (executor agent removed)
                planning_graph = graphs["planning"]

                # Stream from planning graph
                async for event in planning_graph.stream_async(message):
                    # Transform event with execution agent type
                    transformed = transform_strands_event(event, agent_type="execution", session_id=session_id)
                    if transformed:
                        # Update model tracking if we get model information
                        if transformed.get("type") == "metrics":
                            model_id = transformed.get("data", {}).get("model_id", "unknown")
                            if self._active_tracking_sessions.get(session_id) == "unknown":
                                self._active_tracking_sessions[session_id] = model_id
                                # Start streaming metrics tracking
                                self.streaming_metrics_tracker.start_session_tracking(session_id, model_id)

                            # Accumulate partial metrics in streaming tracker
                            self.streaming_metrics_tracker.accumulate_partial_usage(event, session_id)

                            # Accumulate metrics if this is a metrics event
                            accumulate_workflow_metrics(session_id, transformed, self, "execution")

                            # Also save individual message metrics to database
                            if project_path and session_id in self._session_project_paths:
                                try:
                                    db = ProjectDB(self._session_project_paths[session_id])
                                    metrics_data = transformed.get("data", {})

                                    # Get current partial metrics from tracker
                                    partial_metrics = self.streaming_metrics_tracker.get_latest_metrics(session_id)

                                    db.record_message_metric(
                                        session_id=session_id,
                                        message_id=metrics_data.get("message_id", f"msg-{int(time.time()*1000)}"),
                                        role="assistant",
                                        cost=metrics_data.get("cost", 0.0),
                                        tokens=metrics_data.get("total_tokens", 0),
                                        model_name=metrics_data.get("model_id", "unknown"),
                                        prompt_tokens=metrics_data.get("input_tokens", 0),
                                        completion_tokens=metrics_data.get("output_tokens", 0)
                                    )

                                    # Buffer partial metrics for recovery
                                    if partial_metrics and not partial_metrics.is_complete:
                                        self.metrics_buffer.add_metric(
                                            session_id=session_id,
                                            message_id=metrics_data.get("message_id", f"partial-{int(time.time()*1000)}"),
                                            agent_type="execution",
                                            metrics=partial_metrics,
                                            is_finalized=False
                                        )

                                except Exception as e:
                                    logger.error(f"Failed to save individual message metric: {e}")

                        yield transformed
                    
            else:
                # --- Planning Mode: Plan then Execute ---
                planning_graph = graphs["planning"]
                submitted_plan = None
                planning_output = []  # Collect text output to detect execution plan

                # CRITICAL: Verify hooks are active before execution
                if not self._verify_agent_hooks(session_id):
                    logger.error(f"Agent hooks verification failed for session {session_id}. Message persistence may not work.")
                    yield {
                        "type": "error",
                        "data": {"error": "Session hooks are not properly registered"}
                    }
                    return

                # 1. Run Planning Graph
                async for event in planning_graph.stream_async(message):
                    transformed = transform_strands_event(event, agent_type="planning", session_id=session_id)
                    if transformed:
                        # Update model tracking if we get model information
                        if transformed.get("type") == "metrics":
                            model_id = transformed.get("data", {}).get("model_id", "unknown")
                            if self._active_tracking_sessions.get(session_id) == "unknown":
                                self._active_tracking_sessions[session_id] = model_id
                                # Start streaming metrics tracking
                                self.streaming_metrics_tracker.start_session_tracking(session_id, model_id)

                            # Accumulate partial metrics in streaming tracker
                            self.streaming_metrics_tracker.accumulate_partial_usage(event, session_id)

                            # Accumulate metrics if this is a metrics event
                            accumulate_workflow_metrics(session_id, transformed, self, "planning")

                            # Also save individual message metrics to database
                            if project_path and session_id in self._session_project_paths:
                                try:
                                    db = ProjectDB(self._session_project_paths[session_id])
                                    metrics_data = transformed.get("data", {})

                                    # Get current partial metrics from tracker
                                    partial_metrics = self.streaming_metrics_tracker.get_latest_metrics(session_id)

                                    db.record_message_metric(
                                        session_id=session_id,
                                        message_id=metrics_data.get("message_id", f"msg-{int(time.time()*1000)}"),
                                        role="assistant",
                                        cost=metrics_data.get("cost", 0.0),
                                        tokens=metrics_data.get("total_tokens", 0),
                                        model_name=metrics_data.get("model_id", "unknown"),
                                        prompt_tokens=metrics_data.get("input_tokens", 0),
                                        completion_tokens=metrics_data.get("output_tokens", 0)
                                    )

                                    # Buffer partial metrics for recovery
                                    if partial_metrics and not partial_metrics.is_complete:
                                        self.metrics_buffer.add_metric(
                                            session_id=session_id,
                                            message_id=metrics_data.get("message_id", f"partial-{int(time.time()*1000)}"),
                                            agent_type="planning",
                                            metrics=partial_metrics,
                                            is_finalized=False
                                        )

                                except Exception as e:
                                    logger.error(f"Failed to save individual message metric: {e}")

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

                # 3. If plan discussed, execute using planning graph
                if plan_info:
                    logger.info("Executing plan based on conversation...")
                    planning_graph = graphs["planning"]

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

                    async for event in planning_graph.stream_async(execution_message):
                        transformed = transform_strands_event(event, agent_type="execution", session_id=session_id)
                        if transformed:
                            # Update model tracking and accumulate partial metrics
                            if transformed.get("type") == "metrics":
                                model_id = transformed.get("data", {}).get("model_id", "unknown")
                                if self._active_tracking_sessions.get(session_id) == "unknown":
                                    self._active_tracking_sessions[session_id] = model_id
                                    # Start streaming metrics tracking if not already started
                                    self.streaming_metrics_tracker.start_session_tracking(session_id, model_id)

                                # Accumulate partial metrics in streaming tracker
                                self.streaming_metrics_tracker.accumulate_partial_usage(event, session_id)

                                # Accumulate metrics if this is a metrics event
                                accumulate_workflow_metrics(session_id, transformed, self, "execution")

                                # Also save individual message metrics to database
                                if project_path and session_id in self._session_project_paths:
                                    try:
                                        db = ProjectDB(self._session_project_paths[session_id])
                                        metrics_data = transformed.get("data", {})

                                        # Get current partial metrics from tracker
                                        partial_metrics = self.streaming_metrics_tracker.get_latest_metrics(session_id)

                                        db.record_message_metric(
                                            session_id=session_id,
                                            message_id=metrics_data.get("message_id", f"msg-{int(time.time()*1000)}"),
                                            role="assistant",
                                            cost=metrics_data.get("cost", 0.0),
                                            tokens=metrics_data.get("total_tokens", 0),
                                            model_name=metrics_data.get("model_id", "unknown"),
                                            prompt_tokens=metrics_data.get("input_tokens", 0),
                                            completion_tokens=metrics_data.get("output_tokens", 0)
                                        )

                                        # Buffer partial metrics for recovery
                                        if partial_metrics and not partial_metrics.is_complete:
                                            self.metrics_buffer.add_metric(
                                                session_id=session_id,
                                                message_id=metrics_data.get("message_id", f"partial-{int(time.time()*1000)}"),
                                                agent_type="execution",
                                                metrics=partial_metrics,
                                                is_finalized=False
                                            )

                                    except Exception as e:
                                        logger.error(f"Failed to save individual message metric: {e}")

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

                # CRITICAL: Verify message persistence after execution
                if not self._verify_message_persistence(session_id):
                    logger.warning(f"Message persistence verification failed for session {session_id}. No message files were created.")
                else:
                    logger.info(f"Message persistence verification passed for session {session_id}")

            # Track session-level metrics if enabled
            self._track_metrics(session_id, project_path)

        except asyncio.CancelledError:
            logger.info(f"Task cancelled for session {session_id}")

            # Handle cancellation with graceful metrics capture
            try:
                cancellation_result = self.handle_cancellation(session_id)

                # Emit cancellation event with metrics information
                yield {
                    "type": "cancellation_handled",
                    "data": {
                        "session_id": session_id,
                        "metrics_captured": cancellation_result.get("metrics_captured", False),
                        "partial_tokens": cancellation_result.get("partial_tokens", 0),
                        "partial_cost": cancellation_result.get("partial_cost", 0.0),
                        "message": "Operation cancelled by user. Partial metrics have been captured for recovery."
                    }
                }

                # Clean up tracking resources
                self.cleanup_session_resources(session_id)

            except Exception as cancel_error:
                logger.error(f"Error during cancellation handling for session {session_id}: {cancel_error}")
                yield {
                    "type": "cancellation_error",
                    "data": {
                        "session_id": session_id,
                        "error": str(cancel_error),
                        "message": "Operation cancelled but metrics capture failed"
                    }
                }

            yield {"type": "error", "data": {"message": "Operation cancelled by user"}}
            raise
        except Exception as e:
            logger.error(f"Error processing message stream in session {session_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield {"type": "error", "data": {"message": str(e)}}
        finally:
            # Finalize metrics tracking for successful completion
            try:
                if session_id in self._active_tracking_sessions:
                    # Finalize the metrics and mark as complete
                    final_metrics = self.streaming_metrics_tracker.finalize_metrics(session_id)

                    if final_metrics and final_metrics.is_complete:
                        # Buffer the final complete metrics
                        self.metrics_buffer.add_metric(
                            session_id=session_id,
                            message_id=f"final-{int(time.time()*1000)}",
                            agent_type="complete",
                            metrics=final_metrics,
                            is_finalized=True
                        )

                        logger.info(f"Finalized metrics tracking for completed session {session_id}: "
                                 f"{final_metrics.total_tokens} tokens, ${final_metrics.cost:.6f}")

            except Exception as metrics_error:
                logger.error(f"Failed to finalize metrics for session {session_id}: {metrics_error}")

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

    def _verify_agent_hooks(self, session_id: str) -> bool:
        """Verify that agent hooks are properly registered and active."""
        try:
            graphs = self._active_graphs.get(session_id)
            if not graphs:
                logger.error(f"No active graphs found for session {session_id}")
                return False

            # Check that planning agent has active hooks
            planning_graph = graphs.get("planning")
            planning_hooks_active = False

            if planning_graph and planning_graph.nodes:
                planning_node = planning_graph.nodes["planner"]
                planning_hooks_active = (hasattr(planning_node.executor, 'hooks') and
                                       planning_node.executor.hooks.has_callbacks())
                logger.info(f"Planning agent hooks active: {planning_hooks_active}")

            if not planning_hooks_active:
                logger.error(f"Hook verification failed for session {session_id} - Planning: {planning_hooks_active}")
                return False

            return True
        except Exception as e:
            logger.error(f"Hook verification failed: {e}")
            return False

    def _verify_message_persistence(self, session_id: str) -> bool:
        """Verify that message files are created after agent execution."""
        try:
            session_path = os.path.join(self.storage_dir, f"session_{session_id}", "agents")

            if not os.path.exists(session_path):
                logger.error(f"Session agents directory not found: {session_path}")
                return False

            # Check for message files in agent directories
            planning_messages_dir = os.path.join(session_path, "agent_planning-agent", "messages")
            executor_messages_dir = os.path.join(session_path, "agent_executor-agent", "messages")

            planning_files = []
            executor_files = []

            if os.path.exists(planning_messages_dir):
                planning_files = [f for f in os.listdir(planning_messages_dir) if f.endswith(".json")]

            if os.path.exists(executor_messages_dir):
                executor_files = [f for f in os.listdir(executor_messages_dir) if f.endswith(".json")]

            logger.info(f"Message persistence check - Planning: {len(planning_files)} files, Executor: {len(executor_files)} files")

            return len(planning_files) > 0 or len(executor_files) > 0

        except Exception as e:
            logger.error(f"Message persistence verification failed: {e}")
            return False

    def _recover_metrics_callback(self, session_id: str, buffered_metric) -> bool:
        """
        Recovery callback for MetricsBuffer.

        Attempts to recover metrics by saving them to the database.

        Args:
            session_id: The session ID
            buffered_metric: The BufferedMetric object to recover

        Returns:
            True if recovery was successful, False otherwise
        """
        try:
            if session_id in self._session_project_paths:
                db = ProjectDB(self._session_project_paths[session_id])

                # Convert PartialMetrics to database format
                metrics = buffered_metric.metrics
                agent_type = buffered_metric.agent_type

                # Create a recovery session ID for this operation
                recovery_session_id = f"recovery_{session_id}_{int(time.time()*1000)}"

                # Save as partial metrics with recovery information
                db.create_partial_message_metrics(
                    session_id=session_id,
                    message_id=buffered_metric.message_id,
                    agent_type=agent_type,
                    model_id=metrics.model_name,
                    prompt_tokens=metrics.input_tokens,
                    completion_tokens=metrics.output_tokens,
                    total_tokens=metrics.total_tokens,
                    estimated_cost=metrics.cost,
                    recovery_session_id=recovery_session_id,
                    agent_id=self._session_agent_ids.get(session_id, {}).get(agent_type, f"{agent_type}_agent")
                )

                logger.info(f"Successfully recovered metrics for session {session_id}, message {buffered_metric.message_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to recover metrics for session {session_id}: {e}")

        return False

    def handle_cancellation(self, session_id: str) -> Dict[str, Any]:
        """
        Handle session cancellation with graceful metrics capture.

        This method should be called when a streaming operation is cancelled
        to ensure partial metrics are captured and buffered for recovery.

        Args:
            session_id: The session ID being cancelled

        Returns:
            Dictionary with cancellation handling results
        """
        cancellation_result = {
            "session_id": session_id,
            "metrics_captured": False,
            "metrics_buffered": False,
            "partial_tokens": 0,
            "partial_cost": 0.0,
            "error": None
        }

        try:
            logger.info(f"Handling cancellation for session {session_id}")

            # Use the event_utils cancellation handler
            handle_result = handle_session_cancellation(session_id, self.streaming_metrics_tracker, self.metrics_buffer)

            if handle_result:
                cancellation_result.update(handle_result)

                # Get project path for database operations
                project_path = self._session_project_paths.get(session_id)
                if project_path:
                    try:
                        db = ProjectDB(project_path)

                        # Update session metrics to reflect cancellation
                        db.increment_session_cancellations(session_id)
                        db.update_session_health(session_id, "cancelled")

                        # Store partial metrics information for recovery
                        if handle_result.get("partial_metrics"):
                            partial_metrics = handle_result["partial_metrics"]

                            # Create a recovery session ID
                            recovery_session_id = f"recovery_{session_id}_{int(time.time()*1000)}"

                            # Save partial metrics to database
                            db.create_partial_message_metrics(
                                session_id=session_id,
                                message_id=f"cancelled_{int(time.time()*1000)}",
                                agent_type="mixed",  # Could be planning or execution
                                model_id=partial_metrics.model_name,
                                prompt_tokens=partial_metrics.input_tokens,
                                completion_tokens=partial_metrics.output_tokens,
                                total_tokens=partial_metrics.total_tokens,
                                estimated_cost=partial_metrics.cost,
                                recovery_session_id=recovery_session_id,
                                is_complete=False,
                                completion_status="cancelled"
                            )

                        logger.info(f"Cancellation handled successfully for session {session_id}")

                    except Exception as db_error:
                        logger.error(f"Failed to update database for cancelled session {session_id}: {db_error}")
                        cancellation_result["error"] = str(db_error)

            else:
                cancellation_result["error"] = "Cancellation handler returned no result"

        except Exception as e:
            logger.error(f"Error handling cancellation for session {session_id}: {e}")
            cancellation_result["error"] = str(e)

        return cancellation_result

    def attempt_metrics_recovery(self, session_id: str) -> Dict[str, Any]:
        """
        Attempt to recover metrics for a cancelled session.

        Args:
            session_id: The session ID to recover metrics for

        Returns:
            Dictionary with recovery results
        """
        recovery_result = {
            "session_id": session_id,
            "metrics_recovered": False,
            "recovered_count": 0,
            "failed_count": 0,
            "total_cost": 0.0,
            "total_tokens": 0,
            "error": None
        }

        try:
            logger.info(f"Attempting metrics recovery for session {session_id}")

            # Use the event_utils recovery function
            recovery_stats = recover_session_metrics(session_id, self.metrics_buffer)

            if recovery_stats:
                recovery_result.update({
                    "metrics_recovered": recovery_stats.get("successful", 0) > 0,
                    "recovered_count": recovery_stats.get("successful", 0),
                    "failed_count": recovery_stats.get("failed", 0),
                    "total_tokens": recovery_stats.get("total_tokens", 0),
                    "total_cost": recovery_stats.get("total_cost", 0.0)
                })

                # Update database with recovery information
                project_path = self._session_project_paths.get(session_id)
                if project_path and recovery_stats.get("successful", 0) > 0:
                    try:
                        db = ProjectDB(project_path)

                        # Increment recovered operations count
                        db.increment_recovered_operations(session_id)

                        # Update session health
                        db.update_session_health(session_id, "recovered")

                        # Get and update session health report
                        health_report = db.get_session_health_report(session_id)
                        if health_report:
                            logger.info(f"Session health after recovery: {health_report}")

                    except Exception as db_error:
                        logger.error(f"Failed to update database after recovery for session {session_id}: {db_error}")
                        recovery_result["error"] = str(db_error)

            else:
                recovery_result["error"] = "No recovery stats returned"

        except Exception as e:
            logger.error(f"Error during metrics recovery for session {session_id}: {e}")
            recovery_result["error"] = str(e)

        return recovery_result

    def cleanup_session_resources(self, session_id: str) -> bool:
        """
        Clean up all tracking resources for a session.

        This should be called when a session is completely finished
        to free up memory and clean up tracking data.

        Args:
            session_id: The session ID to clean up

        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            logger.info(f"Cleaning up resources for session {session_id}")

            # Stop metrics tracking
            self.streaming_metrics_tracker.end_session_tracking(session_id)

            # Clear metrics buffer for this session
            self.metrics_buffer.clear_session(session_id, keep_recovered=True)

            # Remove from active tracking sessions
            if session_id in self._active_tracking_sessions:
                del self._active_tracking_sessions[session_id]

            # Clean up old checkpoints and stale metrics
            self.streaming_metrics_tracker.cleanup_old_sessions()
            self.metrics_buffer.cleanup_stale_metrics()

            logger.info(f"Successfully cleaned up resources for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error cleaning up resources for session {session_id}: {e}")
            return False

    def get_session_metrics_summary(self, session_id: str) -> Dict[str, Any]:
        """
        Get a comprehensive metrics summary for a session.

        Args:
            session_id: The session ID

        Returns:
            Dictionary with comprehensive metrics summary
        """
        try:
            summary = {
                "session_id": session_id,
                "tracking_active": session_id in self._active_tracking_sessions,
                "buffered_metrics": 0,
                "pending_recovery": 0,
                "streaming_stats": {},
                "buffer_stats": {},
                "database_health": {}
            }

            # Get streaming metrics tracker statistics
            if session_id in self._active_tracking_sessions:
                streaming_stats = self.streaming_metrics_tracker.get_session_statistics(session_id)
                summary["streaming_stats"] = streaming_stats

            # Get metrics buffer statistics
            buffer_summary = self.metrics_buffer.get_buffer_summary()
            if session_id in buffer_summary["sessions"]:
                session_buffer_stats = buffer_summary["sessions"][session_id]
                summary["buffered_metrics"] = session_buffer_stats["metric_count"]
                summary["pending_recovery"] = session_buffer_stats["pending_count"]
                summary["buffer_stats"] = session_buffer_stats

            # Get database health information
            project_path = self._session_project_paths.get(session_id)
            if project_path:
                try:
                    db = ProjectDB(project_path)
                    health_report = db.get_session_health_report(session_id)
                    summary["database_health"] = health_report or {}
                except Exception as e:
                    logger.error(f"Failed to get database health for session {session_id}: {e}")
                    summary["database_health"]["error"] = str(e)

            return summary

        except Exception as e:
            logger.error(f"Error getting metrics summary for session {session_id}: {e}")
            return {"session_id": session_id, "error": str(e)}


# Global instance
_multi_agent_manager = None


def get_multi_agent_manager() -> MultiAgentManager:
    """Get the global multi-agent manager instance."""
    global _multi_agent_manager
    if _multi_agent_manager is None:
        _multi_agent_manager = MultiAgentManager()
    return _multi_agent_manager
