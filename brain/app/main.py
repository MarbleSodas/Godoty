"""
Godoty Brain - FastAPI WebSocket Server

Handles bidirectional communication between:
- Godot Editor Plugin (perception/actuation)
- Tauri Desktop App (UI, chat, HITL confirmations)

Protocol: JSON-RPC 2.0 over WebSocket
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.agents import get_db
from app.agents.tools import resolve_response, set_ws_connection, set_connection_manager, set_project_path, set_godot_version, clear_pending_requests
from app.agents.context import invalidate_context_cache
from app.protocol.jsonrpc import (
    ConfirmationRequest,
    ConfirmationResponse,
    ConsoleErrorParams,
    GodotyHelloParams,
    GodotyHelloResult,
    HITLPreferences,
    JsonRpcError,
    JsonRpcErrorPayload,
    JsonRpcRequest,
    JsonRpcSuccess,
)
from app.sessions import get_session_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("godoty.brain")

# Remote LiteLLM proxy URL (where API keys are securely stored)
REMOTE_PROXY_URL = os.getenv(
    "GODOTY_LITELLM_BASE_URL",
    "https://litellm-production-150c.up.railway.app"
)

# Shutdown state
_shutdown_event = asyncio.Event()
_active_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    logger.info("[Brain] Starting up...")
    
    # Setup signal handlers for graceful shutdown
    def handle_signal(signum, frame):
        logger.info(f"[Brain] Received signal {signum}, initiating shutdown...")
        _shutdown_event.set()
        # Schedule the async shutdown
        asyncio.get_event_loop().call_soon_threadsafe(
            lambda: asyncio.create_task(_perform_shutdown())
        )
    
    # Register signal handlers (SIGTERM for graceful shutdown)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
    
    yield  # Application runs here
    
    # Shutdown cleanup
    logger.info("[Brain] Shutting down...")
    await _perform_shutdown()
    logger.info("[Brain] Shutdown complete.")


async def _perform_shutdown():
    """Perform comprehensive cleanup on shutdown."""
    _shutdown_event.set()
    
    # Close WebSocket connections gracefully
    if connections.godot:
        try:
            await connections.godot.ws.close(code=1001, reason="Server shutting down")
            logger.info("[Brain] Closed Godot WebSocket connection")
        except Exception as e:
            logger.warning(f"[Brain] Error closing Godot connection: {e}")
    
    if connections.tauri:
        try:
            await connections.tauri.ws.close(code=1001, reason="Server shutting down")
            logger.info("[Brain] Closed Tauri WebSocket connection")
        except Exception as e:
            logger.warning(f"[Brain] Error closing Tauri connection: {e}")
    
    # Cancel all tracked async tasks
    for task in _active_tasks:
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
    _active_tasks.clear()
    
    # Clear pending tool requests
    clear_pending_requests()
    
    logger.info("[Brain] All resources cleaned up")


app = FastAPI(title="Godoty Brain", lifespan=lifespan)


# ============================================================================
# Connection State Management
# ============================================================================


@dataclass
class GodotConnection:
    """State for a Godot Editor connection."""
    ws: WebSocket
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str | None = None
    project_path: str | None = None
    godot_version: str | None = None


@dataclass
class TauriConnection:
    """State for a Tauri Desktop App connection."""
    ws: WebSocket
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str | None = None
    pending_confirmations: dict[str, asyncio.Future] = field(default_factory=dict)
    total_tokens: int = 0
    hitl_preferences: HITLPreferences = field(default_factory=HITLPreferences)
    active_request_task: asyncio.Task | None = None
    active_request_session_id: str | None = None


class ConnectionManager:
    """Manages all active connections (Godot + Tauri)."""
    
    def __init__(self) -> None:
        self.godot: GodotConnection | None = None
        self.tauri: TauriConnection | None = None
        self._lock = asyncio.Lock()
    
    async def set_godot(self, conn: GodotConnection | None) -> None:
        async with self._lock:
            old_conn = self.godot
            self.godot = conn
            
            # Notify Tauri about Godot connection status
            if self.tauri:
                if conn:
                    await self._notify_tauri("godot_connected", {
                        "project": {
                            "name": conn.project_name,
                            "path": conn.project_path,
                            "godotVersion": conn.godot_version,
                        }
                    })
                elif old_conn:
                    await self._notify_tauri("godot_disconnected", {})
    
    async def set_tauri(self, conn: TauriConnection | None) -> None:
        async with self._lock:
            self.tauri = conn
            
            # Send current Godot status to newly connected Tauri
            if conn and self.godot:
                await self._notify_tauri("godot_connected", {
                    "project": {
                        "name": self.godot.project_name,
                        "path": self.godot.project_path,
                        "godotVersion": self.godot.godot_version,
                    }
                })
    
    def _get_project_info(self) -> dict[str, str] | None:
        """Get standardized project info dict."""
        if not self.godot:
            return None
        return {
            "name": self.godot.project_name or "",
            "path": self.godot.project_path or "",
            "godotVersion": self.godot.godot_version or "",
        }

    async def _notify_tauri(self, method: str, params: dict) -> None:
        """Send a notification to the Tauri client."""
        if self.tauri:
            try:
                msg = JsonRpcRequest(method=method, params=params).model_dump_json(exclude_none=True)
                await self.tauri.ws.send_text(msg)
            except Exception as e:
                logger.error(f"Failed to notify Tauri: {e}")
    
    async def request_confirmation(
        self,
        action_type: str,
        description: str,
        details: dict[str, Any],
    ) -> ConfirmationResponse:
        """Request user confirmation via Tauri UI."""
        if not self.tauri:
            # No Tauri connected - auto-deny for safety
            return ConfirmationResponse(
                confirmation_id="",
                approved=False,
            )
        
        confirmation_id = str(uuid.uuid4())
        
        request = ConfirmationRequest(
            confirmation_id=confirmation_id,
            action_type=action_type,  # type: ignore
            description=description,
            details=details,
        )
        
        # Create future to await response
        future: asyncio.Future = asyncio.Future()
        self.tauri.pending_confirmations[confirmation_id] = future
        
        # Send confirmation request to Tauri
        await self.tauri.ws.send_text(
            JsonRpcRequest(
                method="confirmation_request",
                params=request.model_dump(),
            ).model_dump_json()
        )
        
        try:
            # Wait for user response (5 min timeout)
            response = await asyncio.wait_for(future, timeout=300.0)
            return response
        except asyncio.TimeoutError:
            return ConfirmationResponse(
                confirmation_id=confirmation_id,
                approved=False,
            )
        finally:
            self.tauri.pending_confirmations.pop(confirmation_id, None)
    
    def resolve_confirmation(self, confirmation_id: str, response: ConfirmationResponse) -> None:
        """Resolve a pending confirmation with user's decision."""
        if self.tauri and confirmation_id in self.tauri.pending_confirmations:
            self.tauri.pending_confirmations[confirmation_id].set_result(response)
    
    def get_hitl_preferences(self) -> HITLPreferences | None:
        """Get HITL preferences from the connected Tauri client."""
        if self.tauri:
            return self.tauri.hitl_preferences
        return None


# Global connection manager
connections = ConnectionManager()

# Make connection manager available to tools for HITL confirmation routing
set_connection_manager(connections)


def _error(id_: int | str | None, code: int, message: str, data: Any | None = None) -> str:
    return JsonRpcError(
        id=id_,
        error=JsonRpcErrorPayload(code=code, message=message, data=data)
    ).model_dump_json()


def _success(id_: int | str | None, result: Any) -> str:
    return JsonRpcSuccess(id=id_, result=result).model_dump_json()


# ============================================================================
# WebSocket Endpoints
# ============================================================================


@app.websocket("/ws/godot")
async def godot_ws_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for Godot Editor plugin."""
    await ws.accept()
    conn = GodotConnection(ws=ws)
    
    logger.info(f"Godot connection established, session: {conn.session_id}")
    set_ws_connection(ws)  # For tool communication
    
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
                req = JsonRpcRequest.model_validate(payload)
            except Exception as exc:
                await ws.send_text(_error(None, -32700, "Invalid JSON-RPC", str(exc)))
                continue
            
            response = await _handle_godot_request(conn, req)
            if response:
                await ws.send_text(response)
    
    except WebSocketDisconnect:
        logger.info(f"Godot disconnected, session: {conn.session_id}")
    finally:
        await connections.set_godot(None)
        set_ws_connection(None)
        set_project_path(None)
        set_godot_version(None)
        clear_pending_requests()
        invalidate_context_cache()


@app.websocket("/ws/tauri")
async def tauri_ws_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for Tauri desktop app."""
    await ws.accept()
    conn = TauriConnection(ws=ws)
    
    logger.info(f"Tauri connection established, session: {conn.session_id}")
    
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
                req = JsonRpcRequest.model_validate(payload)
            except Exception as exc:
                await ws.send_text(_error(None, -32700, "Invalid JSON-RPC", str(exc)))
                continue
            
            response = await _handle_tauri_request(conn, req)
            if response:
                await ws.send_text(response)
    
    except WebSocketDisconnect:
        logger.info(f"Tauri disconnected, session: {conn.session_id}")
    finally:
        await connections.set_tauri(None)


# ============================================================================
# Godot Request Handlers
# ============================================================================


async def _handle_godot_request(conn: GodotConnection, req: JsonRpcRequest) -> str | None:
    """Route and handle requests from Godot."""
    
    if req.method == "hello":
        try:
            params = GodotyHelloParams.model_validate(req.params or {})
        except Exception as exc:
            return _error(req.id, -32602, "Invalid params", str(exc))
        
        conn.project_name = params.project_name
        conn.project_path = (req.params or {}).get("project_path")
        conn.godot_version = params.godot_version
        
        # Set project path for scoped file tools
        if conn.project_path:
            set_project_path(conn.project_path)
        
        # Parse and set Godot version (major.minor format)
        parsed_version = None
        if conn.godot_version:
            version_parts = conn.godot_version.split(".")
            if len(version_parts) >= 2:
                parsed_version = f"{version_parts[0]}.{version_parts[1]}"
        set_godot_version(parsed_version)
        
        # Register this Godot connection
        await connections.set_godot(conn)
        
        logger.info(f"Godot handshake: project={params.project_name}, version={parsed_version}, path={conn.project_path}")
        
        # Trigger background documentation check/indexing
        if parsed_version:
            asyncio.create_task(_check_and_index_documentation(parsed_version))
        
        return _success(req.id, {
            "client": params.client,
            "session_id": conn.session_id,
            "protocol_version": "0.2",
        })
    
    if req.method == "tool_response":
        params = req.params or {}
        request_id = params.get("request_id")
        result = params.get("result")
        if request_id is not None:
            resolve_response(request_id, result)
        return None
    
    if req.method == "console_error":
        try:
            params = ConsoleErrorParams.model_validate(req.params or {})
            logger.info(f"Console {params.type}: {params.text}")
        except Exception as e:
            logger.error(f"Invalid console error: {e}")
        return None
    
    if req.method == "scene_changed":
        scene_path = (req.params or {}).get("scene_path")
        logger.info(f"Scene changed: {scene_path}")
        invalidate_context_cache()  # Scene changes may affect context
        return None
    
    if req.method == "script_changed":
        script_path = (req.params or {}).get("script_path")
        logger.info(f"Script changed: {script_path}")
        invalidate_context_cache()  # Script changes may affect context
        return None
    
    return _error(req.id, -32601, f"Method not found: {req.method}")


# ============================================================================
# Tauri Request Handlers
# ============================================================================


async def _handle_tauri_request(conn: TauriConnection, req: JsonRpcRequest) -> str | None:
    """Route and handle requests from Tauri."""
    
    if req.method == "hello":
        # Register this Tauri connection
        await connections.set_tauri(conn)
        
        # Include project info if Godot is already connected
        # This ensures Tauri gets the project name immediately on connect
        project_info = connections._get_project_info()
        
        # List existing sessions (don't create new ones - sessions are created on first message)
        session_manager = get_session_manager()
        sessions = session_manager.list_sessions()
        
        # Get the most recent session as the active one (if any exist)
        active_session_id = sessions[0].id if sessions else None
        
        return _success(req.id, {
            "session_id": conn.session_id,
            "protocol_version": "0.2",
            "godot_connected": connections.godot is not None,
            "project": project_info,
            "sessions": [
                {
                    "id": s.id,
                    "title": s.title,
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                    "message_count": s.message_count,
                    "total_tokens": s.total_tokens,
                    "total_cost": s.total_cost,
                }
                for s in sessions
            ],
            "active_session_id": active_session_id,
        })
    
    if req.method == "user_message":
        return await _handle_user_message(conn, req)
    
    if req.method == "confirmation_response":
        return await _handle_confirmation_response(conn, req)
    
    if req.method == "get_status":
        return _success(req.id, {
            "godot_connected": connections.godot is not None,
            "project": connections._get_project_info(),
            "total_tokens": conn.total_tokens,
        })
    
    # Session management methods
    if req.method == "list_sessions":
        return _handle_list_sessions(req)
    
    if req.method == "create_session":
        return _handle_create_session(req)
    
    if req.method == "delete_session":
        return _handle_delete_session(req)
    
    if req.method == "rename_session":
        return _handle_rename_session(req)
    
    if req.method == "get_session_history":
        return await _handle_get_session_history(req)
    
    # Knowledge Base Management
    if req.method == "admin_reindex_knowledge":
        # Start reindexing in background
        asyncio.create_task(_reindex_knowledge_task(conn, req.params or {}))
        return None  # Task sends notifications
        
    if req.method == "get_knowledge_status":
        from app.knowledge.godot_knowledge import get_godot_knowledge
        from app.agents.tools import get_godot_version
        
        version = get_godot_version() or "4.5"
            
        knowledge = get_godot_knowledge(version=version)
        
        is_indexed = await knowledge.is_indexed()
        doc_count = 0
        
        if is_indexed:
            try:
                doc_count = await knowledge.vector_db.async_get_count()
            except Exception:
                pass
        
        return _success(req.id, {
            "version": version,
            "is_indexed": is_indexed,
            "is_indexing": knowledge.is_indexing,
            "document_count": doc_count,
        })
    
    if req.method == "list_indexed_versions":
        return await _handle_list_indexed_versions(req)
    
    if req.method == "delete_indexed_version":
        return await _handle_delete_indexed_version(req)
    
    if req.method == "reindex_version":
        asyncio.create_task(_reindex_knowledge_task(conn, req.params or {}))
        return _success(req.id, {"status": "started"})
    
    if req.method == "set_hitl_preferences":
        return _handle_set_hitl_preferences(conn, req)
    
    if req.method == "get_hitl_preferences":
        return _handle_get_hitl_preferences(conn, req)
    
    if req.method == "cancel_request":
        return await _handle_cancel_request(conn, req)
    
    return _error(req.id, -32601, f"Method not found: {req.method}")


async def _handle_user_message(conn: TauriConnection, req: JsonRpcRequest) -> str:
    """Handle user message - route to agent team with streaming and virtual key forwarding."""
    params = req.params or {}
    user_text = params.get("text")
    authorization = params.get("authorization")  # LiteLLM virtual key (from Edge Function)
    model = params.get("model")  # User-selected model (e.g., 'gpt-4o', 'claude-3-5-sonnet-20241022')
    session_id = params.get("session_id")  # Session ID for conversation continuity
    
    if not isinstance(user_text, str) or not user_text.strip():
        return _error(req.id, -32602, "Invalid params", {"text": "required"})
    
    # Get session manager for metadata updates
    session_manager = get_session_manager()
    
    # Track if we're creating a new session (for UI notifications)
    is_new_session = False
    
    # Ensure we have a valid session ID
    if not session_id:
        # Create a new session with title from user message
        title = session_manager.generate_title_from_message(user_text)
        session = session_manager.create_session(title=title)
        session_id = session.id
        is_new_session = True
    else:
        # Check if session exists
        session = session_manager.get_session(session_id)
        if not session:
            # Create session with title from user message
            title = session_manager.generate_title_from_message(user_text)
            session = session_manager.create_session(title=title, session_id=session_id)
            is_new_session = True
    
    # The authorization token is now a LiteLLM virtual key (from Supabase Edge Function)
    # This key has:
    # - Budget limits enforced by LiteLLM
    # - Model restrictions
    # - 30-day expiration
    # The remote LiteLLM proxy validates the virtual key directly
    
    try:
        from app.agents.team import GodotySession
        
        db = get_db()
        
        conn.active_request_session_id = session_id
        
        godoty_session = GodotySession(
            session_id=session_id,
            jwt_token=authorization,
            model_id=model,
            db=db,
        )
        
        # Use streaming to send chunks in real-time
        full_content = ""
        final_metrics = {}
        collected_tool_calls = []
        collected_reasoning = []
        
        async for chunk in godoty_session.process_message_stream(user_text):
            if chunk["type"] == "chunk":
                await conn.ws.send_text(
                    JsonRpcRequest(
                        method="stream_chunk",
                        params={"content": chunk["content"], "session_id": session_id}
                    ).model_dump_json()
                )
                full_content += chunk["content"]
            
            elif chunk["type"] == "tool_call_started":
                await conn.ws.send_text(
                    JsonRpcRequest(
                        method="stream_tool_call",
                        params={"status": "started", "tool": chunk["tool"], "session_id": session_id}
                    ).model_dump_json()
                )
                collected_tool_calls.append(chunk["tool"])
            
            elif chunk["type"] == "tool_call_completed":
                await conn.ws.send_text(
                    JsonRpcRequest(
                        method="stream_tool_call",
                        params={"status": "completed", "tool": chunk["tool"], "session_id": session_id}
                    ).model_dump_json()
                )
                # Update in our list
                for tc in collected_tool_calls:
                    if tc.get("id") == chunk["tool"].get("id"):
                        tc.update(chunk["tool"])
                        break
            
            elif chunk["type"] == "reasoning_started":
                await conn.ws.send_text(
                    JsonRpcRequest(
                        method="stream_reasoning",
                        params={"status": "started", "session_id": session_id}
                    ).model_dump_json()
                )
            
            elif chunk["type"] == "reasoning":
                await conn.ws.send_text(
                    JsonRpcRequest(
                        method="stream_reasoning",
                        params={"status": "step", "content": chunk["content"], "session_id": session_id}
                    ).model_dump_json()
                )
                collected_reasoning.append(chunk["content"])
            
            elif chunk["type"] == "reasoning_completed":
                await conn.ws.send_text(
                    JsonRpcRequest(
                        method="stream_reasoning",
                        params={"status": "completed", "session_id": session_id}
                    ).model_dump_json()
                )
                
            elif chunk["type"] == "done":
                full_content = chunk["content"]
                final_metrics = chunk.get("metrics", {})
                # Update with collected data if not in metrics
                if "tool_calls" not in final_metrics:
                    final_metrics["tool_calls"] = collected_tool_calls
                if "reasoning" not in final_metrics:
                    final_metrics["reasoning"] = collected_reasoning
                
            elif chunk["type"] == "error":
                error_msg = chunk.get("error", "Unknown error")
                if "budget" in error_msg.lower() or "insufficient" in error_msg.lower():
                    return _error(req.id, -32001, "Insufficient credits. Please purchase more credits to continue.", {
                        "error_type": "budget_exceeded",
                        "suggestion": "Purchase credits to continue using Godoty"
                    })
                return _error(req.id, -32000, error_msg)
        
        # Check for budget exceeded error in metrics
        if final_metrics.get("error") and "budget" in str(final_metrics.get("error", "")).lower():
            return _error(req.id, -32001, "Insufficient credits. Please purchase more credits to continue.", {
                "error_type": "budget_exceeded",
                "suggestion": "Purchase credits to continue using Godoty"
            })
        
        # Extract metrics for session storage
        request_tokens = (final_metrics.get("input_tokens") or 0) + (final_metrics.get("output_tokens") or 0)
        request_cost = final_metrics.get("request_cost") or 0.0
        
        # Update session metadata - increment message count and add metrics
        # (title was already set on session creation)
        session_manager.update_session(
            session_id, 
            increment_messages=True,
            add_tokens=request_tokens,
            add_cost=request_cost,
        )
        
        # Get updated session for notification
        updated_session = session_manager.get_session(session_id)
        
        # Update token count
        conn.total_tokens = final_metrics.get("session_total_tokens", conn.total_tokens)
        
        await conn.ws.send_text(
            JsonRpcRequest(
                method="token_update",
                params={"total": conn.total_tokens, "session_id": session_id}
            ).model_dump_json()
        )
        
        # Send session update notification to refresh sidebar
        if updated_session:
            await conn.ws.send_text(
                JsonRpcRequest(
                    method="session_updated",
                    params={
                        "session": {
                            "id": updated_session.id,
                            "title": updated_session.title,
                            "created_at": updated_session.created_at.isoformat(),
                            "updated_at": updated_session.updated_at.isoformat(),
                            "message_count": updated_session.message_count,
                            "total_tokens": updated_session.total_tokens,
                            "total_cost": updated_session.total_cost,
                        },
                        "is_new": is_new_session,
                    }
                ).model_dump_json()
            )
        
        # Send stream complete notification with final metrics and collected data
        await conn.ws.send_text(
            JsonRpcRequest(
                method="stream_complete",
                params={
                    "metrics": final_metrics,
                    "session_id": session_id,
                    "tool_calls": final_metrics.get("tool_calls", []),
                    "reasoning": final_metrics.get("reasoning", []),
                }
            ).model_dump_json()
        )
        
        return _success(req.id, {
            "text": full_content,
            "metrics": final_metrics,
            "session_id": session_id,
        })
        
    except asyncio.CancelledError:
        logger.info(f"Request cancelled for session {session_id}")
        return _success(req.id, {"cancelled": True, "session_id": session_id})
        
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Error processing message: {e}")
        
        if "403" in error_msg or "budget" in error_msg or "exceeded" in error_msg or "insufficient" in error_msg:
            return _error(req.id, -32001, "Insufficient credits. Please purchase more credits to continue.", {
                "error_type": "budget_exceeded",
                "suggestion": "Purchase credits to continue using Godoty"
            })
        
        return _error(req.id, -32000, str(e))
    
    finally:
        conn.active_request_session_id = None


async def _handle_confirmation_response(conn: TauriConnection, req: JsonRpcRequest) -> str | None:
    """Handle user's confirmation decision from Tauri."""
    params = req.params or {}
    
    try:
        response = ConfirmationResponse.model_validate(params)
        connections.resolve_confirmation(response.confirmation_id, response)
        logger.info(f"Confirmation {response.confirmation_id}: approved={response.approved}")
    except Exception as e:
        logger.error(f"Invalid confirmation response: {e}")
    
    return None


# ============================================================================
# HITL Preferences Handlers
# ============================================================================


def _handle_set_hitl_preferences(conn: TauriConnection, req: JsonRpcRequest) -> str:
    params = req.params or {}
    try:
        prefs = HITLPreferences.model_validate(params)
        conn.hitl_preferences = prefs
        enabled_actions = [k for k, v in prefs.always_allow.items() if v]
        logger.info(f"Updated HITL preferences: always_allow_all={prefs.always_allow_all}, enabled={enabled_actions}")
        return _success(req.id, {"updated": True})
    except Exception as e:
        return _error(req.id, -32602, f"Invalid preferences: {e}")


def _handle_get_hitl_preferences(conn: TauriConnection, req: JsonRpcRequest) -> str:
    return _success(req.id, conn.hitl_preferences.model_dump())


async def _handle_cancel_request(conn: TauriConnection, req: JsonRpcRequest) -> str:
    session_id = conn.active_request_session_id
    
    if conn.active_request_task and not conn.active_request_task.done():
        conn.active_request_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(conn.active_request_task), timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        logger.info(f"Request cancelled by user for session {session_id}")
    
    if session_id:
        try:
            await conn.ws.send_text(
                JsonRpcRequest(
                    method="stream_cancelled",
                    params={"session_id": session_id}
                ).model_dump_json()
            )
        except Exception:
            pass
    
    conn.active_request_task = None
    conn.active_request_session_id = None
    
    return _success(req.id, {"cancelled": True, "session_id": session_id})


# ============================================================================
# Session Management Handlers
# ============================================================================


def _handle_list_sessions(req: JsonRpcRequest) -> str:
    """List all available sessions."""
    session_manager = get_session_manager()
    sessions = session_manager.list_sessions()
    
    return _success(req.id, {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "message_count": s.message_count,
            }
            for s in sessions
        ]
    })


def _handle_create_session(req: JsonRpcRequest) -> str:
    """Create a new chat session."""
    params = req.params or {}
    title = params.get("title", "New Chat")
    
    session_manager = get_session_manager()
    session = session_manager.create_session(title=title)
    
    return _success(req.id, {
        "session": {
            "id": session.id,
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "message_count": session.message_count,
        }
    })


def _handle_delete_session(req: JsonRpcRequest) -> str:
    """Delete a session by ID."""
    params = req.params or {}
    session_id = params.get("session_id")
    
    if not session_id:
        return _error(req.id, -32602, "Invalid params", {"session_id": "required"})
    
    session_manager = get_session_manager()
    deleted = session_manager.delete_session(session_id)
    
    if deleted:
        return _success(req.id, {"deleted": True, "session_id": session_id})
    else:
        return _error(req.id, -32001, "Session not found", {"session_id": session_id})


def _handle_rename_session(req: JsonRpcRequest) -> str:
    """Rename a session."""
    params = req.params or {}
    session_id = params.get("session_id")
    title = params.get("title")
    
    if not session_id:
        return _error(req.id, -32602, "Invalid params", {"session_id": "required"})
    if not title:
        return _error(req.id, -32602, "Invalid params", {"title": "required"})
    
    session_manager = get_session_manager()
    session = session_manager.update_session(session_id, title=title)
    
    if session:
        return _success(req.id, {
            "session": {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "message_count": session.message_count,
            }
        })
    else:
        return _error(req.id, -32001, "Session not found", {"session_id": session_id})


async def _handle_get_session_history(req: JsonRpcRequest) -> str:
    """Get chat history for a session.
    
    This queries Agno's internal session storage to retrieve messages with timestamps.
    """
    params = req.params or {}
    session_id = params.get("session_id")
    
    if not session_id:
        return _error(req.id, -32602, "Invalid params", {"session_id": "required"})
    
    # Check if session exists in our metadata table
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        return _error(req.id, -32001, "Session not found", {"session_id": session_id})
    
    # Query Agno's session storage for messages
    try:
        from datetime import datetime
        from app.agents.team import GodotySession
        
        db = get_db()
        godoty_session = GodotySession(session_id=session_id, db=db)
        
        # Try to get chat history from the team - pass session_id explicitly
        messages = []
        try:
            history = godoty_session.team.get_chat_history(session_id=session_id)
            if history:
                for msg in history:
                    # Handle Pydantic models properly
                    if hasattr(msg, "model_dump"):
                        msg_dict = msg.model_dump()
                    else:
                        msg_dict = {
                            "role": getattr(msg, "role", "unknown"),
                            "content": getattr(msg, "content", ""),
                            "created_at": getattr(msg, "created_at", None),
                        }
                    
                    # Extract timestamp (could be 'created_at' or 'timestamp')
                    timestamp = msg_dict.get("created_at") or msg_dict.get("timestamp")
                    
                    # Convert Unix timestamp to ISO string if needed
                    if isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp).isoformat()
                    elif timestamp is None:
                        timestamp = datetime.now().isoformat()
                    
                    messages.append({
                        "role": msg_dict.get("role", "unknown"),
                        "content": msg_dict.get("content", ""),
                        "created_at": timestamp,
                    })
        except Exception as hist_error:
            logger.warning(f"Could not retrieve chat history: {hist_error}")
        
        return _success(req.id, {
            "session_id": session_id,
            "title": session.title,
            "messages": messages,
        })
        
    except Exception as e:
        logger.error(f"Error retrieving session history: {e}")
        return _error(req.id, -32000, f"Error retrieving history: {str(e)}")


# ============================================================================
# REST Endpoints
# ============================================================================


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, Any]:
    """Get current server status."""
    return {
        "godot_connected": connections.godot is not None,
        "tauri_connected": connections.tauri is not None,
        "project_name": connections.godot.project_name if connections.godot else None,
        "total_tokens": connections.tauri.total_tokens if connections.tauri else 0,
    }


@app.post("/shutdown")
async def shutdown() -> dict[str, str]:
    """Gracefully shutdown the brain server.
    
    Called by Tauri before killing the sidecar process.
    Closes all connections and cleans up resources.
    """
    logger.info("[Brain] Shutdown requested via REST API")
    
    # Perform cleanup
    await _perform_shutdown()
    
    # Schedule server shutdown after response is sent
    # This gives time for the response to be sent back to Tauri
    async def delayed_exit():
        await asyncio.sleep(0.5)
        logger.info("[Brain] Exiting process")
        os._exit(0)
    
    asyncio.create_task(delayed_exit())
    
    return {"status": "shutting_down"}


# ============================================================================
# Helper Functions (for tools.py)
# ============================================================================


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager (for use in tools.py)."""
    return connections


async def _check_and_index_documentation(version: str) -> None:
    """Check if docs are indexed for this version, index in background if not."""
    try:
        from app.knowledge.godot_knowledge import get_godot_knowledge
        
        knowledge = get_godot_knowledge(version=version)
        is_indexed = await knowledge.is_indexed()
        
        doc_count = 0
        if is_indexed:
            try:
                doc_count = await knowledge.vector_db.async_get_count()
            except Exception:
                pass
        
        if connections.tauri:
            await connections.tauri.ws.send_text(
                JsonRpcRequest(
                    method="knowledge_status_update",
                    params={
                        "status": "indexed" if is_indexed else "not_indexed",
                        "version": version,
                        "document_count": doc_count,
                    }
                ).model_dump_json()
            )
        
        if not is_indexed and not knowledge.is_indexing:
            logger.info(f"Starting background indexing for Godot {version}")
            
            if connections.tauri:
                await connections.tauri.ws.send_text(
                    JsonRpcRequest(
                        method="knowledge_status_update",
                        params={"status": "indexing", "version": version}
                    ).model_dump_json()
                )
            
            def progress_callback(current: int, total: int) -> None:
                if connections.tauri:
                    asyncio.create_task(connections.tauri.ws.send_text(
                        JsonRpcRequest(
                            method="knowledge_indexing_progress",
                            params={"current": current, "total": total, "version": version, "phase": "fetching"}
                        ).model_dump_json()
                    ))
            
            def embedding_callback(current: int, total: int) -> None:
                if connections.tauri:
                    asyncio.create_task(connections.tauri.ws.send_text(
                        JsonRpcRequest(
                            method="knowledge_indexing_progress",
                            params={"current": current, "total": total, "version": version, "phase": "embedding"}
                        ).model_dump_json()
                    ))
            
            success = await knowledge.load(
                progress_callback=progress_callback,
                embedding_callback=embedding_callback
            )
            
            doc_count = 0
            if success:
                try:
                    doc_count = await knowledge.vector_db.async_get_count()
                except Exception:
                    pass
            
            if connections.tauri:
                await connections.tauri.ws.send_text(
                    JsonRpcRequest(
                        method="knowledge_status_update",
                        params={
                            "status": "loaded" if success else "error",
                            "version": version,
                            "document_count": doc_count,
                            "error": None if success else "Failed to load documentation"
                        }
                    ).model_dump_json()
                )
                
    except Exception as e:
        logger.error(f"Background indexing check failed: {e}")


async def _handle_list_indexed_versions(req: JsonRpcRequest) -> str:
    from pathlib import Path
    
    knowledge_dir = Path.home() / ".godoty" / "knowledge"
    versions = []
    
    if knowledge_dir.exists():
        for item in knowledge_dir.iterdir():
            if item.is_dir() and item.name.endswith(".lance"):
                table_name = item.name.replace(".lance", "")
                if table_name.startswith("godot_docs_") or table_name.startswith("godot_enhanced_"):
                    parts = table_name.rsplit("_", 2)
                    if len(parts) >= 3:
                        version_str = f"{parts[-2]}.{parts[-1]}"
                    else:
                        continue
                    
                    doc_count = 0
                    size_mb = 0.0
                    try:
                        from app.knowledge.godot_knowledge import get_godot_knowledge
                        knowledge = get_godot_knowledge(version=version_str)
                        if await knowledge.is_indexed():
                            doc_count = await knowledge.vector_db.async_get_count()
                        
                        size_bytes = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                        size_mb = round(size_bytes / (1024 * 1024), 2)
                    except Exception:
                        pass
                    
                    existing = next((v for v in versions if v["version"] == version_str), None)
                    if existing:
                        existing["document_count"] += doc_count
                        existing["size_mb"] += size_mb
                    else:
                        versions.append({
                            "version": version_str,
                            "document_count": doc_count,
                            "size_mb": size_mb,
                        })
    
    versions.sort(key=lambda x: x["version"], reverse=True)
    return _success(req.id, {"versions": versions})


async def _handle_delete_indexed_version(req: JsonRpcRequest) -> str:
    import shutil
    from pathlib import Path
    
    params = req.params or {}
    version = params.get("version")
    
    if not version:
        return _error(req.id, -32602, "Invalid params", {"version": "required"})
    
    knowledge_dir = Path.home() / ".godoty" / "knowledge"
    deleted = False
    
    for prefix in ["godot_docs_", "godot_enhanced_"]:
        table_name = f"{prefix}{version.replace('.', '_')}"
        table_path = knowledge_dir / f"{table_name}.lance"
        
        if table_path.exists():
            try:
                shutil.rmtree(table_path)
                deleted = True
            except Exception as e:
                return _error(req.id, -32000, f"Failed to delete: {e}")
    
    from app.knowledge.godot_knowledge import _knowledge_cache
    from app.knowledge.enhanced_knowledge import _enhanced_knowledge_cache
    
    cache_key = f"{version}:default"
    _knowledge_cache.pop(cache_key, None)
    _enhanced_knowledge_cache.pop(cache_key, None)
    
    if deleted:
        return _success(req.id, {"deleted": True, "version": version})
    else:
        return _error(req.id, -32001, f"No indexed data found for version {version}")


async def _reindex_knowledge_task(conn: TauriConnection, params: dict) -> None:
    """Background task to reindex Godot documentation."""
    try:
        from app.knowledge.godot_knowledge import get_godot_knowledge
        from app.agents.tools import get_godot_version
        
        version = params.get("version") or get_godot_version() or "4.5"
        
        logger.info(f"Starting manual reindexing for Godot {version}")
        
        # Notify start
        await conn.ws.send_text(
            JsonRpcRequest(
                method="knowledge_status_update",
                params={"status": "indexing", "version": version}
            ).model_dump_json()
        )
        
        # Define progress callback for fetching
        def progress_callback(current: int, total: int) -> None:
            # Create a task to send notification (callback is sync)
            asyncio.create_task(conn.ws.send_text(
                JsonRpcRequest(
                    method="knowledge_indexing_progress",
                    params={"current": current, "total": total, "version": version, "phase": "fetching"}
                ).model_dump_json()
            ))

        # Define progress callback for embedding
        def embedding_callback(current: int, total: int) -> None:
            asyncio.create_task(conn.ws.send_text(
                JsonRpcRequest(
                    method="knowledge_indexing_progress",
                    params={"current": current, "total": total, "version": version, "phase": "embedding"}
                ).model_dump_json()
            ))

        knowledge = get_godot_knowledge(version=version)
        success = await knowledge.load(force_reload=True, progress_callback=progress_callback, embedding_callback=embedding_callback)
        
        # Get count if successful
        doc_count = 0
        if success:
            try:
                doc_count = await knowledge.vector_db.async_get_count()
            except Exception:
                pass
        
        # Notify completion
        await conn.ws.send_text(
            JsonRpcRequest(
                method="knowledge_status_update",
                params={
                    "status": "loaded" if success else "error",
                    "version": version,
                    "document_count": doc_count,
                    "error": None if success else "Failed to load documentation"
                }
            ).model_dump_json()
        )
        
    except Exception as e:
        logger.error(f"Reindexing failed: {e}")
        await conn.ws.send_text(
            JsonRpcRequest(
                method="knowledge_status_update",
                params={
                    "status": "error",
                    "version": version,
                    "error": str(e)
                }
            ).model_dump_json()
        )
