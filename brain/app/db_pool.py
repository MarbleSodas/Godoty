"""Database connection pool for SQLite.

Provides connection pooling and reuse for SQLite connections to reduce
the overhead of creating new connections for each query.

SQLite doesn't benefit as much from connection pooling as client-server
databases, but pooling still provides benefits:
1. Reduced memory allocation overhead
2. Better cache locality for prepared statements
3. Cleaner connection lifecycle management
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

# Connection pool settings
_DEFAULT_POOL_SIZE = 3
_CONNECTION_TIMEOUT = 30.0


class ConnectionPool:
    """Thread-safe SQLite connection pool.

    Uses a thread-local storage pattern to provide each thread with its
    own cached connection, avoiding contention in multi-threaded scenarios.
    """

    def __init__(self, db_path: Path, pool_size: int = _DEFAULT_POOL_SIZE) -> None:
        """Initialize the connection pool.

        Args:
            db_path: Path to the SQLite database file
            pool_size: Maximum number of connections to cache per thread
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self._local = threading.local()
        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool or create a new one.

        Returns:
            A cached or new SQLite connection with row factory set.
        """
        # Get thread-local cache
        if not hasattr(self._local, "conn"):
            self._local.conn = None

        conn = self._local.conn
        if conn is not None:
            # Verify connection is still alive
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                # Connection is dead, create new one
                self._local.conn = None

        # Create new connection
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        # Optimize for the workload
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-10000")  # 10MB cache
        self._local.conn = conn
        return conn

    def close(self) -> None:
        """Close the connection for the current thread."""
        if hasattr(self._local, "conn"):
            conn = self._local.conn
            if conn is not None:
                conn.close()
            self._local.conn = None

    def close_all(self) -> None:
        """Close all connections across all threads.

        Note: This only closes connections for the current thread due to
        thread-local storage limitations. Other threads will clean up
        their connections when they exit or call close().
        """
        self.close()


class PooledConnection:
    """Context manager for pooled connections.

    Usage:
        with pool.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM table")
            # Connection is automatically returned to pool on exit
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        self._conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> sqlite3.Connection:
        self._conn = self._pool.get_connection()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Don't close the connection, just release reference
        # The connection remains cached in the pool
        self._conn = None


# Global pool instances
_pools: dict[str, ConnectionPool] = {}
_pools_lock = threading.Lock()


def get_pool(db_path: Path, pool_size: int = _DEFAULT_POOL_SIZE) -> ConnectionPool:
    """Get or create a connection pool for the given database path.

    Args:
        db_path: Path to the SQLite database
        pool_size: Maximum connections per thread

    Returns:
        A ConnectionPool instance
    """
    db_key = str(db_path.resolve())
    with _pools_lock:
        if db_key not in _pools:
            _pools[db_key] = ConnectionPool(db_path, pool_size)
        return _pools[db_key]


def close_pool(db_path: Path) -> None:
    """Close the connection pool for a specific database.

    Args:
        db_path: Path to the SQLite database
    """
    db_key = str(db_path.resolve())
    with _pools_lock:
        pool = _pools.pop(db_key, None)
        if pool:
            pool.close_all()


def close_all_pools() -> None:
    """Close all connection pools."""
    with _pools_lock:
        for pool in _pools.values():
            pool.close_all()
        _pools.clear()
