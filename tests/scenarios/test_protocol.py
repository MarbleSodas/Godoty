"""BetterAgents-style scenario tests for Godoty.

These tests simulate end-to-end interactions between the Godot plugin
and the Python brain, validating the full protocol flow.
"""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestHandshakeScenarios:
    """Scenarios for the initial handshake protocol."""

    def test_basic_hello(self) -> None:
        """Scenario: Godot connects and sends hello."""
        client = TestClient(app)
        with client.websocket_connect("/ws/godot") as ws:
            ws.send_text(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "hello",
                    "params": {
                        "client": "godot",
                        "protocol_version": "0.1",
                        "project_name": "Test Project",
                        "godot_version": "4.3",
                    },
                    "id": 1,
                })
            )
            response = json.loads(ws.receive_text())

            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 1
            assert response["result"]["client"] == "godot"
            assert response["result"]["protocol_version"] == "0.2"
            assert "session_id" in response["result"]

    def test_hello_with_minimal_params(self) -> None:
        """Scenario: Godot connects with minimal parameters."""
        client = TestClient(app)
        with client.websocket_connect("/ws/godot") as ws:
            ws.send_text(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "hello",
                    "params": {"client": "godot"},
                    "id": 1,
                })
            )
            response = json.loads(ws.receive_text())

            assert "session_id" in response["result"]


class TestUserMessageScenarios:
    """Scenarios for user message handling via Tauri endpoint."""

    def test_user_message_via_tauri(self) -> None:
        """Scenario: User sends a message via Tauri endpoint.
        
        Note: user_message is only handled by /ws/tauri endpoint.
        This test is skipped as it requires actual LLM integration.
        """
        pytest.skip("Requires LLM integration - tested manually")

    def test_unknown_method_on_godot_endpoint(self) -> None:
        """Scenario: user_message on Godot endpoint returns method not found."""
        client = TestClient(app)
        with client.websocket_connect("/ws/godot") as ws:
            ws.send_text(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "user_message",
                    "params": {"text": "Hello"},
                    "id": 1,
                })
            )
            response = json.loads(ws.receive_text())

            # user_message is only handled on /ws/tauri, not /ws/godot
            assert "error" in response
            assert response["error"]["code"] == -32601


class TestProtocolErrorScenarios:
    """Scenarios for protocol error handling."""

    def test_invalid_json(self) -> None:
        """Scenario: Invalid JSON is rejected."""
        client = TestClient(app)
        with client.websocket_connect("/ws/godot") as ws:
            ws.send_text("not valid json {{{")
            response = json.loads(ws.receive_text())

            assert "error" in response
            assert response["error"]["code"] == -32700

    def test_unknown_method(self) -> None:
        """Scenario: Unknown method returns error."""
        client = TestClient(app)
        with client.websocket_connect("/ws/godot") as ws:
            ws.send_text(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "unknown_method",
                    "params": {},
                    "id": 1,
                })
            )
            response = json.loads(ws.receive_text())

            assert "error" in response
            assert response["error"]["code"] == -32601
            assert "unknown_method" in response["error"]["message"]


class TestEventScenarios:
    """Scenarios for event handling (Godot -> Brain)."""

    def test_console_error_event(self) -> None:
        """Scenario: Godot reports a console error."""
        client = TestClient(app)
        with client.websocket_connect("/ws/godot") as ws:
            # Handshake first
            ws.send_text(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "hello",
                    "params": {"client": "godot"},
                    "id": 1,
                })
            )
            ws.receive_text()

            # Send console error event (no id = no response expected)
            ws.send_text(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "console_error",
                    "params": {
                        "text": "Null reference error",
                        "type": "script_error",
                        "script_path": "res://player.gd",
                        "line": 42,
                    },
                })
            )
            # No response expected for events

    def test_scene_changed_event(self) -> None:
        """Scenario: Active scene changes in editor."""
        client = TestClient(app)
        with client.websocket_connect("/ws/godot") as ws:
            ws.send_text(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "hello",
                    "params": {"client": "godot"},
                    "id": 1,
                })
            )
            ws.receive_text()

            ws.send_text(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "scene_changed",
                    "params": {"scene_path": "res://levels/level_1.tscn"},
                })
            )
            # No response expected


class TestStatusEndpoint:
    """Test the status REST endpoint."""

    def test_status_no_connection(self) -> None:
        """Scenario: Check status when no client connected."""
        client = TestClient(app)
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        # Connection state depends on test ordering, just verify structure
        assert "godot_connected" in data
        assert "tauri_connected" in data
        assert "project_name" in data
        assert "total_tokens" in data
