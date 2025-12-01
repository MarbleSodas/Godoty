"""
GodotyAgent - Unified AI Agent for Godot Development

This module provides a single, intelligent agent that combines planning and execution
capabilities with enhanced RAG for superior codebase understanding and direct code modification.
"""

import os
import uuid
import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, AsyncIterable, Union
from pathlib import Path
from datetime import datetime

from strands import Agent
from core.model import GodotyOpenRouterModel
# from strands.agents import base_agent  # Not needed - using Agent directly
from strands.tools import tool
# from strands.types import AgentResponse  # Define locally if needed
from pydantic import BaseModel

from context import EnhancedContextEngine, create_context_engine
from agents.config.model_config import ModelConfig
from agents.unified_session import (
    UnifiedSessionManager, MessageEntry, SessionInfo, get_unified_session_manager
)
from agents.tools.godot_bridge import get_godot_bridge

logger = logging.getLogger(__name__)


class GodotyRequest(BaseModel):
    """Request model for Godoty agent."""
    message: str
    session_id: str
    project_path: Optional[str] = None
    context_limit: int = 10
    include_dependencies: bool = True
    mode: str = "auto"  # auto, modify, analyze, debug


class GodotyResponse(BaseModel):
    """Response model for Godoty agent."""
    session_id: str
    message_id: str
    response: str
    type: str  # "text", "tool_use", "code_change", "analysis"
    metadata: Dict[str, Any]
    confidence: float
    sources: List[Dict[str, Any]]


class GodotyAgent(Agent):
    """
    Unified Godoty Agent with enhanced RAG capabilities.

    Features:
    - Direct execution without planning phase overhead
    - Semantic codebase understanding using vector embeddings
    - Multi-language code support (GDScript, C#, TypeScript)
    - Integrated tool execution for Godot projects
    - Streaming responses with real-time updates
    - Context-aware suggestions and modifications
    """

    def __init__(self, config: Optional[ModelConfig] = None, project_path: Optional[str] = None):
        """
        Initialize the Godoty Agent.

        Args:
            config: Model configuration
            project_path: Root path of the Godot project
        """
        self.config = config or ModelConfig.get_model_config()
        self.project_path = project_path or os.getcwd()

        # Initialize enhanced context engine
        logger.info("Initializing Enhanced Context Engine...")
        self.context_engine = create_context_engine(self.project_path)

        # Initialize model
        planning_model = self.config.get('planning_model', 'x-ai/grok-4.1-fast:free')
        logger.info(f"Initializing model: {planning_model}")
        self.model = GodotyOpenRouterModel(
            model_id=planning_model,
            api_key=os.getenv('OPENROUTER_API_KEY'),
            temperature=self.config.get('temperature', 0.7),
            max_tokens=self.config.get('max_tokens', 4000),
            site_url="https://godoty.ai",
            app_name="Godoty Assistant"
        )

        # Initialize unified session manager
        logger.info("Initializing Unified Session Manager...")
        self.session_manager = get_unified_session_manager()

        # Initialize session state
        self.session_context: Dict[str, Dict[str, Any]] = {}

        # Tool registry
        self.tools: Dict[str, Any] = {}
        self._register_tools()

        # Initialize Godot bridge for real Godot integration
        logger.info("Initializing Godot bridge connection...")
        self._init_godot_bridge()

        # Response templates
        self._init_templates()

        logger.info("GodotyAgent initialized successfully")

    def _register_tools(self) -> None:
        """Register available tools for the agent."""
        # File system tools
        self.tools.update({
            "read_file": self._create_read_file_tool(),
            "write_file": self._create_write_file_tool(),
            "list_files": self._create_list_files_tool(),
            "search_code": self._create_search_code_tool(),
            "analyze_code": self._create_analyze_code_tool(),
            "modify_code": self._create_modify_code_tool(),
        })

        # Godot-specific tools
        self.tools.update({
            "get_project_info": self._create_project_info_tool(),
            "get_scene_info": self._create_scene_info_tool(),
            "run_godot_command": self._create_run_godot_tool(),
            "debug_scene": self._create_debug_scene_tool(),
        })

        # Web and documentation tools
        self.tools.update({
            "search_documentation": self._create_search_docs_tool(),
            "get_godot_version_info": self._create_version_info_tool(),
        })

    def _init_godot_bridge(self) -> None:
        """Initialize the Godot bridge for real Godot integration."""
        try:
            self.godot_bridge = get_godot_bridge()

            # Register connection callbacks with the connection monitor
            try:
                from services.godot_connection_monitor import get_connection_monitor, ConnectionEvent, ConnectionState
                monitor = get_connection_monitor()
                monitor.add_state_change_listener(self._on_godot_connection_state_change)
                logger.info("✅ Registered Godot connection state callbacks")

                # Store current connection state
                self._connection_state = ConnectionState.DISCONNECTED
                self._project_info = None

            except ImportError:
                logger.warning("⚠️  Connection monitor not available, using on-demand connections")
            except Exception as e:
                logger.warning(f"⚠️  Failed to register connection callbacks: {e}")

            logger.info("Godot bridge initialized, will connect on-demand")
        except Exception as e:
            logger.warning(f"Failed to initialize Godot bridge: {e}")
            self.godot_bridge = None

    async def _on_godot_connection_state_change(self, event: 'ConnectionEvent') -> None:
        """
        Handle Godot connection state changes from the connection monitor.

        Args:
            event: ConnectionEvent with state change information
        """
        try:
            # Update internal state
            self._connection_state = event.state

            # Handle different connection states
            if event.state.name == 'CONNECTED':
                logger.info("🔌 GodotyAgent: Godot connected - project integration available")

                # Update project path if available from connection
                if event.project_path and event.project_path != self.project_path:
                    logger.info(f"📁 Updating project path from Godot: {event.project_path}")
                    self.project_path = event.project_path

                    # Reinitialize context engine with new project path
                    try:
                        self.context_engine = create_context_engine(self.project_path)
                        logger.info("🔄 Context engine updated with new project path")
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to update context engine: {e}")

                # Store project info for tools to use
                self._project_info = {
                    'project_path': event.project_path,
                    'godot_version': event.godot_version,
                    'plugin_version': event.plugin_version,
                    'connected_at': event.timestamp.isoformat()
                }

            elif event.state.name == 'DISCONNECTED':
                logger.info("🔌 GodotyAgent: Godot disconnected - using local mode")
                self._project_info = None

            elif event.state.name == 'CONNECTING':
                logger.debug("🔌 GodotyAgent: Connecting to Godot...")

            elif event.state.name == 'ERROR':
                logger.warning(f"🔌 GodotyAgent: Godot connection error: {event.error}")
                self._project_info = None

        except Exception as e:
            logger.error(f"GodotyAgent: Error handling connection state change: {e}")

    def get_godot_connection_status(self) -> Dict[str, Any]:
        """
        Get current Godot connection status for tools and API responses.

        Returns:
            Dictionary with connection status and project info
        """
        status = {
            'connected': hasattr(self, '_connection_state') and self._connection_state.name == 'CONNECTED',
            'state': getattr(self, '_connection_state', 'UNKNOWN').name if hasattr(self, '_connection_state') else 'UNKNOWN',
            'project_info': getattr(self, '_project_info', None),
            'has_bridge': self.godot_bridge is not None
        }

        # Add bridge-specific status if available
        if self.godot_bridge:
            try:
                # Check if bridge has project info
                bridge_project_info = self.godot_bridge.project_info
                if bridge_project_info:
                    status['bridge_project_info'] = {
                        'project_path': bridge_project_info.project_path,
                        'project_name': bridge_project_info.project_name,
                        'godot_version': bridge_project_info.godot_version,
                        'plugin_version': bridge_project_info.plugin_version,
                        'is_ready': bridge_project_info.is_ready
                    }
            except Exception as e:
                logger.debug(f"Could not get bridge project info: {e}")

        return status

    def _init_templates(self) -> None:
        """Initialize response templates."""
        self.templates = {
            "system_prompt": """
You are Godoty, an expert AI assistant specialized in Godot game development and code modification.

CAPABILITIES:
- Deep understanding of Godot Engine (GDScript, C#, scene system, scripting)
- Advanced codebase analysis using semantic search and vector embeddings
- Direct file modification, creation, and refactoring
- Godot project debugging, optimization, and best practices
- Real-time code generation with context awareness
- Multi-language support (GDScript, C#, TypeScript, JSON)
- Web research for latest Godot documentation and examples

WORKFLOW:
1. Analyze the user's request carefully
2. Use semantic search to find relevant code and context
3. Understand the current project structure and dependencies
4. Plan and execute changes directly with clear explanations
5. Provide code examples and best practice recommendations

RULES:
- Always understand the full context before making changes
- Use semantic search to find related code and examples
- Explain your reasoning for all modifications
- Preserve existing functionality and follow Godot conventions
- Provide complete, working code examples
- Include relevant imports and dependencies
- Test suggestions for common edge cases
- Follow GDScript style guidelines and best practices

ENHANCED RAG:
- You have access to a vector-based code search system
- Use natural language queries like "find player movement code"
- Results include relevance scores and contextual information
- Understand code relationships and dependencies
- Provide intelligent suggestions based on similar implementations

RESPONSE FORMAT:
- Be clear, concise, and helpful
- Use markdown formatting for code blocks
- Include explanations for complex changes
- Provide step-by-step instructions when appropriate
- Highlight important considerations and potential issues
""",

            "code_analysis": """
## Code Analysis

**File:** `{file_path}`
**Language:** `{language}`
**Type:** `{element_type}`

### Understanding
{understanding}

### Dependencies
{dependencies}

### Suggestions
{suggestions}

### Potential Issues
{issues}
""",

            "code_modification": """
## Code Modification

**File:** `{file_path}`
**Change Type:** `{change_type}`

### Changes Made
{changes}

### Updated Code
```{language}
{code}
```

### Reasoning
{reasoning}

### Testing Recommendations
{testing}
"""
        }

    # ===== SESSION MANAGEMENT METHODS =====

    def create_session(self, title: str, project_path: Optional[str] = None) -> str:
        """
        Create a new session for this agent.

        Args:
            title: Session title (will be truncated to 100 chars)
            project_path: Associated project path

        Returns:
            Unique session identifier
        """
        session_id = self.session_manager.create_session(title, project_path or self.project_path)

        # Initialize session context for this agent
        self.session_context[session_id] = {
            'created_at': datetime.utcnow(),
            'message_count': 0,
            'last_activity': None,
            'agent_state': {}
        }

        # Save initial agent state
        self._save_agent_state(session_id)

        logger.info(f"Created new session: {session_id} - {title}")
        return session_id

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get session information."""
        return self.session_manager.get_session(session_id)

    def list_sessions(self, limit: int = 50) -> List[SessionInfo]:
        """List available sessions."""
        return self.session_manager.list_sessions(limit=limit)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        # Remove from agent context
        if session_id in self.session_context:
            del self.session_context[session_id]

        # Delete from session manager
        return self.session_manager.delete_session(session_id)

    def update_session_title(self, session_id: str, title: str) -> bool:
        """Update session title."""
        return self.session_manager.update_session_title(session_id, title)

    def get_conversation_history(self, session_id: str, limit: Optional[int] = None) -> List[MessageEntry]:
        """Get conversation history for a session."""
        return self.session_manager.get_conversation_history(session_id, limit)

    def get_session_metrics(self, session_id: str):
        """Get detailed session metrics."""
        return self.session_manager.get_session_metrics(session_id)

    def _save_agent_state(self, session_id: str) -> bool:
        """Save agent-specific state for session persistence."""
        if session_id not in self.session_context:
            return False

        try:
            agent_state = {
                'session_context': {
                    k: v.isoformat() if isinstance(v, datetime) else v
                    for k, v in self.session_context[session_id].items()
                },
                'context_engine_state': {
                    'project_path': self.project_path,
                    'indexed_files': getattr(self.context_engine, 'indexed_files', [])
                },
                'config': {
                    'model': self.config.get('planning_model'),
                    'temperature': self.config.get('temperature'),
                    'max_tokens': self.config.get('max_tokens')
                }
            }
            return self.session_manager.save_agent_state(session_id, agent_state)
        except Exception as e:
            logger.error(f"Failed to save agent state for {session_id}: {e}")
            return False

    def _load_agent_state(self, session_id: str) -> bool:
        """Load agent-specific state for session."""
        try:
            agent_state = self.session_manager.load_agent_state(session_id)
            if agent_state:
                self.session_context[session_id] = agent_state.get('session_context', {})
                logger.info(f"Loaded agent state for session {session_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to load agent state for {session_id}: {e}")
        return False

    def _record_message(self, session_id: str, message: str, role: str,
                       tokens: int = 0, cost: float = 0.0,
                       model_name: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Record a message in session conversation history.

        Args:
            session_id: Target session
            message: Message content
            role: Message role ('user', 'assistant', 'system', 'tool')
            tokens: Token count for this message
            cost: Cost for this message
            model_name: Model that generated this message
            metadata: Additional message metadata

        Returns:
            True if message was recorded successfully
        """
        try:
            message_entry = MessageEntry(
                message_id=str(uuid.uuid4()),
                role=role,
                content=message,
                timestamp=datetime.utcnow(),
                model_name=model_name,
                tokens=tokens,
                cost=cost,
                metadata=metadata
            )

            success = self.session_manager.add_message(session_id, message_entry)

            if success:
                # Update session context
                if session_id in self.session_context:
                    self.session_context[session_id]['message_count'] += 1
                    self.session_context[session_id]['last_activity'] = datetime.utcnow()

                    # Periodically save agent state (every 10 messages)
                    if self.session_context[session_id]['message_count'] % 10 == 0:
                        self._save_agent_state(session_id)

            return success
        except Exception as e:
            logger.error(f"Failed to record message for {session_id}: {e}")
            return False

    # ===== HELPER METHODS =====

    def _validate_messages_format(self, messages: Any) -> bool:
        """Validate messages format for model interface."""
        if not isinstance(messages, list):
            return False

        for message in messages:
            if not isinstance(message, dict):
                return False
            if 'role' not in message or 'content' not in message:
                return False

        return True

    # ===== MESSAGE PROCESSING METHODS =====

    async def process_message(self, request: GodotyRequest) -> AsyncIterable[GodotyResponse]:
        """
        Process a user message and generate streaming responses.

        Args:
            request: User request with session information

        Yields:
            Streaming GodotyResponse objects
        """
        session_id = request.session_id
        message = request.message

        # Validate session exists
        session_info = self.session_manager.get_session(session_id)
        if not session_info:
            raise ValueError(f"Session {session_id} not found. Please create a session first.")

        # Initialize or load session context
        if session_id not in self.session_context:
            self.session_context[session_id] = {
                "created_at": datetime.utcnow(),
                "message_count": 0,
                "project_path": request.project_path or self.project_path,
                "context_cache": {}
            }
            # Try to load saved agent state
            self._load_agent_state(session_id)

        session = self.session_context[session_id]

        # Record user message in session history
        self._record_message(session_id, message, "user")

        try:
            # Generate unique response ID
            response_id = f"resp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session['message_count']}"

            # Yield initial processing message
            yield GodotyResponse(
                session_id=session_id,
                message_id=response_id,
                response="",
                type="status",
                metadata={"status": "processing", "step": "initialization"},
                confidence=1.0,
                sources=[]
            )

            # Analyze request and get context
            context_results = await self._get_relevant_context(message, request)

            # Yield context analysis
            yield GodotyResponse(
                session_id=session_id,
                message_id=response_id,
                response=f"Found {len(context_results)} relevant code sections in the project...",
                type="analysis",
                metadata={"context_count": len(context_results), "sources": [r.file_path for r in context_results]},
                confidence=0.9,
                sources=[{"file_path": r.file_path, "similarity": r.similarity_score, "type": r.chunk_type} for r in context_results[:5]]
            )

            # Generate response using enhanced context
            full_response = await self._generate_enhanced_response(message, context_results, request)

            # Record assistant response in session history
            model_name = self.config.get('planning_model', 'unknown')
            self._record_message(
                session_id=session_id,
                message=full_response["response"],
                role="assistant",
                model_name=model_name,
                metadata={
                    "type": full_response["type"],
                    "confidence": full_response["confidence"],
                    "context_used": len(context_results),
                    "sources_count": len(full_response.get("sources", []))
                }
            )

            # Stream the response
            yield GodotyResponse(
                session_id=session_id,
                message_id=response_id,
                response=full_response["response"],
                type=full_response["type"],
                metadata=full_response["metadata"],
                confidence=full_response["confidence"],
                sources=full_response.get("sources", [])
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}")

            # Record error in session history
            self._record_message(
                session_id=session_id,
                message=f"Error: {str(e)}",
                role="system",
                metadata={
                    "type": "error",
                    "error_type": type(e).__name__,
                    "error_details": str(e)
                }
            )

            yield GodotyResponse(
                session_id=session_id,
                message_id=response_id,
                response=f"I encountered an error while processing your request: {str(e)}",
                type="error",
                metadata={"error": str(e), "error_type": type(e).__name__},
                confidence=0.1,
                sources=[]
            )

    async def _get_relevant_context(self, query: str, request: GodotyRequest) -> List[Any]:
        """Get relevant context using enhanced RAG."""
        try:
            # Use semantic search from context engine
            context_results = self.context_engine.semantic_search(
                query=query,
                limit=request.context_limit
            )

            logger.info(f"Found {len(context_results)} relevant context items")
            return context_results

        except Exception as e:
            logger.error(f"Error getting context: {e}")
            return []

    async def _generate_enhanced_response(self, message: str, context: List[Any], request: GodotyRequest) -> Dict[str, Any]:
        """Generate response using enhanced context."""
        try:
            # Validate context items
            for i, ctx in enumerate(context):
                if not hasattr(ctx, 'file_path'):
                    logger.warning(f"Context item {i} missing file_path attribute")
                if not hasattr(ctx, 'line_numbers'):
                    logger.warning(f"Context item {i} missing line_numbers attribute")
                elif not isinstance(ctx.line_numbers, tuple):
                    logger.warning(f"Context item {i} line_numbers is not a tuple: {type(ctx.line_numbers)}")

            # Build context-aware prompt
            context_info = self._build_context_prompt(context)

            # Create messages format for model
            user_content = f"USER REQUEST: {message}\n\nPROJECT CONTEXT:\n{context_info}\n\nPlease provide a comprehensive response based on the user's request and the project context above."
            messages = [
                {"role": "system", "content": self.templates['system_prompt']},
                {"role": "user", "content": user_content}
            ]

            # Generate response using model
            try:
                # Validate messages format
                if not self._validate_messages_format(messages):
                    logger.error("Invalid messages format for model")
                    raise ValueError("Messages must be a list of dicts with 'role' and 'content' keys")

                model_response = await self.model.execute(messages)
            except AttributeError:
                # Fallback to stream if execute not available
                logger.warning("model.execute() not available, using stream() as fallback")
                response_parts = []
                async for event in self.model.stream(messages):
                    if "content" in event:
                        response_parts.append(event["content"])
                model_response = "".join(response_parts)
            except Exception as model_error:
                logger.error(f"Error calling model: {model_error}")
                raise model_error

            # Determine response type based on content
            response_type = self._classify_response_type(message, model_response, context)

            # Format response based on type
            formatted_response = self._format_response(model_response, response_type, context)

            return {
                "response": formatted_response,
                "type": response_type,
                "confidence": 0.85,
                "metadata": {
                    "context_used": len(context),
                    "response_length": len(formatted_response),
                    "model_used": self.config.get('planning_model', 'unknown')
                },
                "sources": [
                    {"file_path": ctx.file_path, "similarity": ctx.similarity_score, "type": ctx.chunk_type}
                    for ctx in context[:5]
                ]
            }

        except Exception as e:
            logger.error(f"Error generating enhanced response: {e}")
            return {
                "response": f"I apologize, but I encountered an error generating a response: {str(e)}",
                "type": "error",
                "confidence": 0.1,
                "metadata": {"error": str(e)},
                "sources": []
            }

    def _build_context_prompt(self, context: List[Any]) -> str:
        """Build context information for the prompt."""
        if not context:
            return "No specific context found for this request."

        context_info = "Relevant Code Context:\n\n"

        for i, ctx in enumerate(context[:5]):  # Limit to top 5 results
            start_line, end_line = ctx.line_numbers  # Proper tuple unpacking
            context_info += f"{i+1}. **{ctx.file_path}** (Line {start_line}-{end_line})\n"
            context_info += f"   Type: {ctx.chunk_type}\n"
            context_info += f"   Similarity: {ctx.similarity_score:.2f}\n"
            context_info += f"   Content: {ctx.content[:200]}{'...' if len(ctx.content) > 200 else ''}\n\n"

        return context_info

    def _classify_response_type(self, message: str, response: str, context: List[Any]) -> str:
        """Classify the type of response based on request and content."""
        message_lower = message.lower()

        # Code modification keywords
        if any(keyword in message_lower for keyword in ['modify', 'change', 'fix', 'update', 'implement', 'add', 'remove']):
            return "code_modification"

        # Analysis keywords
        if any(keyword in message_lower for keyword in ['analyze', 'explain', 'understand', 'what is', 'how does', 'why']):
            return "analysis"

        # Debugging keywords
        if any(keyword in message_lower for keyword in ['debug', 'error', 'issue', 'problem', 'broken']):
            return "debugging"

        # Default to text
        return "text"

    def _format_response(self, response: str, response_type: str, context: List[Any]) -> str:
        """Format response based on type."""
        if response_type == "code_modification":
            # Format as code modification response
            return response  # Model should format this properly
        elif response_type == "analysis":
            # Format as analysis response
            return response  # Model should format this properly
        else:
            # Default text response
            return response

    # Tool creation methods
    def _create_read_file_tool(self):
        """Create file reading tool."""
        @tool
        async def read_file(file_path: str) -> str:
            """
            Read and return the contents of a file.

            Args:
                file_path: Path to the file to read

            Returns:
                File contents
            """
            try:
                full_path = Path(self.project_path) / file_path
                if not full_path.exists():
                    return f"Error: File not found: {full_path}"

                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                return f"Contents of {file_path}:\n\n{content}"
            except Exception as e:
                return f"Error reading file {file_path}: {str(e)}"

        return read_file

    def _create_write_file_tool(self):
        """Create file writing tool."""
        @tool
        async def write_file(file_path: str, content: str, create_dirs: bool = True) -> str:
            """
            Write content to a file.

            Args:
                file_path: Path to the file to write
                content: Content to write
                create_dirs: Whether to create parent directories

            Returns:
                Success message
            """
            try:
                full_path = Path(self.project_path) / file_path
                if create_dirs:
                    full_path.parent.mkdir(parents=True, exist_ok=True)

                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                return f"Successfully wrote to {file_path}"
            except Exception as e:
                return f"Error writing file {file_path}: {str(e)}"

        return write_file

    def _create_list_files_tool(self):
        """Create file listing tool."""
        @tool
        async def list_files(directory: str, pattern: str = "*", recursive: bool = True) -> str:
            """
            List files in a directory.

            Args:
                directory: Directory to list
                pattern: File pattern to match
                recursive: Whether to search recursively

            Returns:
                List of files
            """
            try:
                full_path = Path(self.project_path) / directory
                if not full_path.exists():
                    return f"Error: Directory not found: {full_path}"

                if recursive:
                    files = list(full_path.rglob(pattern))
                else:
                    files = list(full_path.glob(pattern))

                file_list = [str(f.relative_to(self.project_path)) for f in files if f.is_file()]
                file_list.sort()

                return f"Files in {directory} matching '{pattern}':\n\n" + "\n".join(file_list)
            except Exception as e:
                return f"Error listing files: {str(e)}"

        return list_files

    def _create_search_code_tool(self):
        """Create code search tool using enhanced RAG."""
        @tool
        async def search_code(query: str, limit: int = 10) -> str:
            """
            Search code using semantic understanding.

            Args:
                query: Natural language search query
                limit: Maximum number of results

            Returns:
                Search results with code snippets
            """
            try:
                results = self.context_engine.semantic_search(query, limit)

                if not results:
                    return f"No code found for query: {query}"

                output = f"Search results for '{query}':\n\n"
                for i, result in enumerate(results, 1):
                    start_line, end_line = result.line_numbers
                    output += f"{i}. **{result.file_path}** (Lines {start_line}-{end_line})\n"
                    output += f"   Type: {result.chunk_type} | Similarity: {result.similarity_score:.2f}\n"
                    output += f"   Explanation: {result.explanation}\n"
                    output += f"   Content: {result.content[:300]}{'...' if len(result.content) > 300 else ''}\n\n"

                return output
            except Exception as e:
                return f"Error searching code: {str(e)}"

        return search_code

    def _create_analyze_code_tool(self):
        """Create code analysis tool."""
        @tool
        async def analyze_code(file_path: str, focus_areas: List[str] = None) -> str:
            """
            Analyze code for issues and improvements.

            Args:
                file_path: Path to the file to analyze
                focus_areas: Specific areas to focus on

            Returns:
                Analysis results
            """
            try:
                full_path = Path(self.project_path) / file_path
                if not full_path.exists():
                    return f"Error: File not found: {full_path}"

                content = full_path.read_text(encoding='utf-8')

                # Use context engine to parse and analyze
                language = full_path.suffix[1:]  # Remove dot
                parsed_elements = self.context_engine.code_parser.parse_file(str(full_path), content)

                analysis = f"Code Analysis for {file_path}\n\n"
                analysis += f"Language: {language}\n"
                analysis += f"Total Elements: {len(parsed_elements)}\n\n"

                # Analyze different element types
                element_types = {}
                for element in parsed_elements:
                    element_types[element.type] = element_types.get(element.type, 0) + 1

                analysis += "Element Types:\n"
                for elem_type, count in element_types.items():
                    analysis += f"- {elem_type}: {count}\n"

                analysis += "\nDetailed Analysis:\n"
                for element in parsed_elements[:5]:  # Show first 5 elements
                    analysis += f"\n**{element.type.title()}: {element.name}**\n"
                    analysis += f"Lines: {element.start_line}-{element.end_line}\n"
                    if element.dependencies:
                        analysis += f"Dependencies: {', '.join(element.dependencies)}\n"

                return analysis
            except Exception as e:
                return f"Error analyzing code: {str(e)}"

        return analyze_code

    def _create_modify_code_tool(self):
        """Create code modification tool."""
        @tool
        async def modify_code(file_path: str, changes: List[Dict[str, Any]]) -> str:
            """
            Modify code with specified changes.

            Args:
                file_path: Path to the file to modify
                changes: List of changes to apply

            Returns:
                Modification results
            """
            try:
                full_path = Path(self.project_path) / file_path
                if not full_path.exists():
                    return f"Error: File not found: {full_path}"

                content = full_path.read_text(encoding='utf-8')
                lines = content.split('\n')

                modifications = []
                for change in changes:
                    change_type = change.get('type', 'replace')
                    line_num = change.get('line_number') - 1  # 0-indexed

                    if 0 <= line_num < len(lines):
                        old_line = lines[line_num]
                        new_line = change.get('new_content', '')

                        if change_type == 'replace':
                            lines[line_num] = new_line
                        elif change_type == 'insert_after':
                            lines.insert(line_num + 1, new_line)
                        elif change_type == 'insert_before':
                            lines.insert(line_num, new_line)
                        elif change_type == 'delete':
                            lines.pop(line_num)

                        modifications.append({
                            'type': change_type,
                            'line': line_num + 1,
                            'old': old_line,
                            'new': new_line
                        })

                # Write modified content
                modified_content = '\n'.join(lines)
                full_path.write_text(modified_content, encoding='utf-8')

                result = f"Successfully modified {file_path}\n\nModifications:\n"
                for mod in modifications:
                    result += f"- Line {mod['line']}: {mod['type']}\n"

                return result
            except Exception as e:
                return f"Error modifying code: {str(e)}"

        return modify_code

    def _create_project_info_tool(self):
        """Create project information tool."""
        @tool
        async def get_project_info() -> str:
            """
            Get information about the Godot project.

            Returns:
                Project information
            """
            try:
                # Try to get real project info from Godot plugin first
                if self.godot_bridge:
                    try:
                        # Ensure connection
                        if not await self.godot_bridge.is_connected():
                            await self.godot_bridge.connect()

                        # Get project info from Godot plugin
                        godot_project_info = await self.godot_bridge.get_project_info()
                        if godot_project_info:
                            output = "Godot Plugin Project Information:\n\n"
                            output += f"- Project Path: {godot_project_info.project_path}\n"
                            output += f"- Project Name: {godot_project_info.project_name}\n"
                            output += f"- Godot Version: {godot_project_info.godot_version}\n"
                            output += f"- Plugin Version: {godot_project_info.plugin_version}\n"
                            output += f"- Is Ready: {godot_project_info.is_ready}\n"
                            return output
                    except Exception as bridge_error:
                        logger.warning(f"Could not get project info from Godot plugin: {bridge_error}")

                # Fallback to file system analysis
                project_info = {
                    "name": Path(self.project_path).name,
                    "path": str(self.project_path),
                    "godot_version": self._detect_godot_version(),
                    "total_files": len(list(Path(self.project_path).rglob("*"))),
                    "script_files": len(list(Path(self.project_path).rglob("*.gd"))),
                    "scene_files": len(list(Path(self.project_path).rglob("*.tscn"))),
                    "cs_files": len(list(Path(self.project_path).rglob("*.cs"))),
                }

                output = "File System Project Information:\n\n"
                for key, value in project_info.items():
                    output += f"- {key.replace('_', ' ').title()}: {value}\n"

                return output
            except Exception as e:
                return f"Error getting project info: {str(e)}"

        return get_project_info

    def _create_scene_info_tool(self):
        """Create scene information tool."""
        @tool
        async def get_scene_info(scene_path: str) -> str:
            """
            Get information about a Godot scene.

            Args:
                scene_path: Path to the scene file

            Returns:
                Scene information
            """
            try:
                full_path = Path(self.project_path) / scene_path
                if not full_path.exists():
                    return f"Error: Scene file not found: {full_path}"

                if full_path.suffix != '.tscn':
                    return f"Error: Not a scene file: {full_path}"

                content = full_path.read_text(encoding='utf-8')
                parsed = self.context_engine.code_parser.parse_file(str(full_path), content)

                nodes = [p for p in parsed if p.type == 'node']
                resources = [p for p in parsed if p.type == 'resource']

                output = f"Scene Information for {scene_path}\n\n"
                output += f"Total Nodes: {len(nodes)}\n"
                output += f"Total Resources: {len(resources)}\n\n"

                if nodes:
                    output += "Nodes:\n"
                    for node in nodes[:10]:  # Show first 10 nodes
                        output += f"- {node.name} (Type: {node.metadata.get('node_type', 'Unknown')})\n"

                return output
            except Exception as e:
                return f"Error getting scene info: {str(e)}"

        return get_scene_info

    def _create_run_godot_tool(self):
        """Create Godot command execution tool."""
        @tool
        async def run_godot_command(command: str, args: List[str] = None) -> str:
            """
            Run a Godot command.

            Args:
                command: Godot command to run
                args: Command arguments

            Returns:
                Command output
            """
            if not self.godot_bridge:
                return "Godot bridge not available"

            try:
                # Ensure connection
                if not await self.godot_bridge.is_connected():
                    connected = await self.godot_bridge.connect()
                    if not connected:
                        return "Failed to connect to Godot plugin"

                # Send command to Godot plugin
                response = await self.godot_bridge.send_command(command, args=args or [])

                if response.success:
                    return f"Command executed successfully: {response.data}"
                else:
                    return f"Command failed: {response.error}"

            except Exception as e:
                return f"Error executing Godot command: {str(e)}"

        return run_godot_command

    def _create_debug_scene_tool(self):
        """Create scene debugging tool."""
        @tool
        async def debug_scene(scene_path: str) -> str:
            """
            Debug a Godot scene for common issues.

            Args:
                scene_path: Path to the scene file

            Returns:
                Debugging results
            """
            # This would implement scene debugging logic
            return f"Would debug scene: {scene_path}"

        return debug_scene

    def _create_search_docs_tool(self):
        """Create documentation search tool."""
        @tool
        async def search_documentation(query: str) -> str:
            """
            Search Godot documentation.

            Args:
                query: Search query

            Returns:
                Documentation results
            """
            # This would implement web search for Godot docs
            return f"Would search documentation for: {query}"

        return search_documentation

    def _create_version_info_tool(self):
        """Create version information tool."""
        @tool
        async def get_godot_version_info() -> str:
            """
            Get Godot version information.

            Returns:
                Version information
            """
            try:
                version = self._detect_godot_version()
                return f"Current Godot version: {version}"
            except Exception as e:
                return f"Error getting version info: {str(e)}"

        return get_godot_version_info

    def _detect_godot_version(self) -> str:
        """Detect Godot version from project."""
        try:
            # Look for version in project.godot
            godot_file = Path(self.project_path) / "project.godot"
            if godot_file.exists():
                content = godot_file.read_text(encoding='utf-8')
                # Parse Godot project file for version
                return self._parse_godot_version(content)
        except Exception:
            pass

        return "Unknown"

    def _parse_godot_version(self, content: str) -> str:
        """Parse Godot version from project file content."""
        # This is a simplified version
        # In production, we'd properly parse the Godot project file format
        if "4.5" in content:
            return "4.5.x"
        elif "4.4" in content:
            return "4.4.x"
        elif "4.3" in content:
            return "4.3.x"
        else:
            return "4.x (latest)"


# Utility function to create and configure the agent
def create_godoty_agent(config: Optional[ModelConfig] = None, project_path: Optional[str] = None) -> GodotyAgent:
    """
    Create and configure a Godoty Agent.

    Args:
        config: Model configuration
        project_path: Root path of the Godot project

    Returns:
        Configured GodotyAgent instance
    """
    return GodotyAgent(config, project_path)