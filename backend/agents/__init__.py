"""Agents module for Godot Assistant."""

import warnings

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from .planning_agent import PlanningAgent, get_planning_agent, close_planning_agent
from .config import AgentConfig

__all__ = [
    "PlanningAgent",
    "get_planning_agent",
    "close_planning_agent",
    "AgentConfig"
]
