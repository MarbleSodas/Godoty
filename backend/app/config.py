"""
Configuration management for Godoty backend application.

Handles environment variables, application settings, and OpenRouter integration.
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenRouter Configuration
    openrouter_api_key: str = Field(..., env="OPENROUTER_API_KEY")
    default_godoty_model: str = Field(default="x-ai/grok-4.1-fast:free", env="DEFAULT_GODOTY_MODEL")

    # Application Configuration
    app_name: str = Field(default="Godoty", env="APP_NAME")
    app_url: str = Field(default="http://localhost:8000", env="APP_URL")
    app_version: str = "1.0.0"

    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    debug: bool = Field(default=False, env="DEBUG")

    # Session Management
    sessions_dir: str = Field(default=".godot/godoty_sessions", env="SESSIONS_DIR")

    # OpenRouter API Settings
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout: int = Field(default=30, env="OPENROUTER_TIMEOUT")

    # Cost and Metrics Settings
    cost_warning_threshold: float = Field(default=1.0, env="COST_WARNING_THRESHOLD")
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")

    # File Security Settings
    max_file_size: int = Field(default=10 * 1024 * 1024, env="MAX_FILE_SIZE")  # 10MB
    allowed_file_extensions: list = Field(
        default=[".gd", ".cs", ".tscn", ".tres", ".md", ".txt"],
        env="ALLOWED_FILE_EXTENSIONS"
    )

    # Godot WebSocket Configuration
    godot_ws_host: str = Field(default="localhost", env="GODOT_WS_HOST")
    godot_ws_port: int = Field(default=9001, env="GODOT_WS_PORT")
    godot_ws_timeout: int = Field(default=10, env="GODOT_WS_TIMEOUT")
    godot_ws_reconnect_interval: int = Field(default=30, env="GODOT_WS_RECONNECT_INTERVAL")
    godot_ws_max_reconnect_attempts: int = Field(default=10, env="GODOT_WS_MAX_RECONNECT_ATTEMPTS")
    godot_ws_enable_auto_reconnect: bool = Field(default=True, env="GODOT_WS_ENABLE_AUTO_RECONNECT")

    # Desktop Mode Configuration
    desktop_mode: bool = Field(default=False, env="DESKTOP_MODE")
    window_title: str = Field(default="Godoty", env="WINDOW_TITLE")
    window_width: int = Field(default=1200, env="WINDOW_WIDTH")
    window_height: int = Field(default=800, env="WINDOW_HEIGHT")
    min_window_width: int = Field(default=800, env="MIN_WINDOW_WIDTH")
    min_window_height: int = Field(default=600, env="MIN_WINDOW_HEIGHT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def openrouter_headers(self) -> dict:
        """Get required OpenRouter API headers."""
        return {
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_name,
        }

    def get_project_sessions_dir(self, project_path: str) -> str:
        """Get sessions directory for a specific project."""
        return os.path.join(project_path, self.sessions_dir)


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def validate_environment() -> list[str]:
    """Validate that required environment variables are set."""
    missing_vars = []

    if not settings.openrouter_api_key:
        missing_vars.append("OPENROUTER_API_KEY")

    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        raise ValueError(error_msg)

    return missing_vars