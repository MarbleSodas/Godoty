"""
Shared rate limiter instance for Godoty API routes.

This module provides a centralized rate limiter that can be imported
across all route modules without circular dependencies.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Global rate limiter instance (configured in main.py)
limiter = None


def get_limiter() -> Limiter:
    """Get the global rate limiter instance."""
    global limiter
    if limiter is None:
        # Fallback if not yet configured
        limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
    return limiter


def set_limiter(limiter_instance: Limiter):
    """Set the global rate limiter instance."""
    global limiter
    limiter = limiter_instance
