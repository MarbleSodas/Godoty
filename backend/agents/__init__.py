"""Agents module for Godot Assistant."""

import warnings

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from .godoty_agent import GodotyAgent, get_godoty_agent
from .config import AgentConfig

__all__ = [
    "GodotyAgent",
    "get_godoty_agent",
    "AgentConfig"
]
