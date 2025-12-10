import sqlite3
import os
import time
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class MetricsDB:
    """
    A raw, minimal SQLite database for tracking OpenRouter API calls and Session metrics.
    Designed for ease of debugging and strict data accounting.
    """

    def __init__(self, db_path: str = "godoty_stats.db"):
        """
        Initialize the database connection.
        
        Args:
            db_path: Path to the sqlite file. Defaults to 'godoty_stats.db' in current directory.
        """
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        """Initialize the simple schema."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # 1. Sessions Table: metadata about the chat session
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)

        # 2. API Calls Table: granular log of every LLM interaction
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                model TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost REAL,
                generation_id TEXT,
                timestamp REAL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        """)

        conn.commit()
        conn.close()

    # --- Write Operations ---

    def register_session(self, session_id: str, title: str = "New Session"):
        """Ensure a session exists in the DB."""
        conn = self._get_conn()
        cursor = conn.cursor()
        now = time.time()
        
        cursor.execute("""
            INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (session_id, title, now, now))
        
        conn.commit()
        conn.close()

    def log_api_call(self, 
                     session_id: str, 
                     model: str, 
                     prompt_tokens: int, 
                     completion_tokens: int, 
                     cost: float, 
                     generation_id: Optional[str] = None):
        """
        Log a single API call's usage.
        """
        # Ensure session exists first
        self.register_session(session_id)

        conn = self._get_conn()
        cursor = conn.cursor()
        now = time.time()
        total_tokens = prompt_tokens + completion_tokens

        cursor.execute("""
            INSERT INTO api_calls 
            (session_id, model, prompt_tokens, completion_tokens, total_tokens, cost, generation_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, model, prompt_tokens, completion_tokens, total_tokens, cost, generation_id, now))

        # Update session timestamp
        cursor.execute("""
            UPDATE sessions SET updated_at = ? WHERE session_id = ?
        """, (now, session_id))

        conn.commit()
        conn.close()
        logger.info(f"Logged API call for session {session_id}: ${cost:.6f}, {total_tokens} tokens")

    # --- Read Operations ---

    def get_session_metrics(self, session_id: str) -> Dict[str, Any]:
        """
        Calculate aggregated metrics for a specific session.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                SUM(total_tokens),
                SUM(cost),
                COUNT(*)
            FROM api_calls
            WHERE session_id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        conn.close()

        total_tokens = row[0] if row and row[0] else 0
        total_cost = row[1] if row and row[1] else 0.0
        call_count = row[2] if row and row[2] else 0

        return {
            "session_id": session_id,
            "total_tokens": total_tokens,
            "total_estimated_cost": total_cost,
            "call_count": call_count
        }

    def get_session_calls(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all individual API calls for a session.
        """
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM api_calls 
            WHERE session_id = ? 
            ORDER BY timestamp ASC
        """, (session_id,))
        
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """
        List all sessions with their live aggregated metrics.
        """
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get sessions
        cursor.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
        sessions_rows = cursor.fetchall()
        
        results = []
        for row in sessions_rows:
            s_id = row['session_id']
            
            # Get metrics for each
            cursor.execute("""
                SELECT SUM(total_tokens), SUM(cost) 
                FROM api_calls 
                WHERE session_id = ?
            """, (s_id,))
            metrics_row = cursor.fetchone()
            
            total_tokens = metrics_row[0] if metrics_row[0] else 0
            total_cost = metrics_row[1] if metrics_row[1] else 0.0

            results.append({
                "id": s_id,
                "title": row['title'],
                "created_at": row['created_at'],
                "last_updated": row['updated_at'],
                "metrics": {
                    "total_tokens": total_tokens,
                    "total_estimated_cost": total_cost
                }
            })

        conn.close()
        return results

    def update_session_title(self, session_id: str, title: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET title = ? WHERE session_id = ?", (title, session_id))
        conn.commit()
        conn.close()

    def delete_session(self, session_id: str):
        """Delete session and its history."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM api_calls WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

# Global instance accessor
_db_instance = None

def get_metrics_db() -> MetricsDB:
    global _db_instance
    if _db_instance is None:
        # Create in current working directory for visibility
        _db_instance = MetricsDB("godoty_stats.db")
    return _db_instance