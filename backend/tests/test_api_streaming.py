import pytest
from fastapi.testclient import TestClient
from main import create_app
import json

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_chat_stream_endpoint(client):
    """Test the chat streaming endpoint."""
    try:
        # 1. Create a session
        session_id = "test_session_stream"
        response = client.post("/api/agent/sessions", json={"session_id": session_id})
        assert response.status_code == 200
        
        # 2. Send a message and stream response
        message = "Hello, are you there?"
        
        # Use stream=True for streaming response
        with client.stream("POST", f"/api/agent/sessions/{session_id}/chat/stream", json={"message": message}) as response:
            assert response.status_code == 200
            
            # Check headers
            print(f"Headers: {response.headers}")
            assert response.headers["content-type"].startswith("text/event-stream")
            
            # Read events
            events = []
            for line in response.iter_lines():
                if line:
                    if isinstance(line, bytes):
                        decoded_line = line.decode('utf-8')
                    else:
                        decoded_line = line
                    print(f"Line: {decoded_line}")
                    if decoded_line.startswith("event: "):
                        event_type = decoded_line[7:]
                        events.append(event_type)
                    elif decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str:
                            try:
                                data = json.loads(data_str)
                                # Basic validation of data structure
                                if isinstance(data, dict) and "text" in data:
                                    assert isinstance(data["text"], str)
                            except json.JSONDecodeError:
                                pass

            # Verify we got some events
            assert len(events) > 0
            assert "data" in events
            assert "done" in events
            
    except Exception:
        import traceback
        with open("test_output.txt", "w") as f:
            traceback.print_exc(file=f)
        raise

def test_godot_status_endpoint(client):
    """Test the Godot status endpoint (via main app structure, but here testing logic if possible)."""
    # Note: This endpoint is part of DesktopApi which is not directly exposed via FastAPI router 
    # but via pywebview. However, we can test the logic if we could access it.
    # Since DesktopApi is not a FastAPI route, we can't test it with TestClient directly 
    # unless we exposed it. 
    # But we can verify the import and class existence in main.py
    from main import DesktopApi
    api = DesktopApi()
    status = api.get_godot_status()
    assert "connected" in status
    assert "project_path" in status
