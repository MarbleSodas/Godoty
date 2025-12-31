"""Godoty Agents package.

Unified single-agent architecture for the Godoty AI assistant.
Replaces the previous multi-agent team with a streamlined design.
"""

from app.agents.agent import (
    DB_DIR,
    DB_PATH,
    GodotySession,
    create_godoty_agent,
    get_db,
    get_jwt_token,
    get_key_spend_info,
    get_model_id,
    set_jwt_token,
    set_model_id,
)
from app.agents.schemas import (
    ArchitecturePlan,
    CodeFile,
    CodeProposal,
    ObservationReport,
    PlanTask,
    SceneNodeInfo,
)

__all__ = [
    # Agent
    "DB_DIR",
    "DB_PATH",
    "GodotySession",
    "create_godoty_agent",
    "get_db",
    "get_jwt_token",
    "get_key_spend_info",
    "get_model_id",
    "set_jwt_token",
    "set_model_id",
    # Schemas (kept for backwards compatibility)
    "ArchitecturePlan",
    "CodeFile",
    "CodeProposal",
    "ObservationReport",
    "PlanTask",
    "SceneNodeInfo",
]