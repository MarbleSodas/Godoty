"""Centralized configuration for the Godoty brain."""
from __future__ import annotations

import os


class Timeouts:
    GODOT_RPC_SECONDS = 30.0
    HITL_CONFIRMATION_SECONDS = 300.0
    LSP_REQUEST_SECONDS = 10.0
    HTTP_CLIENT_SECONDS = 30.0
    WS_SHUTDOWN_SECONDS = 5.0


class Limits:
    MAX_TOOL_CALLS = 10
    MAX_REASONING_STEPS = 7
    MIN_REASONING_STEPS = 2
    HISTORY_RUNS = 10


class URLs:
    DEFAULT_LITELLM_PROXY = os.getenv(
        "GODOTY_LITELLM_BASE_URL",
        "https://litellm-production-150c.up.railway.app"
    )
    GODOT_DOCS_BASE = "https://raw.githubusercontent.com/godotengine/godot-docs/refs/heads/{branch}/classes"


ALLOWED_WS_ORIGINS = {
    "tauri://localhost",
    "http://localhost:1420",
    "http://localhost:5173",
    "http://127.0.0.1:1420",
    "http://127.0.0.1:5173",
}
