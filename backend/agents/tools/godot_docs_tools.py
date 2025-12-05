"""
Simplified Godot Documentation Tools

Provides lightweight tools for searching and accessing Godot API documentation
using a local SQLite database with FTS5 full-text search.
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Any
from strands import tool
from user_data import get_docs_db_path

# Database configuration - uses user data directory (~/.godoty/)
DEFAULT_DB_PATH = get_docs_db_path()


class GodotDocumentationTools:
    """Singleton class for Godot documentation tools."""

    _instance = None
    _db_path: str = str(DEFAULT_DB_PATH)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def set_db_path(cls, db_path: str):
        """Set the database path."""
        cls._db_path = db_path

    @classmethod
    def get_db_path(cls) -> str:
        """Get the database path."""
        return cls._db_path

    @staticmethod
    def _get_connection() -> sqlite3.Connection:
        """Get a database connection."""
        db_path = GodotDocumentationTools.get_db_path()

        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"Documentation database not found at {db_path}. "
                "Please use the 'Rebuild Documentation' feature in settings to build it."
            )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like row access
        return conn

    @staticmethod
    def _get_metadata(conn: sqlite3.Connection) -> Dict[str, str]:
        """Get metadata from the database."""
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM docs_metadata")
        return {row['key']: row['value'] for row in cursor.fetchall()}


# Tool functions for Strands Agent

@tool
def search_godot_docs(
    query: str,
    limit: int = 20,
    content_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search the Godot Engine official documentation for classes, methods, properties, or signals.
    Uses full-text search to find relevant documentation entries.

    Args:
        query: Search query (e.g., "raycast", "look_at", "CharacterBody2D")
        limit: Maximum number of results to return (default: 20, max: 50)
        content_type: Filter by type - 'class', 'method', 'property', or 'signal' (optional)

    Returns:
        Dictionary with search results including class names, item names, types, and descriptions.

    Example:
        search_godot_docs("raycast") - Find all references to raycasting
        search_godot_docs("Node3D", content_type="method") - Find methods in Node3D
    """
    # Validate inputs
    limit = min(max(1, limit), 50)  # Clamp between 1 and 50
    valid_types = ['class', 'method', 'property', 'signal']

    if content_type and content_type not in valid_types:
        return {
            "success": False,
            "error": f"Invalid content_type '{content_type}'. Must be one of: {', '.join(valid_types)}"
        }

    try:
        conn = GodotDocumentationTools._get_connection()
        cursor = conn.cursor()

        # Build FTS5 query
        sql = """
            SELECT
                class_name,
                item_name,
                item_type,
                snippet(godot_docs, 3, '<b>', '</b>', '...', 32) as snippet,
                bm25(godot_docs) as score
            FROM godot_docs
            WHERE godot_docs MATCH ?
        """

        params = [query]

        # Add type filter if specified
        if content_type:
            sql += " AND item_type = ?"
            params.append(content_type)

        sql += " ORDER BY score LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        # Format results
        results = []
        for row in rows:
            results.append({
                "class_name": row['class_name'],
                "item_name": row['item_name'],
                "item_type": row['item_type'],
                "snippet": row['snippet'],
                "relevance_score": abs(row['score'])  # BM25 scores are negative
            })

        conn.close()

        if not results:
            return {
                "success": True,
                "query": query,
                "count": 0,
                "message": f"No documentation found for '{query}'",
                "results": []
            }

        # Format response
        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results
        }

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Search failed: {str(e)}"}


@tool
def get_class_reference(class_name: str) -> Dict[str, Any]:
    """
    Get complete API reference for a specific Godot class.
    Returns class information, inheritance, methods, properties, and signals.

    Args:
        class_name: Exact name of the Godot class (e.g., "Node3D", "CharacterBody2D")

    Returns:
        Dictionary with complete class reference including methods, properties, and signals.

    Example:
        get_class_reference("Node3D") - Get complete Node3D class documentation
        get_class_reference("CharacterBody2D") - Get CharacterBody2D documentation
    """
    try:
        conn = GodotDocumentationTools._get_connection()
        cursor = conn.cursor()

        # Get class info
        cursor.execute("""
            SELECT * FROM godot_docs
            WHERE class_name = ? AND item_type = 'class'
            LIMIT 1
        """, (class_name,))

        class_row = cursor.fetchone()

        if not class_row:
            conn.close()
            return {
                "success": False,
                "error": f"Class '{class_name}' not found in documentation. "
                        "Try using search_godot_docs() to find the correct class name."
            }

        # Get methods
        cursor.execute("""
            SELECT item_name, signature, return_type, brief_description
            FROM godot_docs
            WHERE class_name = ? AND item_type = 'method'
            ORDER BY item_name
            LIMIT 15
        """, (class_name,))
        methods = [dict(row) for row in cursor.fetchall()]

        # Get properties
        cursor.execute("""
            SELECT item_name, signature, return_type, brief_description
            FROM godot_docs
            WHERE class_name = ? AND item_type = 'property'
            ORDER BY item_name
            LIMIT 10
        """, (class_name,))
        properties = [dict(row) for row in cursor.fetchall()]

        # Get signals
        cursor.execute("""
            SELECT item_name, signature, brief_description
            FROM godot_docs
            WHERE class_name = ? AND item_type = 'signal'
            ORDER BY item_name
            LIMIT 5
        """, (class_name,))
        signals = [dict(row) for row in cursor.fetchall()]

        conn.close()

        # Format response
        response = {
            "success": True,
            "class_name": class_name,
            "inherits": class_row['inherits'] or "Object",
            "description": class_row['full_description'][:500] if class_row['full_description'] else class_row['brief_description'],
            "methods": methods,
            "properties": properties,
            "signals": signals,
            "method_count": len(methods),
            "property_count": len(properties),
            "signal_count": len(signals)
        }

        return response

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Failed to get class reference: {str(e)}"}


@tool
def get_documentation_status() -> Dict[str, Any]:
    """
    Get the current status of the Godot documentation database.
    Returns build information, statistics, and database health status.

    Returns:
        Dictionary with database status including version, build time, and statistics.

    Example:
        get_documentation_status() - Check if docs are available and up-to-date
    """
    db_path = GodotDocumentationTools.get_db_path()

    # Check if database exists
    if not os.path.exists(db_path):
        return {
            "success": True,
            "database_exists": False,
            "status": "not_built",
            "message": "Documentation database not found. Use the 'Rebuild Documentation' feature in settings to build it.",
            "db_path": db_path
        }

    try:
        # Get file size
        size_bytes = os.path.getsize(db_path)
        size_mb = round(size_bytes / (1024 * 1024), 2)

        # Connect and get metadata
        conn = GodotDocumentationTools._get_connection()
        metadata = GodotDocumentationTools._get_metadata(conn)

        # Get total counts from FTS table
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM godot_docs")
        total_entries = cursor.fetchone()['total']

        conn.close()

        # Build response
        return {
            "success": True,
            "database_exists": True,
            "status": "completed",
            "db_path": db_path,
            "size_mb": size_mb,
            "build_timestamp": metadata.get('build_timestamp', 'unknown'),
            "godot_version": metadata.get('godot_version', 'unknown'),
            "total_classes": int(metadata.get('total_classes', 0)),
            "total_methods": int(metadata.get('total_methods', 0)),
            "total_properties": int(metadata.get('total_properties', 0)),
            "total_signals": int(metadata.get('total_signals', 0)),
            "total_entries": total_entries,
            "message": "Documentation database is ready"
        }

    except Exception as e:
        return {
            "success": False,
            "database_exists": True,
            "status": "error",
            "error": f"Failed to read database: {str(e)}",
            "message": "Database exists but could not be read. It may be corrupted. Try rebuilding with --force."
        }


# Singleton instance
def get_godot_docs_tools() -> GodotDocumentationTools:
    """Get the singleton instance of GodotDocumentationTools."""
    return GodotDocumentationTools()
