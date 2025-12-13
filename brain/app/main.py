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
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.agents.tools import resolve_response, set_ws_connection, set_connection_manager
from app.protocol.jsonrpc import (
    ConfirmationRequest,
    ConfirmationResponse,
    ConsoleErrorParams,
    GodotyHelloParams,
    GodotyHelloResult,
    JsonRpcError,
    JsonRpcErrorPayload,
    JsonRpcRequest,
    JsonRpcSuccess,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("godoty.brain")

# Remote LiteLLM proxy URL (where API keys are securely stored)
REMOTE_PROXY_URL = os.getenv(
    "GODOTY_LITELLM_BASE_URL",
    "https://litellm-production-150c.up.railway.app"
)

app = FastAPI(title="Godoty Brain")


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
    user_id: str | None = None  # Supabase user ID
    pending_confirmations: dict[str, asyncio.Future] = field(default_factory=dict)
    total_tokens: int = 0


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
    
    async def _notify_tauri(self, method: str, params: dict) -> None:
        """Send a notification to the Tauri client."""
        if self.tauri:
            try:
                msg = JsonRpcRequest(method=method, params=params).model_dump_json()
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


# Legacy endpoint for backwards compatibility
@app.websocket("/ws")
async def legacy_ws_endpoint(ws: WebSocket) -> None:
    """Legacy WebSocket endpoint - routes to Godot handler."""
    await godot_ws_endpoint(ws)


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
        
        # Register this Godot connection
        await connections.set_godot(conn)
        
        logger.info(f"Godot handshake: project={params.project_name}")
        
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
        return None
    
    if req.method == "script_changed":
        script_path = (req.params or {}).get("script_path")
        logger.info(f"Script changed: {script_path}")
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
        
        return _success(req.id, {
            "session_id": conn.session_id,
            "protocol_version": "0.2",
            "godot_connected": connections.godot is not None,
        })
    
    if req.method == "user_message":
        return await _handle_user_message(conn, req)
    
    if req.method == "confirmation_response":
        return await _handle_confirmation_response(conn, req)
    
    if req.method == "get_status":
        return _success(req.id, {
            "godot_connected": connections.godot is not None,
            "project": {
                "name": connections.godot.project_name,
                "path": connections.godot.project_path,
            } if connections.godot else None,
            "total_tokens": conn.total_tokens,
        })
    
    return _error(req.id, -32601, f"Method not found: {req.method}")


async def _handle_user_message(conn: TauriConnection, req: JsonRpcRequest) -> str:
    """Handle user message - route to agent team with virtual key forwarding."""
    params = req.params or {}
    user_text = params.get("text")
    authorization = params.get("authorization")  # LiteLLM virtual key (from Edge Function)
    model = params.get("model")  # User-selected model (e.g., 'gpt-4o', 'claude-3-5-sonnet-20241022')
    
    if not isinstance(user_text, str) or not user_text.strip():
        return _error(req.id, -32602, "Invalid params", {"text": "required"})
    
    # The authorization token is now a LiteLLM virtual key (from Supabase Edge Function)
    # This key has:
    # - Budget limits enforced by LiteLLM
    # - Model restrictions
    # - 30-day expiration
    # The remote LiteLLM proxy validates the virtual key directly
    
    try:
        from app.agents.team import GodotySession
        
        session = GodotySession(
            session_id=conn.session_id,
            jwt_token=authorization,  # Pass virtual key for LiteLLM auth
            model_id=model,  # Pass user-selected model
        )
        reply_text, metrics = await session.process_message(user_text)
        
        # Update token count
        conn.total_tokens = metrics.get("session_total_tokens", conn.total_tokens)
        
        # Send token update notification
        await conn.ws.send_text(
            JsonRpcRequest(
                method="token_update",
                params={"total": conn.total_tokens}
            ).model_dump_json()
        )
        
        return _success(req.id, {
            "text": reply_text,
            "metrics": metrics,
        })
        
    except ImportError:
        # Fall back to basic reply if team not configured
        from app.agents.basic_agent import generate_reply
        
        reply_text, metrics = generate_reply(user_text)
        return _success(req.id, {
            "text": reply_text,
            "metrics": metrics,
        })
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return _error(req.id, -32000, str(e))


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


# ============================================================================
# Helper Functions (for tools.py)
# ============================================================================


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager (for use in tools.py)."""
    return connections
