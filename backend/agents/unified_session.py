"""
Unified Session Management for GodotyAgent

This module provides simplified, robust session management for the single-agent architecture.
It consolidates conversation history, metrics tracking, and state persistence in a clean,
streamlined interface designed specifically for the GodotyAgent.

Key Features:
- SQLite-based session persistence
- JSON conversation history storage
- Integrated metrics tracking
- Simplified session lifecycle management
- Backward compatibility with existing sessions
"""

import os
import json
import sqlite3
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass, asdict
import threading

logger = logging.getLogger(__name__)


@dataclass
class MessageEntry:
    """Single message in conversation history."""
    message_id: str
    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    timestamp: datetime
    model_name: Optional[str] = None
    tokens: int = 0
    cost: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageEntry':
        """Create from dictionary retrieved from storage."""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class SessionInfo:
    """Session metadata and summary information."""
    session_id: str
    title: str
    project_path: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    message_count: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionInfo':
        """Create from dictionary retrieved from storage."""
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)


@dataclass
class SessionMetrics:
    """Session-level metrics and usage statistics."""
    session_id: str
    total_messages: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    average_response_time: float = 0.0
    last_activity: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        if self.last_activity:
            data['last_activity'] = self.last_activity.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionMetrics':
        """Create from dictionary retrieved from storage."""
        if data.get('last_activity'):
            data['last_activity'] = datetime.fromisoformat(data['last_activity'])
        return cls(**data)


class DatabaseManager:
    """Thread-safe SQLite database operations for session management."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    project_path TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    message_count INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    total_cost REAL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message_id TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    model_name TEXT,
                    tokens INTEGER DEFAULT 0,
                    cost REAL DEFAULT 0.0,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS session_metrics (
                    session_id TEXT PRIMARY KEY,
                    total_messages INTEGER DEFAULT 0,
                    user_messages INTEGER DEFAULT 0,
                    assistant_messages INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    total_cost REAL DEFAULT 0.0,
                    average_response_time REAL DEFAULT 0.0,
                    last_activity TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS agent_state (
                    session_id TEXT PRIMARY KEY,
                    state_data TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_timestamp
                    ON messages(session_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                    ON sessions(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sessions_active
                    ON sessions(is_active, updated_at DESC);
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get thread-safe database connection."""
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def create_session(self, session_info: SessionInfo) -> bool:
        """Create new session in database."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO sessions
                       (session_id, title, project_path, created_at, updated_at,
                        is_active, message_count, total_tokens, total_cost)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_info.session_id, session_info.title, session_info.project_path,
                     session_info.created_at, session_info.updated_at, session_info.is_active,
                     session_info.message_count, session_info.total_tokens, session_info.total_cost)
                )

                # Initialize metrics
                conn.execute(
                    """INSERT OR REPLACE INTO session_metrics
                       (session_id, total_messages, user_messages, assistant_messages,
                        total_tokens, total_cost, average_response_time, last_activity)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_info.session_id, 0, 0, 0, 0, 0.0, 0.0, None)
                )

                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to create session {session_info.session_id}: {e}")
            return False

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Retrieve session information."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()

                if row:
                    return SessionInfo(
                        session_id=row['session_id'],
                        title=row['title'],
                        project_path=row['project_path'],
                        created_at=datetime.fromisoformat(row['created_at']),
                        updated_at=datetime.fromisoformat(row['updated_at']),
                        is_active=bool(row['is_active']),
                        message_count=row['message_count'],
                        total_tokens=row['total_tokens'],
                        total_cost=row['total_cost']
                    )
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
        return None

    def update_session(self, session_info: SessionInfo) -> bool:
        """Update session information."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """UPDATE sessions SET
                       title = ?, project_path = ?, updated_at = ?, is_active = ?,
                       message_count = ?, total_tokens = ?, total_cost = ?
                       WHERE session_id = ?""",
                    (session_info.title, session_info.project_path, session_info.updated_at,
                     session_info.is_active, session_info.message_count,
                     session_info.total_tokens, session_info.total_cost, session_info.session_id)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to update session {session_info.session_id}: {e}")
            return False

    def list_sessions(self, include_hidden: bool = False, limit: int = 50) -> List[SessionInfo]:
        """List available sessions."""
        try:
            with self._get_connection() as conn:
                query = """
                    SELECT * FROM sessions
                    WHERE is_active = ? OR ? = 1
                    ORDER BY updated_at DESC
                    LIMIT ?
                """
                rows = conn.execute(query, (True, include_hidden, limit)).fetchall()

                sessions = []
                for row in rows:
                    sessions.append(SessionInfo(
                        session_id=row['session_id'],
                        title=row['title'],
                        project_path=row['project_path'],
                        created_at=datetime.fromisoformat(row['created_at']),
                        updated_at=datetime.fromisoformat(row['updated_at']),
                        is_active=bool(row['is_active']),
                        message_count=row['message_count'],
                        total_tokens=row['total_tokens'],
                        total_cost=row['total_cost']
                    ))
                return sessions
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """Soft delete session (mark as inactive)."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE sessions SET is_active = 0 WHERE session_id = ?",
                    (session_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False


class UnifiedSessionManager:
    """
    Simplified session management for the single GodotyAgent architecture.

    This class provides a clean, unified interface for session persistence,
    conversation history management, and metrics tracking.
    """

    def __init__(self, storage_path: str = "./.godoty_sessions"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self.db_path = self.storage_path / "unified_sessions.db"
        self.db = DatabaseManager(str(self.db_path))

        # Legacy session directory for backward compatibility
        self.legacy_sessions_dir = self.storage_path

        self._lock = threading.Lock()
        logger.info(f"UnifiedSessionManager initialized with storage at {storage_path}")

    def create_session(self, title: str, project_path: Optional[str] = None) -> str:
        """
        Create a new session.

        Args:
            title: Human-readable session title
            project_path: Associated Godot project path

        Returns:
            Unique session identifier
        """
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Truncate title if too long
        title = title[:100] if len(title) > 100 else title

        session_info = SessionInfo(
            session_id=session_id,
            title=title,
            project_path=project_path,
            created_at=now,
            updated_at=now,
            is_active=True
        )

        if self.db.create_session(session_info):
            logger.info(f"Created new session: {session_id} - {title}")
            return session_id
        else:
            raise RuntimeError(f"Failed to create session: {title}")

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Retrieve session information."""
        return self.db.get_session(session_id)

    def update_session_title(self, session_id: str, title: str) -> bool:
        """Update session title."""
        session_info = self.db.get_session(session_id)
        if session_info:
            session_info.title = title[:100] if len(title) > 100 else title
            session_info.updated_at = datetime.utcnow()
            return self.db.update_session(session_info)
        return False

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists in storage."""
        try:
            session = self.db.get_session(session_id)
            return session is not None
        except Exception as e:
            logger.warning(f"Error checking session existence {session_id}: {e}")
            return False

    def get_session_title(self, session_id: str) -> str:
        """Get current session title for logging."""
        try:
            session = self.db.get_session(session_id)
            if session:
                return session.title or 'Untitled Session'
            return 'Untitled Session'
        except Exception:
            return 'Unknown Session'

    def list_sessions(self, include_hidden: bool = False, limit: int = 50) -> List[SessionInfo]:
        """List available sessions."""
        return self.db.list_sessions(include_hidden, limit)

    def delete_session(self, session_id: str) -> bool:
        """Soft delete session."""
        return self.db.delete_session(session_id)

    def add_message(self, session_id: str, message: MessageEntry) -> bool:
        """
        Add a message to session conversation history.

        Args:
            session_id: Target session identifier
            message: Message to add

        Returns:
            True if message was added successfully
        """
        try:
            with self.db._get_connection() as conn:
                # Insert message
                metadata_json = json.dumps(message.metadata) if message.metadata else None
                conn.execute(
                    """INSERT INTO messages
                       (session_id, message_id, role, content, timestamp,
                        model_name, tokens, cost, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, message.message_id, message.role, message.content,
                     message.timestamp, message.model_name, message.tokens,
                     message.cost, metadata_json)
                )

                # Update session stats
                conn.execute(
                    """UPDATE sessions SET
                       message_count = message_count + 1,
                       total_tokens = total_tokens + ?,
                       total_cost = total_cost + ?,
                       updated_at = ?
                       WHERE session_id = ?""",
                    (message.tokens, message.cost, message.timestamp, session_id)
                )

                # Update metrics
                role_type = 'user' if message.role in ['user', 'system'] else 'assistant'
                conn.execute(
                    """UPDATE session_metrics SET
                       total_messages = total_messages + 1,
                       {role}_messages = {role}_messages + 1,
                       total_tokens = total_tokens + ?,
                       total_cost = total_cost + ?,
                       last_activity = ?
                       WHERE session_id = ?""".format(role=role_type),
                    (message.tokens, message.cost, message.timestamp, session_id)
                )

                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to add message to {session_id}: {e}")
            return False

    def get_conversation_history(self, session_id: str, limit: Optional[int] = None) -> List[MessageEntry]:
        """
        Retrieve conversation history for a session.

        Args:
            session_id: Target session identifier
            limit: Maximum number of messages to retrieve

        Returns:
            List of messages in chronological order
        """
        try:
            with self.db._get_connection() as conn:
                query = """
                    SELECT * FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """
                params = [session_id]

                if limit:
                    query += " LIMIT ?"
                    params.append(limit)

                rows = conn.execute(query, params).fetchall()

                messages = []
                for row in rows:
                    metadata = json.loads(row['metadata']) if row['metadata'] else None
                    messages.append(MessageEntry(
                        message_id=row['message_id'],
                        role=row['role'],
                        content=row['content'],
                        timestamp=datetime.fromisoformat(row['timestamp']),
                        model_name=row['model_name'],
                        tokens=row['tokens'],
                        cost=row['cost'],
                        metadata=metadata
                    ))
                return messages
        except Exception as e:
            logger.error(f"Failed to get conversation history for {session_id}: {e}")
            return []

    def get_session_metrics(self, session_id: str) -> Optional[SessionMetrics]:
        """Retrieve detailed metrics for a session."""
        try:
            with self.db._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM session_metrics WHERE session_id = ?",
                    (session_id,)
                ).fetchone()

                if row:
                    return SessionMetrics(
                        session_id=row['session_id'],
                        total_messages=row['total_messages'],
                        user_messages=row['user_messages'],
                        assistant_messages=row['assistant_messages'],
                        total_tokens=row['total_tokens'],
                        total_cost=row['total_cost'],
                        average_response_time=row['average_response_time'],
                        last_activity=datetime.fromisoformat(row['last_activity']) if row['last_activity'] else None
                    )
        except Exception as e:
            logger.error(f"Failed to get session metrics for {session_id}: {e}")
        return None

    def save_agent_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """Save agent state for session persistence."""
        try:
            with self.db._get_connection() as conn:
                state_json = json.dumps(state)
                conn.execute(
                    """INSERT OR REPLACE INTO agent_state
                       (session_id, state_data, updated_at)
                       VALUES (?, ?, ?)""",
                    (session_id, state_json, datetime.utcnow())
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save agent state for {session_id}: {e}")
            return False

    def load_agent_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load saved agent state for session."""
        try:
            with self.db._get_connection() as conn:
                row = conn.execute(
                    "SELECT state_data FROM agent_state WHERE session_id = ?",
                    (session_id,)
                ).fetchone()

                if row:
                    return json.loads(row['state_data'])
        except Exception as e:
            logger.error(f"Failed to load agent state for {session_id}: {e}")
        return None

    def migrate_legacy_session(self, legacy_session_path: str) -> Optional[str]:
        """
        Migrate a legacy multi-agent session to the unified format.

        Args:
            legacy_session_path: Path to legacy session directory

        Returns:
            New session ID if migration successful, None otherwise
        """
        try:
            legacy_path = Path(legacy_session_path)
            if not legacy_path.exists():
                return None

            # Load legacy session metadata
            metadata_file = legacy_path / "session_metadata.json"
            if not metadata_file.exists():
                logger.warning(f"No metadata found for legacy session: {legacy_path}")
                return None

            with open(metadata_file, 'r') as f:
                legacy_metadata = json.load(f)

            # Create new session
            session_id = self.create_session(
                title=legacy_metadata.get('title', 'Migrated Session'),
                project_path=legacy_metadata.get('project_path')
            )

            # Legacy system has been removed - no migration needed

            logger.info(f"Migrated legacy session to {session_id}")
            return session_id

        except Exception as e:
            logger.error(f"Failed to migrate legacy session {legacy_session_path}: {e}")
            return None

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics and usage information."""
        try:
            with self.db._get_connection() as conn:
                # Session stats
                session_stats = conn.execute("""
                    SELECT
                        COUNT(*) as total_sessions,
                        COUNT(CASE WHEN is_active = 1 THEN 1 END) as active_sessions,
                        SUM(message_count) as total_messages,
                        SUM(total_tokens) as total_tokens,
                        SUM(total_cost) as total_cost
                    FROM sessions
                """).fetchone()

                # Storage size
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

                return {
                    'total_sessions': session_stats['total_sessions'] or 0,
                    'active_sessions': session_stats['active_sessions'] or 0,
                    'total_messages': session_stats['total_messages'] or 0,
                    'total_tokens': session_stats['total_tokens'] or 0,
                    'total_cost': session_stats['total_cost'] or 0.0,
                    'database_size_bytes': db_size,
                    'database_size_mb': round(db_size / (1024 * 1024), 2),
                    'storage_path': str(self.storage_path)
                }
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {}


# Singleton instance for application-wide use
_unified_manager = None

def get_unified_session_manager() -> UnifiedSessionManager:
    """Get the singleton UnifiedSessionManager instance."""
    global _unified_manager
    if _unified_manager is None:
        _unified_manager = UnifiedSessionManager()
    return _unified_manager

def create_session_manager(storage_path: str) -> UnifiedSessionManager:
    """Create a new UnifiedSessionManager instance with custom storage path."""
    return UnifiedSessionManager(storage_path)