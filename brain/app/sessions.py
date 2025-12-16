"""Session management for Godoty.

Provides CRUD operations for chat sessions stored in SQLite.
This module manages session metadata separately from Agno's internal session storage,
allowing the frontend to list, switch, and manage chat sessions.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Import the shared database path from team module
from app.agents.team import DB_DIR, DB_PATH


@dataclass
class Session:
    """Represents a chat session."""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0


class SessionManager:
    """Manages chat sessions in SQLite.
    
    This class handles session metadata (title, timestamps, message counts, metrics)
    while Agno's SqliteDb handles the actual conversation storage.
    """
    
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection with row factory for dict-like access."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self) -> None:
        """Initialize the sessions metadata table."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS godoty_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New Chat',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    total_cost REAL DEFAULT 0.0
                )
            """)
            # Add columns if they don't exist (migration for existing databases)
            try:
                conn.execute("ALTER TABLE godoty_sessions ADD COLUMN total_tokens INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute("ALTER TABLE godoty_sessions ADD COLUMN total_cost REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()
        finally:
            conn.close()
    
    def list_sessions(self) -> list[Session]:
        """List all sessions, most recent first."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT id, title, created_at, updated_at, message_count, total_tokens, total_cost
                FROM godoty_sessions
                ORDER BY updated_at DESC
            """)
            rows = cursor.fetchall()
            return [
                Session(
                    id=row["id"],
                    title=row["title"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    message_count=row["message_count"],
                    total_tokens=row["total_tokens"] or 0,
                    total_cost=row["total_cost"] or 0.0,
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT id, title, created_at, updated_at, message_count, total_tokens, total_cost FROM godoty_sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                return Session(
                    id=row["id"],
                    title=row["title"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    message_count=row["message_count"],
                    total_tokens=row["total_tokens"] or 0,
                    total_cost=row["total_cost"] or 0.0,
                )
            return None
        finally:
            conn.close()
    
    def create_session(self, title: str = "New Chat", session_id: str | None = None) -> Session:
        """Create a new session.
        
        Args:
            title: The session title (default: "New Chat")
            session_id: Optional specific session ID to use
            
        Returns:
            The newly created Session
        """
        conn = self._get_conn()
        try:
            new_id = session_id or str(uuid.uuid4())
            now = datetime.now().isoformat()
            conn.execute(
                """
                INSERT INTO godoty_sessions (id, title, created_at, updated_at, message_count)
                VALUES (?, ?, ?, ?, 0)
                """,
                (new_id, title, now, now)
            )
            conn.commit()
            return Session(
                id=new_id,
                title=title,
                created_at=datetime.fromisoformat(now),
                updated_at=datetime.fromisoformat(now),
                message_count=0,
            )
        finally:
            conn.close()
    
    def update_session(
        self,
        session_id: str,
        title: str | None = None,
        increment_messages: bool = False,
        add_tokens: int = 0,
        add_cost: float = 0.0,
    ) -> Optional[Session]:
        """Update session metadata.
        
        Args:
            session_id: ID of session to update
            title: New title (if provided)
            increment_messages: If True, increment message count by 1
            add_tokens: Number of tokens to add to session total
            add_cost: Cost to add to session total
            
        Returns:
            Updated Session or None if not found
        """
        conn = self._get_conn()
        try:
            now = datetime.now().isoformat()
            
            updates = ["updated_at = ?"]
            params: list = [now]
            
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            
            if increment_messages:
                updates.append("message_count = message_count + 1")
            
            if add_tokens > 0:
                updates.append("total_tokens = total_tokens + ?")
                params.append(add_tokens)
            
            if add_cost > 0:
                updates.append("total_cost = total_cost + ?")
                params.append(add_cost)
            
            params.append(session_id)
            
            conn.execute(
                f"UPDATE godoty_sessions SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()
            
            return self.get_session(session_id)
        finally:
            conn.close()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its associated data.
        
        Args:
            session_id: ID of session to delete
            
        Returns:
            True if session was deleted, False if not found
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM godoty_sessions WHERE id = ?",
                (session_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def ensure_default_session(self) -> Session:
        """Ensure at least one session exists, creating if needed.
        
        Returns:
            The default session (first one, or newly created)
        """
        sessions = self.list_sessions()
        if sessions:
            return sessions[0]
        return self.create_session()
    
    def generate_title_from_message(self, message: str, max_length: int = 30) -> str:
        """Generate a session title from the first user message.
        
        Args:
            message: The user's first message
            max_length: Maximum title length (default: 30 chars for quick identification)
            
        Returns:
            A truncated version of the message suitable as a title
        """
        # Clean up the message
        title = message.strip().replace("\n", " ")
        
        # Truncate if too long
        if len(title) > max_length:
            title = title[:max_length - 3] + "..."
        
        return title if title else "New Chat"


# Global session manager instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get the global SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
