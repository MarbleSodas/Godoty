"""
Planning Agent Implementation

This module provides the main planning agent that uses OpenRouter and Strands
to generate execution plans for other agents.
"""

import logging
from typing import Optional, AsyncIterable, Dict, Any
from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager

from .models import OpenRouterModel
from .config import AgentConfig
from .tools import (
    # File system tools
    read_file,
    list_files,
    search_codebase,
    # Web tools
    search_documentation,
    fetch_webpage,
    get_godot_api_reference,
    # Godot bridge
    GodotBridge,
    get_godot_bridge,
    ensure_godot_connection,
    # Godot debug tools
    GodotDebugTools,
    get_project_overview,
    analyze_scene_tree,
    # Godot executor tools
    create_node,
    modify_node_property,
    delete_node,
    create_scene,
    open_scene,
    select_nodes,
    play_scene,
    stop_playing,
    # Godot security
    validate_operation,
    validate_path
)
from .tools.mcp_tools import MCPToolManager

logger = logging.getLogger(__name__)


class PlanningAgent:
    """
    Planning agent that creates execution plans for other agents.

    This agent uses OpenRouter models via Strands Agents framework to:
    - Analyze user requests
    - Break down complex tasks into steps
    - Identify dependencies and resources
    - Provide actionable execution plans
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
        enable_mcp: Optional[bool] = None,
        **kwargs
    ):
        """
        Initialize the planning agent.

        Args:
            api_key: OpenRouter API key (defaults to config)
            model_id: Model ID to use (defaults to config)
            enable_mcp: Enable MCP tools (defaults to config)
            **kwargs: Additional configuration options
        """
        # Get configuration
        config = AgentConfig.get_openrouter_config()
        model_config = AgentConfig.get_model_config()

        # Override with provided values
        api_key_value = api_key if api_key else config["api_key"]
        if model_id:
            model_config["model_id"] = model_id
        else:
            model_config["model_id"] = config["model_id"]

        # Add app name and URL to model config
        model_config["app_name"] = config.get("app_name", "Godot-Assistant")
        model_config["app_url"] = config.get("app_url", "http://localhost:8000")

        # Merge additional config
        model_config.update(kwargs)

        # Initialize OpenRouter model with new signature
        try:
            self.model = OpenRouterModel(api_key_value, **model_config)
            logger.info(f"Initialized OpenRouter model: {model_config.get('model_id')}")
        except Exception as e:
            logger.error(f"Failed to initialize model: {e}")
            # Try fallback model
            if model_config.get('model_id') != AgentConfig.FALLBACK_MODEL:
                logger.info(f"Attempting fallback model: {AgentConfig.FALLBACK_MODEL}")
                model_config['model_id'] = AgentConfig.FALLBACK_MODEL
                self.model = OpenRouterModel(api_key_value, **model_config)
            else:
                raise

        # Define base tools for the agent - streamlined for essential functionality
        self.tools = [
            # File system tools
            read_file,
            list_files,
            search_codebase,
            # Web tools
            search_documentation,
            fetch_webpage,
            get_godot_api_reference,
            # Godot connection tools
            ensure_godot_connection,
            # Essential Godot debug tools
            get_project_overview,
            analyze_scene_tree,
            # Godot executor tools - core functionality
            create_node,
            modify_node_property,
            delete_node,
            create_scene,
            open_scene,
            select_nodes,
            play_scene,
            stop_playing,
            # Essential security tools
            validate_operation,
            validate_path
        ]

        # Track MCP manager for cleanup
        self.mcp_manager: Optional[MCPToolManager] = None

        # Initialize conversation manager for context handling BEFORE MCP initialization
        self.conversation_manager = SlidingWindowConversationManager(
            window_size=20,  # Keep last 20 messages for context
            should_truncate_results=True
        )

        # Initialize MCP tools if enabled
        mcp_enabled = enable_mcp if enable_mcp is not None else AgentConfig.is_mcp_enabled()
        if mcp_enabled:
            self._initialize_mcp_tools_sync()

            # Try to initialize MCP tools synchronously if possible
            try:
                import asyncio
                # Check if we're already in an event loop
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an async context, we'll initialize lazily later
                    logger.info("In async context, MCP tools will be initialized lazily")
                except RuntimeError:
                    # We're not in an async context, try to initialize
                    logger.info("Initializing MCP tools synchronously...")
                    asyncio.run(self._ensure_mcp_initialized())
            except Exception as e:
                logger.warning(f"Failed to initialize MCP tools synchronously: {e}")
                if not AgentConfig.MCP_FAIL_SILENTLY:
                    logger.warning("MCP tools will be initialized lazily when needed")

        # Create Strands agent
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT,
            conversation_manager=self.conversation_manager
        )

        logger.info("Planning agent initialized successfully")

    def _initialize_mcp_tools_sync(self):
        """
        Initialize MCP tools synchronously during agent construction.

        This is a workaround since __init__ can't be async. MCP tools are
        initialized lazily on first use.
        """
        try:
            logger.info("MCP tools will be initialized on first agent invocation")
            self.mcp_manager = MCPToolManager.get_instance()
            # Note: Actual initialization happens in _ensure_mcp_initialized
        except Exception as e:
            error_msg = f"Failed to prepare MCP tool manager: {e}"
            if AgentConfig.MCP_FAIL_SILENTLY:
                logger.warning(error_msg)
                logger.warning("Continuing without MCP tools")
            else:
                logger.error(error_msg)
                raise

    async def _ensure_mcp_initialized(self):
        """
        Ensure MCP tools are initialized before use.

        This is called before agent invocations to lazily initialize MCP.
        """
        if self.mcp_manager:
            try:
                # Initialize if not connected
                if not self.mcp_manager.is_connected():
                    logger.info("Initializing MCP tools...")
                    servers_config = AgentConfig.get_mcp_servers_config()
                    success = await self.mcp_manager.initialize(
                        servers=servers_config,
                        fail_silently=AgentConfig.MCP_FAIL_SILENTLY
                    )
                else:
                    logger.info("MCP already connected, checking for tools...")
                    success = True

                if success:
                    # Always get MCP tools and add them if not already present
                    mcp_tools = self.mcp_manager.get_all_tools()
                    existing_tool_names = {getattr(tool, '__name__', str(tool)) for tool in self.tools}

                    # Add only new MCP tools
                    new_tools = []
                    for tool in mcp_tools:
                        tool_name = getattr(tool, '__name__', str(tool))
                        if tool_name not in existing_tool_names:
                            new_tools.append(tool)
                            existing_tool_names.add(tool_name)

                    if new_tools:
                        logger.info(f"Adding {len(new_tools)} new MCP tools to agent")
                        self.tools.extend(new_tools)

                        # Recreate agent with updated tools
                        self.agent = Agent(
                            model=self.model,
                            tools=self.tools,
                            system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT,
                            conversation_manager=self.conversation_manager
                        )

                        connected_servers = self.mcp_manager.get_connected_servers()
                        logger.info(f"MCP tools updated successfully: {', '.join(connected_servers)}")
                    else:
                        logger.info("All MCP tools already present in agent tools")
                else:
                    logger.warning("No MCP servers connected")

            except Exception as e:
                error_msg = f"Failed to initialize MCP tools: {e}"
                if AgentConfig.MCP_FAIL_SILENTLY:
                    logger.warning(error_msg)
                    logger.warning("Continuing without MCP tools")
                else:
                    logger.error(error_msg)
                    raise

    def plan(self, prompt: str) -> str:
        """
        Generate a plan synchronously.

        Args:
            prompt: User's request for planning

        Returns:
            Generated plan as a string
        """
        try:
            result = self.agent(prompt)

            # Extract text from result
            if hasattr(result, 'message'):
                content = result.message.get('content', [])
                if content and isinstance(content, list):
                    text_parts = [
                        block.get('text', '')
                        for block in content
                        if 'text' in block
                    ]
                    return '\n'.join(text_parts)

            return str(result)

        except Exception as e:
            logger.error(f"Error generating plan: {e}")
            raise

    async def plan_async(self, prompt: str) -> str:
        """
        Generate a plan asynchronously.

        Args:
            prompt: User's request for planning

        Returns:
            Generated plan as a string
        """
        try:
            # Ensure MCP tools are initialized
            await self._ensure_mcp_initialized()

            # Use direct OpenRouter model call to bypass Strands streaming entirely
            logger.info("Using direct OpenRouter model call to bypass toolUseId streaming error")

            # Create messages in Strands format
            messages = [{"role": "user", "content": [{"text": prompt}]}]

            # Get tool specifications from agent tools
            tool_specs = []
            for tool in self.tools:
                if hasattr(tool, 'tool_spec'):
                    tool_specs.append(tool.tool_spec)
                elif hasattr(tool, '__name__') and hasattr(tool, '__doc__'):
                    # Create basic tool spec for tools without explicit spec
                    tool_specs.append({
                        "name": tool.__name__,
                        "description": tool.__doc__ or f"Tool: {tool.__name__}",
                        "input_schema": {"type": "object", "properties": {}}
                    })

            # Use the OpenRouter model's complete method directly
            result = await self.model.complete(
                messages=messages,
                tool_specs=tool_specs,
                system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT
            )

            # Extract text from result
            if result and 'message' in result:
                content = result['message'].get('content', [])
                if content and isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and 'text' in block:
                            text_parts.append(block['text'])
                        elif isinstance(block, str):
                            text_parts.append(block)

                    if text_parts:
                        return '\n'.join(text_parts)

            return str(result) if result else "No plan generated"

        except Exception as e:
            logger.error(f"Error generating plan: {e}")
            raise

    async def plan_stream(self, prompt: str) -> AsyncIterable[Dict[str, Any]]:
        """
        Generate a plan with streaming responses.

        Args:
            prompt: User's request for planning

        Yields:
            Dictionary events containing:
            - type: Event type ('start', 'data', 'tool_use', 'tool_result', 'end')
            - data: Event data (text chunk, tool info, etc.)
        """
        try:
            # Yield start event
            yield {
                "type": "start",
                "data": {"message": "Starting plan generation..."}
            }

            # Ensure MCP tools are initialized
            await self._ensure_mcp_initialized()

            # Use direct OpenRouter model call to bypass Strands streaming entirely
            logger.info("Using direct OpenRouter model call for streaming to avoid toolUseId error")

            try:
                # Create messages in Strands format
                messages = [{"role": "user", "content": [{"text": prompt}]}]

                # Get tool specifications from agent tools
                tool_specs = []
                for tool in self.tools:
                    if hasattr(tool, 'tool_spec'):
                        tool_specs.append(tool.tool_spec)
                    elif hasattr(tool, '__name__') and hasattr(tool, '__doc__'):
                        # Create basic tool spec for tools without explicit spec
                        tool_specs.append({
                            "name": tool.__name__,
                            "description": tool.__doc__ or f"Tool: {tool.__name__}",
                            "input_schema": {"type": "object", "properties": {}}
                        })

                # Use the OpenRouter model's complete method directly
                result = await self.model.complete(
                    messages=messages,
                    tool_specs=tool_specs,
                    system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT
                )

                # Extract text from result
                if result and 'message' in result:
                    content = result['message'].get('content', [])
                    if content and isinstance(content, list):
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict) and 'text' in block:
                                text_parts.append(block['text'])
                            elif isinstance(block, str):
                                text_parts.append(block)

                        if text_parts:
                            full_text = '\n'.join(text_parts)

                            # Replace problematic Unicode characters for Windows compatibility
                            safe_text = full_text.replace('→', '->').replace('✓', '+').replace('✗', '-')

                            # Stream the result as chunks for real-time feel
                            chunk_size = 30  # Small chunks for streaming effect
                            for i in range(0, len(safe_text), chunk_size):
                                chunk = safe_text[i:i + chunk_size]
                                yield {
                                    "type": "data",
                                    "data": {"text": chunk}
                                }
                                # Small delay to simulate streaming
                                import asyncio
                                await asyncio.sleep(0.05)

                            # Yield end event
                            yield {
                                "type": "end",
                                "data": {"stop_reason": "end_turn"}
                            }

                            # Include metadata if available
                            if 'usage' in result:
                                yield {
                                    "type": "metadata",
                                    "data": result['usage']
                                }

                            return

                # If no content was extracted, yield a default message
                yield {
                    "type": "data",
                    "data": {"text": "Plan generated but content could not be extracted."}
                }

                yield {
                    "type": "end",
                    "data": {"stop_reason": "end_turn"}
                }

            except Exception as inner_error:
                logger.error(f"Error in direct OpenRouter call: {inner_error}")
                yield {
                    "type": "error",
                    "data": {"error": str(inner_error)}
                }

        except Exception as e:
            logger.error(f"Error in streaming plan: {e}")
            yield {
                "type": "error",
                "data": {"error": str(e)}
            }

    def reset_conversation(self):
        """Reset the conversation history by recreating the agent."""
        # Recreate the agent to reset conversation history
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=AgentConfig.PLANNING_AGENT_SYSTEM_PROMPT,
            conversation_manager=self.conversation_manager
        )
        logger.info("Conversation history reset")

    async def close(self):
        """Close the agent and cleanup resources."""
        # Cleanup MCP connections
        if self.mcp_manager:
            try:
                await self.mcp_manager.cleanup()
                logger.info("MCP tools cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up MCP tools: {e}")

        # Close model
        if hasattr(self.model, 'close'):
            await self.model.close()

        logger.info("Planning agent closed")


# Singleton instance
_planning_agent_instance: Optional[PlanningAgent] = None


def get_planning_agent() -> PlanningAgent:
    """
    Get or create the planning agent singleton instance.

    Returns:
        PlanningAgent instance
    """
    global _planning_agent_instance

    if _planning_agent_instance is None:
        _planning_agent_instance = PlanningAgent()

    return _planning_agent_instance


async def close_planning_agent():
    """Close the planning agent singleton instance."""
    global _planning_agent_instance

    if _planning_agent_instance is not None:
        await _planning_agent_instance.close()
        _planning_agent_instance = None
