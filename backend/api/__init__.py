"""API routes for Godot Assistant."""

import warnings

# Suppress LangGraph warning before importing any modules
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

# Import current API routes
from .config_routes import router as config_router
from .godoty_router import create_godoty_router
from .health_routes import router as health_router
from .sse_routes import router as sse_router

__all__ = ["config_router", "create_godoty_router", "health_router", "sse_router"]
