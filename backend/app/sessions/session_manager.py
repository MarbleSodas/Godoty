"""
Session management for Godoty using Strands FileSessionManager.

Handles session creation, persistence, and project-based storage for
conversation history and agent state.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from strands.session.file_session_manager import FileSessionManager

from app.config import settings

logger = logging.getLogger(__name__)


class GodotySessionManager:
    """
    Session management wrapper for Godoty agents.

    Provides project-based session storage and lifecycle management
    using Strands FileSessionManager as the underlying storage engine.
    """

    def __init__(self, project_path: str):
        """
        Initialize session manager for a project.

        Args:
            project_path: Root path of the Godot project
        """
        self.project_path = Path(project_path).resolve()
        self.sessions_dir = settings.get_project_sessions_dir(str(self.project_path))

        # Ensure sessions directory exists
        self.sessions_dir_path = Path(self.sessions_dir)
        self.sessions_dir_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized session manager for project: {self.project_path}")
        logger.info(f"Sessions directory: {self.sessions_dir}")

    def create_session(self, title: Optional[str] = None) -> str:
        """
        Create a new session and return its ID.

        Args:
            title: Optional session title (auto-generated if not provided)

        Returns:
            Session ID string
        """
        try:
            session_id = str(uuid.uuid4())
            session_title = title or self._generate_session_title()

            # Create session metadata
            session_metadata = {
                "session_id": session_id,
                "title": session_title,
                "project_path": str(self.project_path),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "status": "active",
                "message_count": 0,
                "total_cost": 0.0,
                "model_id": settings.default_godoty_model
            }

            # Create session directory
            session_dir = self._get_session_dir(session_id)
            session_dir.mkdir(exist_ok=True)

            # Save session metadata
            self._save_session_metadata(session_id, session_metadata)

            # Initialize Strands FileSessionManager
            strands_manager = FileSessionManager(session_id=session_id)

            logger.info(f"Created new session: {session_id} - {session_title}")
            return session_id

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def get_session(self, session_id: str) -> FileSessionManager:
        """
        Get Strands FileSessionManager for an existing session.

        Args:
            session_id: Session ID to retrieve

        Returns:
            FileSessionManager instance

        Raises:
            ValueError: If session doesn't exist
        """
        try:
            # Validate session exists
            if not self.session_exists(session_id):
                raise ValueError(f"Session not found: {session_id}")

            # Create Strands FileSessionManager
            strands_manager = FileSessionManager(session_id=session_id)

            logger.debug(f"Retrieved session manager for: {session_id}")
            return strands_manager

        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            raise

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all sessions for the project.

        Returns:
            List of session metadata dictionaries
        """
        try:
            sessions = []

            if not self.sessions_dir_path.exists():
                return sessions

            # Scan session directories
            for session_dir in self.sessions_dir_path.iterdir():
                if session_dir.is_dir():
                    session_id = session_dir.name

                    try:
                        metadata = self._load_session_metadata(session_id)
                        if metadata:
                            sessions.append(metadata)
                    except Exception as e:
                        logger.warning(f"Failed to load metadata for session {session_id}: {e}")

            # Sort by creation date (newest first)
            sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            logger.info(f"Found {len(sessions)} sessions for project")
            return sessions

        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all its data.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            if not self.session_exists(session_id):
                logger.warning(f"Session not found for deletion: {session_id}")
                return False

            session_dir = self._get_session_dir(session_id)

            # Remove session directory and all contents
            import shutil
            shutil.rmtree(session_dir)

            logger.info(f"Deleted session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    def update_session_metadata(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update session metadata.

        Args:
            session_id: Session ID to update
            updates: Dictionary of metadata updates

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            if not self.session_exists(session_id):
                return False

            # Load existing metadata
            metadata = self._load_session_metadata(session_id)
            if not metadata:
                return False

            # Apply updates
            metadata.update(updates)
            metadata["updated_at"] = datetime.utcnow().isoformat()

            # Save updated metadata
            self._save_session_metadata(session_id, metadata)

            logger.debug(f"Updated metadata for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update session metadata {session_id}: {e}")
            return False

    def session_exists(self, session_id: str) -> bool:
        """
        Check if a session exists.

        Args:
            session_id: Session ID to check

        Returns:
            True if session exists, False otherwise
        """
        try:
            session_dir = self._get_session_dir(session_id)
            metadata_file = session_dir / "session.json"
            return session_dir.exists() and metadata_file.exists()
        except Exception:
            return False

    def _get_session_dir(self, session_id: str) -> Path:
        """Get the directory path for a session."""
        return self.sessions_dir_path / f"session_{session_id}"

    def _load_session_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session metadata from file."""
        try:
            metadata_file = self._get_session_dir(session_id) / "session.json"

            if not metadata_file.exists():
                return None

            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"Failed to load session metadata {session_id}: {e}")
            return None

    def _save_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """Save session metadata to file."""
        try:
            metadata_file = self._get_session_dir(session_id) / "session.json"

            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save session metadata {session_id}: {e}")
            raise

    def _generate_session_title(self) -> str:
        """Generate a default session title."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"Godoty Session - {timestamp}"

    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get usage statistics for a session.

        Args:
            session_id: Session ID to get stats for

        Returns:
            Dictionary with session statistics or None if not found
        """
        try:
            if not self.session_exists(session_id):
                return None

            metadata = self._load_session_metadata(session_id)
            if not metadata:
                return None

            # Get additional stats from Strands session if available
            try:
                strands_manager = self.get_session(session_id)
                # This would be enhanced to get actual message count, tokens, etc.
                # from the Strands session data
            except Exception as e:
                logger.warning(f"Could not get Strands session data: {e}")

            return {
                "session_id": session_id,
                "title": metadata.get("title", ""),
                "created_at": metadata.get("created_at"),
                "updated_at": metadata.get("updated_at"),
                "message_count": metadata.get("message_count", 0),
                "total_cost": metadata.get("total_cost", 0.0),
                "status": metadata.get("status", "active"),
                "model_id": metadata.get("model_id", "")
            }

        except Exception as e:
            logger.error(f"Failed to get session stats {session_id}: {e}")
            return None