"""
MCP Tools Manager for Godot Assistant Agents

This module provides integration with Model Context Protocol (MCP) servers,
enabling both planning and executor agents to access external tools like
sequential-thinking and context7 documentation fetching.
"""

import logging
from typing import Optional, Dict, List, Any
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
                "prefix": "mcp__sequential_thinking__",
                "description": "Advanced step-by-step reasoning for complex problem solving"
            },
            "context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp"],
                "prefix": "mcp__context7__",
                "description": "Up-to-date documentation and code examples for libraries"
            },
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "prefix": "mcp__filesystem__",
                "description": "File system operations for temporary files and backups"
            },
            "git": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-git", "--repository", "."],
                "prefix": "mcp__git__",
                "description": "Git operations for version control and project management"
            }
        }

    async def enhance_executor_plan(
        self,
        plan_text: str,
        execution_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Enhance an executor plan using MCP tools for better execution strategy.

        Args:
            plan_text: Original plan text from planning agent
            execution_context: Current execution context

        Returns:
            Dict with enhanced plan information and suggestions
        """
        enhancements = {
            "original_plan": plan_text,
            "optimizations": [],
            "risk_mitigations": [],
            "alternative_strategies": [],
            "resource_suggestions": []
        }

        try:
            # Use sequential-thinking for execution strategy analysis
            if "sequential-thinking" in self._clients:
                try:
                    analysis_prompt = f"""
                    Analyze this execution plan for potential optimizations and risk mitigations:

                    Plan: {plan_text}

                    Context: {execution_context or {}}

                    Provide:
                    1. Execution order optimizations
                    2. Risk mitigation strategies
                    3. Alternative approaches for high-risk operations
                    4. Resource usage suggestions
                    """

                    result = await self.call_tool(
                        "sequential-thinking",
                        "think",
                        {"prompt": analysis_prompt}
                    )

                    if result and hasattr(result, 'content'):
                        # Parse the analysis result for structured insights
                        content = str(result.content)
                        enhancements["optimizations"] = self._extract_optimizations(content)
                        enhancements["risk_mitigations"] = self._extract_risk_mitigations(content)
                        enhancements["alternative_strategies"] = self._extract_alternatives(content)
                        enhancements["resource_suggestions"] = self._extract_resource_suggestions(content)

                except Exception as e:
                    logger.warning(f"Sequential thinking analysis failed: {e}")

            # Use context7 for Godot-specific best practices
            if "context7" in self._clients:
                try:
                    # Look for Godot-specific operations in the plan
                    godot_operations = self._extract_godot_operations(plan_text)

                    if godot_operations:
                        for operation in godot_operations:
                            try:
                                # Get best practices for each operation type
                                result = await self.call_tool(
                                    "context7",
                                    "get_library_docs",
                                    {
                                        "library_id": "/godot/godot",
                                        "topic": operation,
                                        "tokens": 2000
                                    }
                                )

                                if result and hasattr(result, 'content'):
                                    # Extract best practices and add to suggestions
                                    practices = self._extract_best_practices(str(result.content), operation)
                                    enhancements["optimizations"].extend(practices)

                            except Exception as e:
                                logger.warning(f"Context7 lookup for {operation} failed: {e}")

                except Exception as e:
                    logger.warning(f"Context7 analysis failed: {e}")

            return enhancements

        except Exception as e:
            logger.error(f"Plan enhancement failed: {e}")
            return enhancements

    def _extract_optimizations(self, content: str) -> List[str]:
        """Extract optimization suggestions from analysis content."""
        optimizations = []
        lines = content.split('\n')

        # Look for optimization-related content
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['optimization', 'optimize', 'better', 'improve']):
                if line.strip() and not line.startswith('#'):
                    optimizations.append(line.strip())

        return optimizations[:5]  # Limit to top 5

    def _extract_risk_mitigations(self, content: str) -> List[str]:
        """Extract risk mitigation strategies from analysis content."""
        mitigations = []
        lines = content.split('\n')

        # Look for risk-related content
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['risk', 'mitigation', 'backup', 'safety', 'caution']):
                if line.strip() and not line.startswith('#'):
                    mitigations.append(line.strip())

        return mitigations[:5]  # Limit to top 5

    def _extract_alternatives(self, content: str) -> List[str]:
        """Extract alternative strategies from analysis content."""
        alternatives = []
        lines = content.split('\n')

        # Look for alternative approach content
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['alternative', 'instead', 'option', 'approach']):
                if line.strip() and not line.startswith('#'):
                    alternatives.append(line.strip())

        return alternatives[:3]  # Limit to top 3

    def _extract_resource_suggestions(self, content: str) -> List[str]:
        """Extract resource usage suggestions from analysis content."""
        suggestions = []
        lines = content.split('\n')

        # Look for resource-related content
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['resource', 'memory', 'performance', 'efficient']):
                if line.strip() and not line.startswith('#'):
                    suggestions.append(line.strip())

        return suggestions[:5]  # Limit to top 5

    def _extract_godot_operations(self, plan_text: str) -> List[str]:
        """Extract Godot-specific operations from plan text."""
        operations = []

        # Common Godot operation patterns
        godot_patterns = [
            'create_node', 'delete_node', 'modify_node',
            'create_scene', 'gdscript', 'godot',
            'node2d', 'node3d', 'sprite', 'animation',
            'signal', 'resource', 'material'
        ]

        plan_lower = plan_text.lower()
        for pattern in godot_patterns:
            if pattern in plan_lower:
                operations.append(pattern)

        return list(set(operations))  # Remove duplicates

    def _extract_best_practices(self, content: str, operation: str) -> List[str]:
        """Extract best practices for a specific operation."""
        practices = []
        lines = content.split('\n')

        # Look for practice-related content
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['best practice', 'recommend', 'should', 'avoid']):
                if operation.lower() in line_lower and line.strip():
                    practices.append(line.strip())

        return practices[:3]  # Limit to top 3

    async def get_execution_context_insights(
        self,
        execution_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get insights about the current execution context using MCP tools.

        Args:
            execution_context: Current execution context

        Returns:
            Dict with context insights and recommendations
        """
        insights = {
            "context_analysis": {},
            "recommendations": [],
            "potential_issues": [],
            "optimization_opportunities": []
        }

        try:
            # Use sequential-thinking for context analysis
            if "sequential-thinking" in self._clients:
                try:
                    analysis_prompt = f"""
                    Analyze this execution context for potential issues and optimization opportunities:

                    Context: {execution_context}

                    Provide:
                    1. Context suitability analysis
                    2. Potential issues or conflicts
                    3. Optimization opportunities
                    4. Recommendations for improvement
                    """

                    result = await self.call_tool(
                        "sequential-thinking",
                        "think",
                        {"prompt": analysis_prompt}
                    )

                    if result and hasattr(result, 'content'):
                        content = str(result.content)
                        insights["context_analysis"] = {"analysis": content}
                        insights["recommendations"] = self._extract_recommendations(content)
                        insights["potential_issues"] = self._extract_issues(content)
                        insights["optimization_opportunities"] = self._extract_opportunities(content)

                except Exception as e:
                    logger.warning(f"Context analysis failed: {e}")

            return insights

        except Exception as e:
            logger.error(f"Context insights failed: {e}")
            return insights

    def _extract_recommendations(self, content: str) -> List[str]:
        """Extract recommendations from analysis content."""
        recommendations = []
        lines = content.split('\n')

        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['recommend', 'suggest', 'should', 'advise']):
                if line.strip() and not line.startswith('#'):
                    recommendations.append(line.strip())

        return recommendations[:5]

    def _extract_issues(self, content: str) -> List[str]:
        """Extract potential issues from analysis content."""
        issues = []
        lines = content.split('\n')

        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['issue', 'problem', 'conflict', 'warning']):
                if line.strip() and not line.startswith('#'):
                    issues.append(line.strip())

        return issues[:5]

    def _extract_opportunities(self, content: str) -> List[str]:
        """Extract optimization opportunities from analysis content."""
        opportunities = []
        lines = content.split('\n')

        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['opportunity', 'improve', 'optimize', 'better']):
                if line.strip() and not line.startswith('#'):
                    opportunities.append(line.strip())

        return opportunities[:5]

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
