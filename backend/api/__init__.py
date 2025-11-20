"""API routes for Godot Assistant."""

import warnings

# Suppress LangGraph warning before importing any modules
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from .agent_routes import router as agent_router

__all__ = ["agent_router"]
