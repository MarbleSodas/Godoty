"""Agents module for Godot Assistant."""

import warnings

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

# Import from new Agno-based implementation
from .agno_agent import GodotyTeam, get_godoty_agent

# Backward compatibility alias
GodotyAgent = GodotyTeam

from .config import AgentConfig

__all__ = [
    "GodotyTeam",
    "GodotyAgent",  # Backward compatibility
    "get_godoty_agent",
    "AgentConfig"
]
