"""
Tool configuration for agents.

Handles configuration for:
- MCP (Model Context Protocol) servers
- Godot integration
- Tool enablement flags
"""
import os
from typing import Dict


class ToolConfig:
    """Configuration for agent tools."""
    
    # MCP Server Configuration
    ENABLE_MCP_TOOLS = os.getenv("ENABLE_MCP_TOOLS", "true").lower() == "true"
    MCP_FAIL_SILENTLY = os.getenv("MCP_FAIL_SILENTLY", "true").lower() == "true"
    
    # Sequential Thinking MCP Server
    ENABLE_SEQUENTIAL_THINKING = os.getenv("ENABLE_SEQUENTIAL_THINKING", "true").lower() == "true"
    SEQUENTIAL_THINKING_COMMAND = os.getenv("SEQUENTIAL_THINKING_COMMAND", "npx")
    SEQUENTIAL_THINKING_ARGS = os.getenv("SEQUENTIAL_THINKING_ARGS", "-y,@modelcontextprotocol/server-sequential-thinking").split(",")
    
    # Context7 MCP Server
    ENABLE_CONTEXT7 = os.getenv("ENABLE_CONTEXT7", "true").lower() == "true"
    CONTEXT7_COMMAND = os.getenv("CONTEXT7_COMMAND", "npx")
    CONTEXT7_ARGS = os.getenv("CONTEXT7_ARGS", "-y,@upstash/context7-mcp").split(",")
    
    # Godot Integration Configuration
    ENABLE_GODOT_TOOLS = os.getenv("ENABLE_GODOT_TOOLS", "true").lower() == "true"
    GODOT_BRIDGE_HOST = os.getenv("GODOT_BRIDGE_HOST", "localhost")
    GODOT_BRIDGE_PORT = int(os.getenv("GODOT_BRIDGE_PORT", "9001"))
    GODOT_CONNECTION_TIMEOUT = float(os.getenv("GODOT_CONNECTION_TIMEOUT", "10.0"))
    GODOT_MAX_RETRIES = int(os.getenv("GODOT_MAX_RETRIES", "3"))
    GODOT_RETRY_DELAY = float(os.getenv("GODOT_RETRY_DELAY", "2.0"))
    GODOT_COMMAND_TIMEOUT = float(os.getenv("GODOT_COMMAND_TIMEOUT", "30.0"))
    GODOT_SCREENSHOT_DIR = os.getenv("GODOT_SCREENSHOT_DIR", ".godoty/screenshots")
    
    @classmethod
    def get_mcp_servers_config(cls) -> Dict:
        """Get MCP servers configuration."""
        servers = {}
        
        if cls.ENABLE_MCP_TOOLS:
            if cls.ENABLE_SEQUENTIAL_THINKING:
                servers["sequential-thinking"] = {
                    "command": cls.SEQUENTIAL_THINKING_COMMAND,
                    "args": cls.SEQUENTIAL_THINKING_ARGS,
                    "prefix": "mcp__sequential_thinking__"
                }
            
            if cls.ENABLE_CONTEXT7:
                servers["context7"] = {
                    "command": cls.CONTEXT7_COMMAND,
                    "args": cls.CONTEXT7_ARGS,
                    "prefix": "mcp__context7__"
                }
        
        return servers
    
    @classmethod
    def is_mcp_enabled(cls) -> bool:
        """Check if MCP tools are enabled."""
        return cls.ENABLE_MCP_TOOLS and (
            cls.ENABLE_SEQUENTIAL_THINKING or cls.ENABLE_CONTEXT7
        )
    
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
            "screenshot_dir": cls.GODOT_SCREENSHOT_DIR
        }
