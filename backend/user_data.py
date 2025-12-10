"""
Centralized user data path management for Godoty.

All user data is stored in ~/.godoty/ including:
- config.json (API keys, settings)
- .godot_docs.db (documentation database)
- .godot_docs_rebuild.db (temp rebuild file)
- .godot_rebuild_status.json (rebuild status)
- screenshots/ (captured screenshots)

This module provides PyInstaller-compatible paths that work in both
development and frozen (bundled) environments.
"""
import os
import sys
from pathlib import Path


def get_user_data_dir() -> Path:
    """Get the user data directory (~/.godoty/)."""
    return Path.home() / '.godoty'


def ensure_user_data_dir() -> Path:
    """Ensure user data directory exists and return path."""
    data_dir = get_user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_docs_db_path() -> Path:
    """Get path for Godot documentation database."""
    return ensure_user_data_dir() / '.godot_docs.db'


def get_docs_rebuild_db_path() -> Path:
    """Get path for temporary rebuild database."""
    return ensure_user_data_dir() / '.godot_docs_rebuild.db'


def get_rebuild_status_path() -> Path:
    """Get path for rebuild status file."""
    return ensure_user_data_dir() / '.godot_rebuild_status.json'


def get_screenshots_dir() -> Path:
    """Get path for screenshots directory."""
    screenshots_dir = ensure_user_data_dir() / 'screenshots'
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    return screenshots_dir


def get_config_path() -> Path:
    """Get path for config.json."""
    return ensure_user_data_dir() / 'config.json'


def is_frozen() -> bool:
    """Check if running in PyInstaller bundle."""
    return getattr(sys, 'frozen', False)


def get_bundle_resource_path(relative_path: str) -> Path:
    """
    Get path to bundled resource (for Angular dist, etc.).

    In frozen (PyInstaller) mode, returns path relative to _MEIPASS.
    In development mode, returns path relative to this file's directory.
    """
    if is_frozen():
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent
    return base_path / relative_path
