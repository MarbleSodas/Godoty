import json

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ws_hello() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "hello",
                    "params": {"client": "godot", "protocol_version": "0.2"},
                    "id": 1,
                }
            )
        )
        raw = ws.receive_text()
        msg = json.loads(raw)
        assert msg["jsonrpc"] == "2.0"
        assert msg["id"] == 1
        assert "session_id" in msg["result"]
        assert msg["result"]["client"] == "godot"
