"""
MCP Tools Manager for Planning Agent

This module provides integration with Model Context Protocol (MCP) servers,
enabling the planning agent to access external tools like sequential-thinking
and context7 documentation fetching.
"""

import logging
from typing import Optional, Dict, List
from contextlib import asynccontextmanager

from strands.tools.mcp import MCPClient
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPToolManager:
    """
    Singleton manager for MCP client connections and tool access.

    This class handles the lifecycle of MCP server connections and provides
    a centralized way to access MCP tools for the planning agent.
    """

    _instance: Optional['MCPToolManager'] = None
    _initialized: bool = False

    def __init__(self):
        """Initialize the MCP tool manager."""
        if MCPToolManager._initialized:
            return

        self._clients: Dict[str, MCPClient] = {}
        self._tools: Dict[str, List] = {}
        self._connected: bool = False
        MCPToolManager._initialized = True

    @classmethod
    def get_instance(cls) -> 'MCPToolManager':
        """
        Get the singleton instance of MCPToolManager.

        Returns:
            MCPToolManager: The singleton instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(
        self,
        servers: Optional[Dict[str, dict]] = None,
        fail_silently: bool = True
    ) -> bool:
        """
        Initialize MCP clients for configured servers.

        Args:
            servers: Dictionary of server configurations. If None, uses default config.
                    Format: {
                        "server_name": {
                            "command": "npx",
                            "args": ["-y", "@package"],
                            "prefix": "mcp__server_name__"
                        }
                    }
            fail_silently: If True, log errors but continue if servers fail to connect

        Returns:
            bool: True if at least one server connected successfully
        """
        if self._connected:
            logger.warning("MCPToolManager already initialized")
            return True

        if servers is None:
            servers = self._get_default_servers()

        success_count = 0

        for server_name, config in servers.items():
            try:
                logger.info(f"Initializing MCP server: {server_name}")

                # Create transport function for stdio client
                def create_transport():
                    return stdio_client(
                        StdioServerParameters(
                            command=config["command"],
                            args=config["args"]
                        )
                    )

                # Create MCP client with transport
                client = MCPClient(create_transport)

                # Start the client (this establishes connection)
                client.start()

                # List available tools
                tools = client.list_tools_sync()

                if not tools:
                    logger.warning(f"No tools available from {server_name}")

                # Store client and tools
                self._clients[server_name] = client
                self._tools[server_name] = tools

                success_count += 1
                logger.info(
                    f"Successfully connected to {server_name} "
                    f"({len(tools)} tools available)"
                )

            except Exception as e:
                error_msg = f"Failed to initialize MCP server '{server_name}': {e}"

                if fail_silently:
                    logger.warning(error_msg)
                else:
                    logger.error(error_msg)
                    raise

        self._connected = success_count > 0

        if not self._connected:
            logger.warning("No MCP servers connected successfully")

        return self._connected

    def _get_default_servers(self) -> Dict[str, dict]:
        """
        Get default MCP server configurations.

        Returns:
            Dict[str, dict]: Default server configurations
        """
        return {
            "sequential-thinking": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
                "prefix": "mcp__sequential_thinking__"
            },
            "context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp"],
                "prefix": "mcp__context7__"
            }
        }

    def get_all_tools(self) -> List:
        """
        Get all tools from all connected MCP servers.

        Returns:
            List: Combined list of all MCP tools
        """
        all_tools = []
        for server_name, tools in self._tools.items():
            all_tools.extend(tools)
        return all_tools

    def get_tools_by_server(self, server_name: str) -> Optional[List]:
        """
        Get tools from a specific MCP server.

        Args:
            server_name: Name of the MCP server

        Returns:
            Optional[List]: List of tools, or None if server not found
        """
        return self._tools.get(server_name)

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict
    ) -> any:
        """
        Call a tool from a specific MCP server.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            ValueError: If server not connected or tool not found
        """
        if server_name not in self._clients:
            raise ValueError(f"MCP server '{server_name}' not connected")

        client = self._clients[server_name]

        try:
            result = await client.call_tool_async(tool_name, arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling tool '{tool_name}' on server '{server_name}': {e}")
            raise

    async def cleanup(self):
        """
        Clean up all MCP client connections.
        """
        logger.info("Cleaning up MCP connections")

        for server_name, client in self._clients.items():
            try:
                # MCPClient cleanup is automatic when the object is garbage collected
                # No explicit stop needed as it requires exception arguments
                logger.info(f"Disconnected from {server_name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {server_name}: {e}")

        self._clients.clear()
        self._tools.clear()
        self._connected = False
        MCPToolManager._initialized = False
        MCPToolManager._instance = None

    def is_connected(self) -> bool:
        """
        Check if at least one MCP server is connected.

        Returns:
            bool: True if connected to at least one server
        """
        return self._connected

    def get_connected_servers(self) -> List[str]:
        """
        Get list of connected MCP server names.

        Returns:
            List[str]: Names of connected servers
        """
        return list(self._clients.keys())


# Convenience function for agent integration
async def get_mcp_tools(
    servers: Optional[Dict[str, dict]] = None,
    fail_silently: bool = True
) -> List:
    """
    Convenience function to get MCP tools for agent initialization.

    Args:
        servers: Optional server configurations
        fail_silently: If True, continue even if servers fail to connect

    Returns:
        List: All available MCP tools
    """
    manager = MCPToolManager.get_instance()

    if not manager.is_connected():
        await manager.initialize(servers=servers, fail_silently=fail_silently)

    return manager.get_all_tools()
