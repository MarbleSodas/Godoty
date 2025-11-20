"""
Multi-Agent Manager for Godot Assistant.

This module manages multi-agent sessions and orchestration using Strands Agents.
It handles:
- Session creation and persistence
- Multi-agent graph execution
- Message processing
"""

import logging
import os
import warnings
from typing import Dict, Any, Optional, List
from pathlib import Path

# Suppress LangGraph warning before importing strands
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from strands import Agent
from strands.multiagent.graph import Graph, GraphBuilder
from strands.session.file_session_manager import FileSessionManager

from .planning_agent import get_planning_agent
from .executor_agent import get_executor_agent
from .config import AgentConfig

logger = logging.getLogger(__name__)


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
        self._active_graphs: Dict[str, Graph] = {}
        logger.info(f"MultiAgentManager initialized with storage: {self.storage_dir}")

    def create_session(self, session_id: str) -> str:
        """
        Create a new multi-agent session.

        Args:
            session_id: Unique session identifier

        Returns:
            Session ID
        """
        if session_id in self._active_graphs:
            logger.info(f"Session {session_id} already active")
            return session_id

        try:
            # Get agents
            planning_agent = get_planning_agent()
            
            # Create session manager
            session_manager = FileSessionManager(
                session_id=session_id,
                storage_dir=self.storage_dir
            )

            # Create graph using GraphBuilder
            builder = GraphBuilder()
            builder.add_node(planning_agent.agent, "planner")
            builder.set_entry_point("planner")
            builder.set_session_manager(session_manager)

            # Set execution limits to prevent infinite loops
            builder.set_max_node_executions(50)  # Limit total node executions
            builder.set_execution_timeout(300)    # 5 minute timeout

            # Build graph
            graph = builder.build()
            
            self._active_graphs[session_id] = graph
            logger.info(f"Created session {session_id}")
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
            return {
                "session_id": session_id,
                "path": session_path,
                "active": session_id in self._active_graphs
            }
        return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all available sessions.

        Returns:
            List of session details
        """
        sessions = []
        if os.path.exists(self.storage_dir):
            for filename in os.listdir(self.storage_dir):
                if filename.endswith(".json"):
                    session_id = filename[:-5]
                    sessions.append(self.get_session(session_id))
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False otherwise
        """
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

    async def process_message(self, session_id: str, message: str, project_id: Optional[str] = None) -> Any:
        """
        Process a message in a session.

        Args:
            session_id: Session ID
            message: User message
            project_id: Optional project ID for metrics tracking

        Returns:
            Agent response with metrics if enabled
        """
        # Ensure session exists/is loaded
        if session_id not in self._active_graphs:
            if self.get_session(session_id):
                self.create_session(session_id)  # Re-load
            else:
                raise ValueError(f"Session {session_id} not found")

        graph = self._active_graphs[session_id]
        
        # Execute graph
        try:
            logger.info(f"Processing message in session {session_id}")
            result = graph(message)
            
            # Extract response from planner node
            response_text = ""
            if result.results and "planner" in result.results:
                node_result = result.results["planner"]
                response_text = str(node_result.result)
            else:
                response_text = str(result)

            # Track session-level metrics if enabled
            try:
                from agents.config import AgentConfig
                from database import get_db_manager
                
                metrics_config = AgentConfig.get_metrics_config()
                if metrics_config.get("enabled", True):
                    # Get or create session metrics
                    db_manager = get_db_manager()
                    await db_manager.get_or_create_session_metrics(
                        session_id=session_id,
                        project_id=project_id
                    )
                    
                    # Get or create project metrics if project_id provided
                    if project_id:
                        await db_manager.get_or_create_project_metrics(
                            project_id=project_id
                        )
            except Exception as e:
                logger.error(f"Failed to track session metrics: {e}")
                # Don't fail the request if metrics tracking fails
                
            return response_text

        except Exception as e:
            logger.error(f"Error processing message in session {session_id}: {e}")
            raise


    async def process_message_stream(self, session_id: str, message: str, project_id: Optional[str] = None):
        """
        Process a message in a session and stream the response.

        Args:
            session_id: Session ID
            message: User message
            project_id: Optional project ID for metrics tracking

        Yields:
            Dict with event type and data
        """
        # Ensure session exists/is loaded
        if session_id not in self._active_graphs:
            if self.get_session(session_id):
                self.create_session(session_id)  # Re-load
            else:
                raise ValueError(f"Session {session_id} not found")

        graph = self._active_graphs[session_id]
        
        try:
            logger.info(f"Processing message stream in session {session_id}")
            
            # Get the planning agent from the graph
            # Note: This assumes the graph structure has a 'planner' node which is the PlanningAgent
            # In a more complex graph, we might need to stream from the graph execution itself
            # but Strands Graph doesn't natively support streaming intermediate results easily yet
            # so we'll stream from the planner directly for now if possible, or emulate it.
            
            # For now, we'll use the planner's stream method directly if we can access it
            # This is a simplification - ideally we'd stream the graph execution
            
            # Find the planner node
            # This is a bit of a hack - we know the structure from create_session
            planning_agent = get_planning_agent()
            
            # Stream from the agent
            async for event in planning_agent.plan_stream(message):
                yield event
                
            # Track session-level metrics if enabled (after streaming completes)
            try:
                from agents.config import AgentConfig
                from database import get_db_manager
                
                metrics_config = AgentConfig.get_metrics_config()
                if metrics_config.get("enabled", True):
                    db_manager = get_db_manager()
                    await db_manager.get_or_create_session_metrics(
                        session_id=session_id,
                        project_id=project_id
                    )
                    if project_id:
                        await db_manager.get_or_create_project_metrics(project_id=project_id)
            except Exception as e:
                logger.error(f"Failed to track session metrics: {e}")

        except Exception as e:
            logger.error(f"Error processing message stream in session {session_id}: {e}")
            yield {"type": "error", "data": {"message": str(e)}}


# Global instance
_multi_agent_manager = None


def get_multi_agent_manager() -> MultiAgentManager:
    """Get the global multi-agent manager instance."""
    global _multi_agent_manager
    if _multi_agent_manager is None:
        _multi_agent_manager = MultiAgentManager()
    return _multi_agent_manager
