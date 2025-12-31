"""In-memory caching for frequently accessed data.

Provides simple TTL-based caching with LRU eviction for storing
frequently accessed data like session lookups, project context, etc.
"""

import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheEntry:
    """A cached value with expiration."""

    value: Any
    expires_at: float

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return time.time() > self.expires_at


class SimpleCache:
    """Simple in-memory cache with LRU eviction and TTL support.

    This cache is designed for single-process use cases where distributed
    caching is not required. It provides fast in-memory lookups with
    automatic expiration and size-based eviction.

    Usage:
        cache = SimpleCache(max_size=1000, default_ttl=300)

        # Set a value
        cache.set("key", {"data": "value"}, ttl=60)

        # Get a value
        value = cache.get("key")  # Returns None if expired or not found

        # Invalidate a specific key
        cache.invalidate("key")

        # Clear all cache entries
        cache.clear()
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0) -> None:
        """Initialize the cache.

        Args:
            max_size: Maximum number of entries to store
            default_ttl: Default time-to-live in seconds for entries
        """
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Args:
            key: The cache key to look up

        Returns:
            The cached value, or None if not found or expired
        """
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired():
            # Remove expired entry
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key to store under
            value: The value to cache
            ttl: Time-to-live in seconds (uses default_ttl if not specified)
        """
        # Evict oldest entry if at capacity (simple FIFO)
        if len(self._cache) >= self._max_size and key not in self._cache:
            # Remove first (oldest) key
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        expires_at = time.time() + (ttl or self._default_ttl)
        self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    def invalidate(self, key: str) -> None:
        """Invalidate a specific cache entry.

        Args:
            key: The cache key to invalidate
        """
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def size(self) -> int:
        """Get the current number of cached entries."""
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats including size, hits, misses, and hit rate
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


# Global cache instances for different use cases
# Each cache is tuned for its specific use case

# Session cache - stores session metadata (1 min TTL, smaller size)
session_cache = SimpleCache(max_size=500, default_ttl=60.0)

# Project context cache - stores project file listings and structure (5 min TTL)
project_context_cache = SimpleCache(max_size=100, default_ttl=300.0)

# Documentation cache - stores frequently accessed docs (10 min TTL, larger size)
docs_cache = SimpleCache(max_size=2000, default_ttl=600.0)


def cached(ttl: float = 300.0, cache_instance: Optional[SimpleCache] = None):
    """Decorator for caching function results.

    Usage:
        @cached(ttl=60, cache_instance=session_cache)
        async def get_session(session_id: str) -> Session:
            # ... fetch from database ...
            return session

    Args:
        ttl: Time-to-live for cached results in seconds
        cache_instance: Which cache to use (defaults to session_cache)

    Returns:
        Decorator function
    """
    cache = cache_instance or session_cache

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key = f"{func.__name__}:{args}:{kwargs}"

            # Try cache first
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value

            # Cache miss - compute and store
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl=ttl)
            return result

        return wrapper
    return decorator
