"""
Tool configuration for agents.

Handles configuration for:
- Godot integration (hardcoded defaults)
- Tool enablement flags

MCP server integration is disabled - no external npx dependencies.
"""
from typing import Dict
from user_data import get_screenshots_dir


class ToolConfig:
    """Configuration for agent tools."""

    # Godot Integration Configuration
    ENABLE_GODOT_TOOLS = True
    GODOT_BRIDGE_HOST = "localhost"
    GODOT_BRIDGE_PORT = 9001
    GODOT_CONNECTION_TIMEOUT = 10.0
    GODOT_MAX_RETRIES = 3
    GODOT_RETRY_DELAY = 2.0
    GODOT_COMMAND_TIMEOUT = 30.0

    @classmethod
    def get_screenshot_dir(cls) -> str:
        """Get screenshot directory path in user data."""
        return str(get_screenshots_dir())

    @classmethod
    def get_mcp_servers_config(cls) -> Dict:
        """Get MCP servers configuration - returns empty (MCP disabled)."""
        return {}

    @classmethod
    def is_mcp_enabled(cls) -> bool:
        """Check if MCP tools are enabled - always False."""
        return False

    @classmethod
    def is_godot_enabled(cls) -> bool:
        """Check if Godot tools are enabled."""
        return cls.ENABLE_GODOT_TOOLS

    @classmethod
    def get_godot_config(cls) -> Dict:
        """Get Godot bridge configuration."""
        return {
            "host": cls.GODOT_BRIDGE_HOST,
            "port": cls.GODOT_BRIDGE_PORT,
            "timeout": cls.GODOT_CONNECTION_TIMEOUT,
            "max_retries": cls.GODOT_MAX_RETRIES,
            "retry_delay": cls.GODOT_RETRY_DELAY,
            "command_timeout": cls.GODOT_COMMAND_TIMEOUT,
            "screenshot_dir": cls.get_screenshot_dir()
        }
