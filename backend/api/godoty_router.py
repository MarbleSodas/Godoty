"""
GodotyAPIRouter - Simplified Unified API Router for GodotyAgent

This module provides a streamlined API interface for the single GodotyAgent architecture,
consolidating all agent operations into a clean, efficient router design.

Key Features:
- Unified agent endpoints (no multi-agent complexity)
- Simplified session management
- Real-time streaming with SSE
- Comprehensive metrics and configuration
- Clean error handling and validation
"""

import os
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, AsyncGenerator, Union
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agents.godoty_agent import GodotyAgent, GodotyRequest, GodotyResponse
from agents.unified_session import (
    UnifiedSessionManager, SessionInfo, MessageEntry, get_unified_session_manager
)
from agents.config.model_config import ModelConfig
from core.model import GodotyOpenRouterModel
from utils.serialization import safe_json_dumps

logger = logging.getLogger(__name__)

# Global agent instance
_godoty_agent = None
_session_manager = None


def get_godoty_agent() -> GodotyAgent:
    """Get or create the global GodotyAgent instance."""
    global _godoty_agent
    if _godoty_agent is None:
        _godoty_agent = GodotyAgent()
        logger.info("Created global GodotyAgent instance")
    return _godoty_agent


def get_session_manager() -> UnifiedSessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = get_unified_session_manager()
        logger.info("Created global UnifiedSessionManager instance")
    return _session_manager


# ===== REQUEST/RESPONSE MODELS =====

class SessionCreateRequest(BaseModel):
    """Request to create a new session."""
    title: str = Field(..., min_length=1, max_length=100, description="Session title")
    project_path: Optional[str] = Field(None, description="Associated project path")


class ChatStreamRequest(BaseModel):
    """Request to stream chat responses."""
    message: str = Field(..., min_length=1, description="Message to send to the agent")
    mode: str = Field("planning", description="Agent mode: 'planning' or 'fast'")
    context_limit: int = Field(10, description="Context limit for conversation")
    include_dependencies: bool = Field(True, description="Include project dependencies")


class SessionTitleRequest(BaseModel):
    """Request to update session title."""
    title: str = Field(..., min_length=1, max_length=100, description="New session title")


class SessionCreateResponse(BaseModel):
    """Response after creating a session."""
    session_id: str
    title: str
    project_path: Optional[str]
    created_at: datetime


class SessionListResponse(BaseModel):
    """Response for session listing."""
    sessions: List[Dict[str, Any]]
    total_count: int


class SessionDetailResponse(BaseModel):
    """Detailed session information."""
    session_id: str
    title: str
    project_path: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_active: bool
    message_count: int
    total_tokens: int
    total_cost: float
    metrics: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    """Request to send a chat message."""
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    session_id: str = Field(..., description="Target session ID")
    project_path: Optional[str] = Field(None, description="Override project path")
    context_limit: int = Field(10, ge=1, le=50, description="Context items limit")
    include_dependencies: bool = Field(True, description="Include dependency analysis")
    mode: str = Field("auto", pattern="^(auto|modify|analyze|debug)$", description="Processing mode")


class ChatStreamingEvent(BaseModel):
    """Server-sent event for streaming responses."""
    event_type: str = Field(..., description="Event type")
    data: Dict[str, Any] = Field(..., description="Event data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConfigUpdateRequest(BaseModel):
    """Request to update agent configuration."""
    model_id: Optional[str] = Field(None, description="Model identifier")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature setting")
    max_tokens: Optional[int] = Field(None, ge=1, le=32000, description="Max tokens setting")
    api_key: Optional[str] = Field(None, description="OpenRouter API key")


class ConfigResponse(BaseModel):
    """Current agent configuration."""
    model_id: str
    temperature: float
    max_tokens: int
    has_api_key: bool
    api_key_source: str
    available_models: List[Dict[str, str]]
    metrics_enabled: bool


class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    version: str
    agent_available: bool
    session_manager_available: bool
    storage_available: bool
    godot_tools_available: bool
    mcp_tools_available: bool
    godot_connection_info: Dict[str, Any] = {}
    errors: List[str] = []


# ===== API ROUTER =====

class GodotyAPIRouter:
    """
    Simplified unified API router for the GodotyAgent architecture.

    This router consolidates all agent operations into a single, clean interface
    that removes the complexity of multi-agent workflows while maintaining
    full functionality and performance.
    """

    def __init__(self):
        self.router = APIRouter(prefix="/api/godoty", tags=["godoty"])
        self._register_routes()
        logger.info("GodotyAPIRouter initialized")

    def _register_routes(self):
        """Register all API routes."""

        # Health and status
        self.router.add_api_route(
            "/health", self.health_check, methods=["GET"],
            response_model=HealthCheckResponse
        )
        self.router.add_api_route(
            "/status", self.get_status, methods=["GET"]
        )
        self.router.add_api_route(
            "/connection/status", self.get_connection_status, methods=["GET"]
        )

        # Session management
        self.router.add_api_route(
            "/sessions", self.create_session, methods=["POST"],
            response_model=SessionCreateResponse
        )
        self.router.add_api_route(
            "/sessions", self.list_sessions, methods=["GET"],
            response_model=SessionListResponse
        )
        self.router.add_api_route(
            "/sessions/{session_id}", self.get_session, methods=["GET"],
            response_model=SessionDetailResponse
        )
        self.router.add_api_route(
            "/sessions/{session_id}", self.update_session, methods=["PUT"]
        )
        self.router.add_api_route(
            "/sessions/{session_id}", self.delete_session, methods=["DELETE"]
        )

        # Chat and messaging
        self.router.add_api_route(
            "/sessions/{session_id}/chat", self.chat_message, methods=["POST"]
        )
        self.router.add_api_route(
            "/sessions/{session_id}/chat/stream", self.chat_stream, methods=["POST"]
        )
        self.router.add_api_route(
            "/sessions/{session_id}/history", self.get_chat_history, methods=["GET"]
        )

        # Additional session management endpoints
        self.router.add_api_route(
            "/sessions/{session_id}/title", self.update_session_title, methods=["POST"]
        )
        self.router.add_api_route(
            "/sessions/{session_id}/hide", self.hide_session, methods=["POST"]
        )
        self.router.add_api_route(
            "/sessions/{session_id}/stop", self.stop_session, methods=["POST"]
        )

        # Configuration
        self.router.add_api_route(
            "/config", self.get_config, methods=["GET"],
            response_model=ConfigResponse
        )
        self.router.add_api_route(
            "/config", self.update_config, methods=["POST"]
        )

        # Metrics and analytics
        self.router.add_api_route(
            "/sessions/{session_id}/metrics", self.get_session_metrics, methods=["GET"]
        )
        self.router.add_api_route(
            "/metrics", self.get_global_metrics, methods=["GET"]
        )

    # ===== HEALTH AND STATUS ENDPOINTS =====

    async def health_check(self) -> HealthCheckResponse:
        """Comprehensive health check of the system."""
        errors = []

        try:
            # Check agent availability
            agent = get_godoty_agent()
            agent_available = True
        except Exception as e:
            agent_available = False
            errors.append(f"Agent initialization failed: {str(e)}")

        try:
            # Check session manager
            session_manager = get_session_manager()
            stats = session_manager.get_storage_stats()
            session_manager_available = True
            storage_available = stats.get('database_size_mb', 0) >= 0
        except Exception as e:
            session_manager_available = False
            storage_available = False
            errors.append(f"Session manager failed: {str(e)}")

        # Check tools
        try:
            # Check if Godot executable is available
            godot_executable = os.system("which godot > /dev/null 2>&1") == 0

            # Check actual Godot connection via connection monitor
            godot_plugin_connected = False
            godot_connection_info = {}
            try:
                from services.godot_connection_monitor import get_connection_monitor
                monitor = get_connection_monitor()
                godot_connection_info = monitor.get_status()

                # Consider plugin connected if monitor is running and state is CONNECTED
                godot_plugin_connected = (
                    godot_connection_info.get('running', False) and
                    godot_connection_info.get('state') == 'connected'
                )

                logger.debug(f"Health check Godot connection: {godot_connection_info.get('state', 'unknown')}")

            except ImportError:
                # Fallback to port check if connection monitor not available
                import socket
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1.0)  # Quick 1-second timeout
                    result = sock.connect_ex(('localhost', 9001))
                    sock.close()
                    godot_plugin_connected = (result == 0)
                    godot_connection_info = {'state': 'port_check_fallback', 'port_9001_open': godot_plugin_connected}
                except Exception:
                    godot_plugin_connected = False
                    godot_connection_info = {'state': 'port_check_failed', 'port_9001_open': False}
            except Exception as e:
                logger.debug(f"Error getting connection monitor status: {e}")
                godot_connection_info = {'state': 'error', 'error': str(e)}

            # Godot tools are considered available if either executable exists or plugin is connected
            godot_tools = godot_executable or godot_plugin_connected

            mcp_tools = os.system("which uvx > /dev/null 2>&1") == 0
        except:
            godot_tools = False
            mcp_tools = False
            godot_connection_info = {'state': 'health_check_error'}

        status = "healthy" if not errors else "unhealthy"

        return HealthCheckResponse(
            status=status,
            timestamp=datetime.utcnow(),
            version="2.0.0",
            agent_available=agent_available,
            session_manager_available=session_manager_available,
            storage_available=storage_available,
            godot_tools_available=godot_tools,
            mcp_tools_available=mcp_tools,
            godot_connection_info=godot_connection_info,
            errors=errors
        )

    async def get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        try:
            session_manager = get_session_manager()
            stats = session_manager.get_storage_stats()

            return {
                "status": "operational",
                "timestamp": datetime.utcnow().isoformat(),
                "agent_loaded": _godoty_agent is not None,
                "sessions": {
                    "total": stats.get('total_sessions', 0),
                    "active": stats.get('active_sessions', 0),
                    "total_messages": stats.get('total_messages', 0)
                },
                "storage": {
                    "database_size_mb": stats.get('database_size_mb', 0),
                    "total_tokens": stats.get('total_tokens', 0),
                    "total_cost": stats.get('total_cost', 0.0)
                },
                "tools": {
                    "godot_available": self._check_godot_availability(),
                    "mcp_available": os.system("which uvx > /dev/null 2>&1") == 0
                }
            }
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed Godot connection status."""
        try:
            # Try to get connection monitor status first
            try:
                from services.godot_connection_monitor import get_connection_monitor
                monitor = get_connection_monitor()
                connection_status = monitor.get_status()

                # Add agent-specific connection info
                agent = get_godoty_agent()
                agent_connection_info = agent.get_godot_connection_status()

                # Combine both sources of connection information
                return {
                    "monitor": connection_status,
                    "agent": agent_connection_info,
                    "timestamp": datetime.utcnow().isoformat(),
                    "integration_available": connection_status.get('running', False) and agent_connection_info.get('connected', False)
                }

            except ImportError:
                # Fallback if connection monitor not available
                logger.warning("Connection monitor not available, using agent status only")
                agent = get_godoty_agent()
                agent_connection_info = agent.get_godot_connection_status()

                return {
                    "monitor": {"state": "unavailable", "running": False},
                    "agent": agent_connection_info,
                    "timestamp": datetime.utcnow().isoformat(),
                    "integration_available": agent_connection_info.get('connected', False)
                }

        except Exception as e:
            logger.error(f"Connection status check failed: {e}")
            return {
                "monitor": {"state": "error", "error": str(e)},
                "agent": {"connected": False, "state": "ERROR"},
                "timestamp": datetime.utcnow().isoformat(),
                "integration_available": False
            }

    def _check_godot_availability(self) -> bool:
        """Check if Godot tools are available (either executable or plugin connection)."""
        try:
            # Check if Godot executable is available
            godot_executable = os.system("which godot > /dev/null 2>&1") == 0

            # Check if Godot plugin is actually connected via WebSocket
            import socket
            godot_plugin_connected = False
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)  # Quick 1-second timeout
                result = sock.connect_ex(('localhost', 9001))
                sock.close()
                godot_plugin_connected = (result == 0)
            except Exception:
                godot_plugin_connected = False

            # Godot tools are considered available if either executable exists or plugin is connected
            return godot_executable or godot_plugin_connected
        except Exception:
            return False

    # ===== SESSION MANAGEMENT ENDPOINTS =====

    async def create_session(self, request: SessionCreateRequest) -> SessionCreateResponse:
        """Create a new session."""
        try:
            agent = get_godoty_agent()
            session_id = agent.create_session(request.title, request.project_path)

            return SessionCreateResponse(
                session_id=session_id,
                title=request.title,
                project_path=request.project_path,
                created_at=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Session creation failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def list_sessions(self, limit: int = 50, include_hidden: bool = False) -> SessionListResponse:
        """List available sessions."""
        try:
            session_manager = get_session_manager()
            sessions = session_manager.list_sessions(include_hidden, limit)

            session_data = []
            for session in sessions:
                session_data.append({
                    "session_id": session.session_id,
                    "title": session.title,
                    "project_path": session.project_path,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "is_active": session.is_active,
                    "message_count": session.message_count,
                    "total_tokens": session.total_tokens,
                    "total_cost": session.total_cost
                })

            return SessionListResponse(
                sessions=session_data,
                total_count=len(session_data)
            )
        except Exception as e:
            logger.error(f"Session listing failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_session(self, session_id: str) -> SessionDetailResponse:
        """Get detailed session information."""
        try:
            session_manager = get_session_manager()
            session_info = session_manager.get_session(session_id)

            if not session_info:
                raise HTTPException(status_code=404, detail="Session not found")

            metrics = session_manager.get_session_metrics(session_id)

            return SessionDetailResponse(
                session_id=session_info.session_id,
                title=session_info.title,
                project_path=session_info.project_path,
                created_at=session_info.created_at,
                updated_at=session_info.updated_at,
                is_active=session_info.is_active,
                message_count=session_info.message_count,
                total_tokens=session_info.total_tokens,
                total_cost=session_info.total_cost,
                metrics=metrics.to_dict() if metrics else None
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Session retrieval failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_session(self, session_id: str, title: str) -> Dict[str, Any]:
        """Update session information."""
        try:
            agent = get_godoty_agent()
            success = agent.update_session_title(session_id, title)

            if not success:
                raise HTTPException(status_code=404, detail="Session not found")

            return {
                "session_id": session_id,
                "title": title,
                "updated_at": datetime.utcnow().isoformat(),
                "success": True
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Session update failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """Delete a session (soft delete)."""
        try:
            agent = get_godoty_agent()
            success = agent.delete_session(session_id)

            if not success:
                raise HTTPException(status_code=404, detail="Session not found")

            return {
                "session_id": session_id,
                "deleted_at": datetime.utcnow().isoformat(),
                "success": True
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Session deletion failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ===== CHAT AND MESSAGING ENDPOINTS =====

    async def chat_message(self, request: ChatRequest) -> Dict[str, Any]:
        """Send a chat message and get response (non-streaming)."""
        try:
            agent = get_godoty_agent()
            godoty_request = GodotyRequest(
                message=request.message,
                session_id=request.session_id,
                project_path=request.project_path,
                context_limit=request.context_limit,
                include_dependencies=request.include_dependencies,
                mode=request.mode
            )

            # Collect all streaming responses and return the final one
            responses = []
            async for response in agent.process_message(godoty_request):
                responses.append(response)

            if not responses:
                raise HTTPException(status_code=500, detail="No response generated")

            # Return the final response
            final_response = responses[-1]
            return {
                "session_id": final_response.session_id,
                "message_id": final_response.message_id,
                "response": final_response.response,
                "type": final_response.type,
                "metadata": final_response.metadata,
                "confidence": final_response.confidence,
                "sources": final_response.sources,
                "timestamp": datetime.utcnow().isoformat()
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Chat message failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def chat_stream(self, session_id: str, request: ChatStreamRequest, project_path: Optional[str] = None) -> EventSourceResponse:
        """Stream chat responses using Server-Sent Events."""

        async def generate_sse_events() -> AsyncGenerator[str, None]:
            """Generate SSE events for streaming responses."""
            try:
                agent = get_godoty_agent()
                godoty_request = GodotyRequest(
                    message=request.message,
                    session_id=session_id,
                    project_path=project_path,
                    context_limit=request.context_limit,
                    include_dependencies=request.include_dependencies,
                    mode=request.mode
                )

                async for response in agent.process_message(godoty_request):
                    # Convert response to SSE format
                    event_data = {
                        "session_id": response.session_id,
                        "message_id": response.message_id,
                        "response": response.response,
                        "type": response.type,
                        "metadata": response.metadata,
                        "confidence": response.confidence,
                        "sources": response.sources,
                        "timestamp": datetime.utcnow().isoformat()
                    }

                    # Send SSE event
                    yield f"event: chat_response\n"
                    yield f"data: {safe_json_dumps(event_data)}\n\n"

                # Send completion event
                completion_data = {
                    "session_id": session_id,
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat()
                }
                yield f"event: chat_complete\n"
                yield f"data: {safe_json_dumps(completion_data)}\n\n"

            except ValueError as e:
                # Send error event
                error_data = {
                    "session_id": session_id,
                    "error": str(e),
                    "error_type": "validation_error",
                    "timestamp": datetime.utcnow().isoformat()
                }
                yield f"event: error\n"
                yield f"data: {safe_json_dumps(error_data)}\n\n"

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                error_data = {
                    "session_id": session_id,
                    "error": str(e),
                    "error_type": "server_error",
                    "timestamp": datetime.utcnow().isoformat()
                }
                yield f"event: error\n"
                yield f"data: {safe_json_dumps(error_data)}\n\n"

        return EventSourceResponse(generate_sse_events())

    async def get_chat_history(self, session_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """Get chat history for a session."""
        try:
            agent = get_godoty_agent()
            history = agent.get_conversation_history(session_id, limit)

            messages = []
            for msg in history:
                messages.append({
                    "message_id": msg.message_id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "model_name": msg.model_name,
                    "tokens": msg.tokens,
                    "cost": msg.cost,
                    "metadata": msg.metadata
                })

            return {
                "session_id": session_id,
                "messages": messages,
                "total_count": len(messages),
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Chat history retrieval failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ===== CONFIGURATION ENDPOINTS =====

    async def get_config(self) -> ConfigResponse:
        """Get current agent configuration."""
        try:
            # Check API key availability
            api_key = os.getenv('OPENROUTER_API_KEY')
            has_api_key = bool(api_key)
            api_key_source = "environment" if api_key else "none"

            # Get current configuration
            model_config = ModelConfig.get_model_config()

            # Get available models
            available_models = []
            for name, model_id in model_config.get('allowed_models', {}).items():
                available_models.append({
                    "id": model_id,
                    "name": name,
                    "provider": "openrouter"
                })

            return ConfigResponse(
                model_id=model_config.get('planning_model', 'unknown'),
                temperature=model_config.get('temperature', 0.7),
                max_tokens=model_config.get('max_tokens', 4000),
                has_api_key=has_api_key,
                api_key_source=api_key_source,
                available_models=available_models,
                metrics_enabled=True
            )

        except Exception as e:
            logger.error(f"Config retrieval failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_config(self, request: ConfigUpdateRequest) -> Dict[str, Any]:
        """Update agent configuration."""
        try:
            # This would update the configuration file
            # For now, just validate the request
            updated_fields = {}

            if request.model_id is not None:
                updated_fields["model_id"] = request.model_id
            if request.temperature is not None:
                updated_fields["temperature"] = request.temperature
            if request.max_tokens is not None:
                updated_fields["max_tokens"] = request.max_tokens
            if request.api_key is not None:
                # Note: In production, API key updates should be handled securely
                updated_fields["api_key"] = "updated"

            return {
                "updated_fields": updated_fields,
                "timestamp": datetime.utcnow().isoformat(),
                "success": True
            }

        except Exception as e:
            logger.error(f"Config update failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ===== METRICS ENDPOINTS =====

    async def get_session_metrics(self, session_id: str) -> Dict[str, Any]:
        """Get detailed metrics for a specific session."""
        try:
            session_manager = get_session_manager()
            metrics = session_manager.get_session_metrics(session_id)

            if not metrics:
                raise HTTPException(status_code=404, detail="Session not found")

            return {
                "session_id": session_id,
                "metrics": metrics.to_dict(),
                "timestamp": datetime.utcnow().isoformat()
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Session metrics retrieval failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_global_metrics(self) -> Dict[str, Any]:
        """Get global system metrics."""
        try:
            session_manager = get_session_manager()
            stats = session_manager.get_storage_stats()

            return {
                "global_metrics": {
                    "total_sessions": stats.get('total_sessions', 0),
                    "active_sessions": stats.get('active_sessions', 0),
                    "total_messages": stats.get('total_messages', 0),
                    "total_tokens": stats.get('total_tokens', 0),
                    "total_cost": stats.get('total_cost', 0.0),
                    "database_size_mb": stats.get('database_size_mb', 0)
                },
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Global metrics retrieval failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_session_title(self, session_id: str, request: SessionTitleRequest) -> Dict[str, Any]:
        """Update session title with enhanced error handling and validation."""
        try:
            session_manager = get_session_manager()

            # Validate session exists before attempting update
            if not session_manager.session_exists(session_id):
                logger.warning(f"Session not found for title update: {session_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Session {session_id} not found"
                )

            # Extract and validate title
            title = request.title.strip()
            if not title:
                raise HTTPException(
                    status_code=400,
                    detail="Title cannot be empty"
                )

            if len(title) > 100:
                raise HTTPException(
                    status_code=400,
                    detail="Title cannot exceed 100 characters"
                )

            # Get current title for logging
            current_title = session_manager.get_session_title(session_id)

            # Update session title in the database
            success = session_manager.update_session_title(session_id, title)

            if not success:
                logger.error(f"Failed to update session title in database: {session_id}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to update session title"
                )

            logger.info(f"Updated session title: {session_id} from '{current_title}' to '{title}'")

            return {
                "success": True,
                "status": "success",
                "message": "Session title updated successfully",
                "session_id": session_id,
                "previous_title": current_title,
                "new_title": title
            }

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Error updating session title {session_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update session title: {str(e)}"
            )

    async def hide_session(self, session_id: str) -> Dict[str, Any]:
        """Hide a session (mark as inactive)."""
        try:
            session_manager = get_session_manager()

            # Mark session as hidden/inactive
            success = session_manager.hide_session(session_id)

            if not success:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

            logger.info(f"Hidden session: {session_id}")

            return {
                "status": "success",
                "message": "Session hidden successfully",
                "session_id": session_id
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to hide session: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def stop_session(self, session_id: str) -> Dict[str, Any]:
        """Stop a session (end current activity)."""
        try:
            session_manager = get_session_manager()

            # Stop any ongoing activity in the session
            success = session_manager.stop_session(session_id)

            if not success:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

            logger.info(f"Stopped session: {session_id}")

            return {
                "status": "success",
                "message": "Session stopped successfully",
                "session_id": session_id
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to stop session: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ===== ROUTER INSTANCE =====

def create_godoty_router() -> APIRouter:
    """Create and return the Godoty API router."""
    router_instance = GodotyAPIRouter()
    return router_instance.router


# ===== DEPENDENCY INJECTION =====

async def verify_session_exists(session_id: str) -> bool:
    """Verify that a session exists."""
    session_manager = get_session_manager()
    session_info = session_manager.get_session(session_id)
    return session_info is not None