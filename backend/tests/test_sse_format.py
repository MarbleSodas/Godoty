import pytest
import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from main import create_app

app = create_app()

@pytest.mark.asyncio
async def test_chat_session_stream_sse_format():
    """Test that chat session stream returns SSE events with 'type' in the data payload."""
    
    # Mock MultiAgentManager
    mock_manager = MagicMock()
    mock_manager.get_session.return_value = {"id": "test_session"}
    
    # Mock process_message_stream to yield events
    async def mock_stream(session_id, message):
        yield {"type": "tool_use", "data": {"tool_name": "test_tool", "tool_input": {}}}
        yield {"type": "data", "data": {"text": "Hello"}}
    
    mock_manager.process_message_stream = mock_stream
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("agents.multi_agent_manager.get_multi_agent_manager", return_value=mock_manager):
            async with client.stream(
                "POST",
                "/api/agent/sessions/test_session/chat/stream",
                json={"message": "test message"}
            ) as response:
                assert response.status_code == 200
                
                events = []
                async for line in response.aiter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            events.append(data)
                        except json.JSONDecodeError:
                            pass
                
                # Verify events have 'type' field
                assert len(events) >= 2
                
                # Check tool_use event
                tool_event = next((e for e in events if e.get("type") == "tool_use"), None)
                assert tool_event is not None
                assert tool_event["data"]["tool_name"] == "test_tool"
                
                # Check data event
                data_event = next((e for e in events if e.get("type") == "data"), None)
                assert data_event is not None
                assert data_event["data"]["text"] == "Hello"
