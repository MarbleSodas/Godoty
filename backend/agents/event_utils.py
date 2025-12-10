"""
Backward compatibility shim for event_utils module.

This module redirects imports to the new Agno-based implementation.
The original Strands implementation has been renamed to event_utils_strands.py
and is kept for reference but should not be used.
"""

# Re-export everything from agno_event_utils for backward compatibility
from agents.agno_event_utils import (
    transform_agno_event,
    transform_agno_event as transform_strands_event,  # Backward compatibility alias
    sanitize_event_data,
)

__all__ = [
    "transform_agno_event",
    "transform_strands_event",
    "sanitize_event_data",
]
