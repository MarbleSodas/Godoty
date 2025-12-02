"""
Main Godoty agent implementation using Strands framework.

Integrates OpenRouter model provider with Godot-specific tools to provide
intelligent assistance for Godot 4.x development.
"""

import logging
from typing import Any, Dict, List, Optional, AsyncGenerator

from strands import Agent
from strands.session.file_session_manager import FileSessionManager
from strands.tools import PythonAgentTool
from strands.types.tools import ToolSpec

from app.models.openrouter_model import StrandsOpenRouterModel
from app.tools.godot_tools import GodotTools
from app.config import settings

logger = logging.getLogger(__name__)


class GodotyAgent:
    """
    Godoty AI assistant agent for Godot 4.x development.

    Provides intelligent code assistance, project analysis, and development guidance
    specifically tailored for Godot game development workflows.
    """

    def __init__(self, session_id: str, project_path: str, model_id: Optional[str] = None):
        """
        Initialize Godoty agent.

        Args:
            session_id: Unique session identifier
            project_path: Path to Godot project
            model_id: OpenRouter model to use (defaults to DEFAULT_GODOTY_MODEL)
        """
        self.session_id = session_id
        self.project_path = project_path
        self.model_id = model_id or settings.default_godoty_model

        # Initialize components
        self._init_model()
        self._init_session_manager()
        self._init_tools()
        self._init_strands_agent()

        logger.info(f"Initialized Godoty agent for session {session_id}")

    def _init_model(self) -> None:
        """Initialize the OpenRouter model provider."""
        try:
            self.model = StrandsOpenRouterModel(model_id=self.model_id)
            logger.info(f"Initialized OpenRouter model: {self.model_id}")
        except Exception as e:
            logger.error(f"Failed to initialize model: {e}")
            raise

    def _init_session_manager(self) -> None:
        """Initialize Strands FileSessionManager."""
        try:
            self.session_manager = FileSessionManager(session_id=self.session_id)
            logger.info(f"Initialized session manager for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to initialize session manager: {e}")
            raise

    def _init_tools(self) -> None:
        """Initialize Godot-specific tools."""
        try:
            self.godot_tools = GodotTools(project_path=self.project_path)
            self.tools = self._create_tool_definitions()
            logger.info(f"Initialized {len(self.tools)} Godot tools")
        except Exception as e:
            logger.error(f"Failed to initialize tools: {e}")
            raise

    def _create_tool_definitions(self) -> List[PythonAgentTool]:
        """Create Strands Tool definitions for Godot operations."""
        return [
            PythonAgentTool(
                tool_name="list_project_files",
                tool_spec=ToolSpec(
                    name="list_project_files",
                    description="List all files in the Godot project, categorized by type (scripts, scenes, resources, etc.)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "extensions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of file extensions to filter by"
                            }
                        }
                    }
                ),
                tool_func=self._tool_list_project_files
            ),
            PythonAgentTool(
                tool_name="read_script",
                tool_spec=ToolSpec(
                    name="read_script",
                    description="Read a Godot script file (.gd) and return its content with metadata",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Relative path to the script file within the project"
                            },
                            "max_lines": {
                                "type": "integer",
                                "default": 1000,
                                "description": "Maximum number of lines to read"
                            }
                        },
                        "required": ["file_path"]
                    }
                ),
                tool_func=self._tool_read_script
            ),
            PythonAgentTool(
                tool_name="get_scene_tree",
                tool_spec=ToolSpec(
                    name="get_scene_tree",
                    description="Analyze a .tscn scene file and return the node hierarchy and structure",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "scene_path": {
                                "type": "string",
                                "description": "Relative path to the scene file within the project"
                            }
                        },
                        "required": ["scene_path"]
                    }
                ),
                tool_func=self._tool_get_scene_tree
            ),
            PythonAgentTool(
                tool_name="search_godot_docs",
                tool_spec=ToolSpec(
                    name="search_godot_docs",
                    description="Search through project documentation and files for relevant information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query to find relevant information"
                            },
                            "max_results": {
                                "type": "integer",
                                "default": 10,
                                "description": "Maximum number of search results to return"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                tool_func=self._tool_search_godot_docs
            )
        ]

    def _init_strands_agent(self) -> None:
        """Initialize the Strands Agent with model, tools, and system prompt."""
        try:
            self.agent = Agent(
                model=self.model,
                session_manager=self.session_manager,
                tools=self.tools,
                system_prompt=self._get_system_prompt()
            )
            logger.info("Initialized Strands agent")
        except Exception as e:
            logger.error(f"Failed to initialize Strands agent: {e}")
            raise

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the Godoty agent."""
        return """You are Godoty, an expert AI assistant specialized in Godot 4.x game development.

Your capabilities include:
- Analyzing and improving GDScript code
- Understanding Godot scene structures and node hierarchies
- Providing best practices for Godot development
- Debugging common Godot issues
- Suggesting architectural improvements
- Explaining Godot concepts and features

Your approach:
1. Always consider the context of the user's project
2. Provide practical, actionable advice
3. Explain complex concepts clearly
3. Follow Godot best practices and conventions
4. Be thorough but concise
5. When analyzing code, focus on both correctness and performance
6. Suggest improvements that align with Godot's design philosophy

You have access to tools for:
- Reading project files and understanding project structure
- Analyzing GDScript code with metadata extraction
- Parsing scene files to understand node hierarchies
- Searching through project documentation

Use these tools to provide accurate, context-aware assistance for Godot development."""

    async def process_message(self, message: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a user message and return streaming response.

        Args:
            message: User message to process

        Yields:
            Stream events compatible with frontend SSE format
        """
        try:
            logger.info(f"Processing message for session {self.session_id}: {message[:100]}...")

            # Process message through Strands agent
            async for event in self.agent.process_message(message):
                # Convert Strands events to frontend format
                frontend_event = self._convert_stream_event(event)
                yield frontend_event

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            yield {
                "type": "error",
                "error": {
                    "type": "processing_error",
                    "message": str(e),
                    "recoverable": True
                }
            }

    def _convert_stream_event(self, strands_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Strands event format to frontend-compatible SSE format.

        Args:
            strands_event: Event from Strands agent

        Returns:
            Frontend-compatible event dictionary
        """
        event_type = strands_event.get("type", "unknown")

        # Map event types
        if event_type == "text":
            return {
                "type": "text",
                "content": strands_event.get("content", "")
            }
        elif event_type == "tool_use":
            return {
                "type": "tool_use",
                "tool": strands_event.get("tool", ""),
                "parameters": strands_event.get("parameters", {}),
                "id": strands_event.get("id", "")
            }
        elif event_type == "tool_result":
            return {
                "type": "tool_result",
                "tool": strands_event.get("tool", ""),
                "result": strands_event.get("result", {}),
                "id": strands_event.get("id", "")
            }
        elif event_type == "plan_created":
            return {
                "type": "plan_created",
                "plan": strands_event.get("plan", {})
            }
        elif event_type == "execution_started":
            return {
                "type": "execution_started",
                "step": strands_event.get("step", "")
            }
        elif event_type == "metadata":
            return {
                "type": "metadata",
                "data": strands_event.get("data", {})
            }
        elif event_type == "done":
            return {
                "type": "done",
                "final_message": strands_event.get("final_message", ""),
                "metrics": strands_event.get("metrics", {})
            }
        elif event_type == "error":
            return {
                "type": "error",
                "error": strands_event.get("error", {})
            }
        else:
            # Pass through unknown events
            return strands_event

    # Tool implementation methods
    async def _tool_list_project_files(self, extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        """Tool implementation for listing project files."""
        try:
            result = self.godot_tools.list_project_files(extensions)
            return {"files_by_type": result, "total_files": sum(len(files) for files in result.values())}
        except Exception as e:
            logger.error(f"Error in list_project_files tool: {e}")
            return {"error": str(e)}

    async def _tool_read_script(self, file_path: str, max_lines: int = 1000) -> Dict[str, Any]:
        """Tool implementation for reading script files."""
        try:
            result = self.godot_tools.read_script(file_path, max_lines)
            return result
        except Exception as e:
            logger.error(f"Error in read_script tool: {e}")
            return {"error": str(e)}

    async def _tool_get_scene_tree(self, scene_path: str) -> Dict[str, Any]:
        """Tool implementation for analyzing scene files."""
        try:
            result = self.godot_tools.get_scene_tree(scene_path)
            return result
        except Exception as e:
            logger.error(f"Error in get_scene_tree tool: {e}")
            return {"error": str(e)}

    async def _tool_search_godot_docs(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Tool implementation for searching documentation."""
        try:
            results = self.godot_tools.search_godot_docs(query, max_results)
            return {"query": query, "results": results, "result_count": len(results)}
        except Exception as e:
            logger.error(f"Error in search_godot_docs tool: {e}")
            return {"error": str(e)}

    def get_session_info(self) -> Dict[str, Any]:
        """Get information about the current session."""
        return {
            "session_id": self.session_id,
            "project_path": self.project_path,
            "model_id": self.model_id,
            "agent_initialized": hasattr(self, 'agent')
        }