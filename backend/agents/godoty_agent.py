"""
Backward compatibility shim for godoty_agent module.

This module redirects imports to the new Agno-based implementation.
The original Strands implementation has been renamed to godoty_agent_strands.py
and is kept for reference but should not be used.
"""

# Re-export everything from agno_agent for backward compatibility
from agents.agno_agent import (
    GodotyTeam,
    GodotyTeam as GodotyAgent,  # Backward compatibility alias
    get_godoty_agent,
    AgentMode,
    PlanState,
    MAX_AGENT_STEPS,
    MIN_BALANCE_FOR_STEP,
    BALANCE_CHECK_INTERVAL,
)

# For internal access to singleton
from agents.agno_agent import _godoty_team_instance, _team_lock

# Alias for backward compatibility
_godoty_agent_instance = _godoty_team_instance

__all__ = [
    "GodotyTeam",
    "GodotyAgent",
    "get_godoty_agent",
    "AgentMode",
    "PlanState",
    "_godoty_agent_instance",
    "_godoty_team_instance",
]
