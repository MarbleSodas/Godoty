import sqlite3
import os
import sys
import json
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional, Any

class ProjectDB:
    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.project_hash = self._get_project_hash(self.project_path)
        self.db_path = self._get_db_path()
        self._init_db()

    def _get_project_hash(self, project_path: str) -> str:
        return hashlib.sha256(project_path.encode('utf-8')).hexdigest()

    def _get_db_path(self) -> str:
        app_name = "Godoty"
        if sys.platform == "win32":
            base_path = os.environ.get("APPDATA")
            if not base_path:
                base_path = os.path.expanduser("~\AppData\Roaming")
        elif sys.platform == "darwin":
            base_path = os.path.expanduser("~/Library/Application Support")
        else:  # linux and others
            base_path = os.path.expanduser("~/.local/share")

        app_dir = os.path.join(base_path, app_name)
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, "app_data.db")

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Sessions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                project_hash TEXT,
                created_at REAL,
                chat_history JSON,
                last_updated REAL
            )
        """)

        # Metrics Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_hash TEXT,
                session_id TEXT,
                cost REAL,
                tokens INTEGER,
                timestamp REAL,
                model_name TEXT
            )
        """)
        
        conn.commit()
        conn.close()

    # --- Session Methods ---

    def save_session(self, session_id: str, chat_history: List[Dict[str, Any]]):
        conn = self._get_connection()
        cursor = conn.cursor()
        now = time.time()
        
        # Check if exists to preserve created_at if it's an update
        # For now, we use upsert. If we want to strictly preserve creation time:
        # We could check first. But 'created_at' implies when the session started.
        # Let's assume the caller handles session creation time or we set it on first insert.
        
        # Try insert, if conflict update
        # We need to know if it's new to set created_at properly?
        # Actually, the schema has created_at. 
        # If we just upsert, we might overwrite created_at if we pass it?
        # The query below sets created_at on INSERT.
        # On UPDATE, it only updates chat_history and last_updated.
        
        cursor.execute("""
            INSERT INTO sessions (session_id, project_hash, created_at, chat_history, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                chat_history = excluded.chat_history,
                last_updated = excluded.last_updated
        """, (session_id, self.project_hash, now, json.dumps(chat_history), now))
        
        conn.commit()
        conn.close()

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_id, created_at, last_updated, chat_history 
            FROM sessions 
            WHERE project_hash = ?
            ORDER BY last_updated DESC
        """, (self.project_hash,))
        
        rows = cursor.fetchall()
        sessions = []
        for row in rows:
            try:
                history = json.loads(row[3])
            except:
                history = []
                
            sessions.append({
                "id": row[0],
                "created_at": row[1],
                "last_updated": row[2],
                "chat_history": history
            })
            
        conn.close()
        return sessions

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_id, created_at, last_updated, chat_history 
            FROM sessions 
            WHERE session_id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            try:
                history = json.loads(row[3])
            except:
                history = []
            return {
                "id": row[0],
                "created_at": row[1],
                "last_updated": row[2],
                "chat_history": history
            }
        return None

    def delete_session(self, session_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

    # --- Metrics Methods ---

    def record_metric(self, session_id: str, cost: float, tokens: int, model_name: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        now = time.time()
        
        cursor.execute("""
            INSERT INTO metrics (project_hash, session_id, cost, tokens, timestamp, model_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (self.project_hash, session_id, cost, tokens, now, model_name))
        
        conn.commit()
        conn.close()

    def get_project_total_cost(self) -> float:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT SUM(cost) FROM metrics WHERE project_hash = ?
        """, (self.project_hash,))
        
        result = cursor.fetchone()[0]
        conn.close()
        return result if result else 0.0

    def get_project_metrics(self) -> Dict[str, Any]:
        # Aggregated metrics for the project
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                SUM(cost), 
                SUM(tokens), 
                COUNT(DISTINCT session_id)
            FROM metrics 
            WHERE project_hash = ?
        """, (self.project_hash,))
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            "total_cost": row[0] if row[0] else 0.0,
            "total_tokens": row[1] if row[1] else 0,
            "total_sessions": row[2] if row[2] else 0
        }

    def get_session_metrics(self, session_id: str) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT SUM(cost), SUM(tokens) FROM metrics WHERE session_id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            "session_cost": row[0] if row[0] else 0.0,
            "session_tokens": row[1] if row[1] else 0
        }

    def get_metrics_for_sessions(self, session_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get metrics for multiple sessions.
        
        Args:
            session_ids: List of session IDs
            
        Returns:
            Dictionary of session_id -> metrics
        """
        if not session_ids:
            return {}
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(session_ids))
        query = f"""
            SELECT session_id, SUM(cost), SUM(tokens) 
            FROM metrics 
            WHERE session_id IN ({placeholders})
            GROUP BY session_id
        """
        
        cursor.execute(query, session_ids)
        rows = cursor.fetchall()
        conn.close()
        
        result = {}
        for row in rows:
            result[row[0]] = {
                "session_cost": row[1] if row[1] else 0.0,
                "session_tokens": row[2] if row[2] else 0
            }
            
        return result
