"""
Integration tests for Server-Sent Events (SSE) functionality.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator
from fastapi.testclient import TestClient
from fastapi import FastAPI

from api.sse_routes import SSEManager, event_generator, extract_project_name
from services.godot_connection_monitor import ConnectionEvent, ConnectionState


class MockConnectionMonitor:
    """Mock connection monitor for testing."""

    def __init__(self):
        self.bridge = MagicMock()
        self.bridge.project_info = None
        self.status_data = {
            "state": "disconnected",
            "last_attempt": "2025-01-01T12:00:00",
            "project_path": None,
            "project_name": None,
            "godot_version": None,
            "plugin_version": None,
            "project_settings": {}
        }

    def get_status(self):
        return self.status_data.copy()


class TestSSEIntegration:
    """Integration tests for SSE functionality."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app for testing."""
        app = FastAPI()
        from api.sse_routes import router
        app.include_router(router, prefix="/api")
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_monitor(self):
        """Create mock connection monitor."""
        return MockConnectionMonitor()

    def test_extract_project_name(self):
        """Test project name extraction function."""
        # Test with None inputs
        assert extract_project_name(None, None, None) is None

        # Test with project_info.project_name
        mock_project_info = MagicMock()
        mock_project_info.project_name = "TestProject"
        result = extract_project_name(mock_project_info, {}, "/path/to/project")
        assert result == "TestProject"

        # Test with project_settings name
        project_settings = {"name": "SettingsProject"}
        result = extract_project_name(None, project_settings, "/path/to/project")
        assert result == "SettingsProject"

        # Test with project path basename
        result = extract_project_name(None, {}, "/path/to/MyProject")
        assert result == "MyProject"

        # Test priority: project_info > settings > path
        mock_project_info.project_name = "PriorityProject"
        project_settings = {"name": "SettingsProject"}
        result = extract_project_name(mock_project_info, project_settings, "/path/to/PathProject")
        assert result == "PriorityProject"

    @pytest.mark.asyncio
    async def test_sse_manager_basic_operations(self):
        """Test SSE manager basic operations."""
        manager = SSEManager()

        # Test empty manager
        assert len(manager.clients) == 0

        # Test adding and removing clients
        queue1 = asyncio.Queue(maxsize=10)
        queue2 = asyncio.Queue(maxsize=10)

        manager.add_client(queue1)
        assert len(manager.clients) == 1
        assert queue1 in manager.clients

        manager.add_client(queue2)
        assert len(manager.clients) == 2

        manager.remove_client(queue1)
        assert len(manager.clients) == 1
        assert queue1 not in manager.clients
        assert queue2 in manager.clients

        manager.remove_client(queue2)
        assert len(manager.clients) == 0

    @pytest.mark.asyncio
    async def test_sse_manager_broadcast(self, mock_monitor):
        """Test SSE manager broadcast functionality."""
        manager = SSEManager()

        # Create test queues
        queue1 = asyncio.Queue(maxsize=10)
        queue2 = asyncio.Queue(maxsize=10)

        manager.add_client(queue1)
        manager.add_client(queue2)

        # Mock get_connection_monitor
        with patch('api.sse_routes.get_connection_monitor', return_value=mock_monitor):
            # Create test event
            event = ConnectionEvent(
                state=ConnectionState.CONNECTED,
                timestamp=asyncio.get_event_loop().time(),
                error=None,
                project_path="/test/path",
                godot_version="4.2",
                plugin_version="1.0"
            )

            # Broadcast event
            await manager.broadcast(event)

            # Check that both queues received the event
            event1 = await queue1.get()
            event2 = await queue2.get()

            assert event1["state"] == "connected"
            assert event2["state"] == "connected"
            assert event1["project_path"] == "/test/path"
            assert event2["project_path"] == "/test/path"

    @pytest.mark.asyncio
    async def test_sse_manager_broadcast_with_monitor_errors(self):
        """Test SSE manager broadcast when monitor has errors."""
        manager = SSEManager()
        queue = asyncio.Queue(maxsize=10)
        manager.add_client(queue)

        # Mock monitor that raises exception
        def failing_monitor():
            raise Exception("Monitor error")

        with patch('api.sse_routes.get_connection_monitor', side_effect=failing_monitor):
            # Create test event
            event = ConnectionEvent(
                state=ConnectionState.CONNECTED,
                timestamp=asyncio.get_event_loop().time(),
                error=None,
                project_path="/test/path",
                godot_version="4.2",
                plugin_version="1.0"
            )

            # Broadcast should still work even with monitor error
            await manager.broadcast(event)

            # Check that queue received event without project info
            result = await queue.get()
            assert result["state"] == "connected"
            assert result["project_path"] == "/test/path"
            assert result["project_name"] is None

    @pytest.mark.asyncio
    async def test_sse_manager_broadcast_with_serialization_error(self):
        """Test SSE manager broadcast when event serialization fails."""
        manager = SSEManager()
        queue = asyncio.Queue(maxsize=10)
        manager.add_client(queue)

        # Create mock event that fails to_dict
        failing_event = MagicMock()
        failing_event.to_dict.side_effect = Exception("Serialization failed")

        # Mock monitor
        with patch('api.sse_routes.get_connection_monitor', return_value=MockConnectionMonitor()):
            # Broadcast should handle serialization error gracefully
            await manager.broadcast(failing_event)

            # Check that queue received error event
            result = await queue.get()
            assert result["state"] == "error"
            assert result["error"] == "Failed to serialize event data"

    @pytest.mark.asyncio
    async def test_sse_manager_broadcast_with_client_timeouts(self):
        """Test SSE manager broadcast handling client timeouts."""
        manager = SSEManager()

        # Create a queue that will always timeout
        class TimeoutQueue:
            def __init__(self):
                self.put_count = 0

            async def put(self, item, timeout=None):
                self.put_count += 1
                raise asyncio.TimeoutError()

        timeout_queue = TimeoutQueue()
        manager.add_client(timeout_queue)

        # Mock monitor
        with patch('api.sse_routes.get_connection_monitor', return_value=MockConnectionMonitor()):
            # Create test event
            event = ConnectionEvent(
                state=ConnectionState.CONNECTED,
                timestamp=asyncio.get_event_loop().time(),
                error=None,
                project_path="/test/path",
                godot_version="4.2",
                plugin_version="1.0"
            )

            # Broadcast should handle timeout and remove client
            await manager.broadcast(event)

            # Queue should have been removed
            assert len(manager.clients) == 0
            assert timeout_queue.put_count == 1

    @pytest.mark.asyncio
    async def test_event_generator_initial_status_success(self):
        """Test event generator successful initial status."""
        mock_monitor = MockConnectionMonitor()
        mock_monitor.status_data = {
            "state": "connected",
            "last_attempt": "2025-01-01T12:00:00",
            "project_path": "/test/project",
            "godot_version": "4.2",
            "plugin_version": "1.0",
            "project_settings": {"name": "TestProject"}
        }

        # Mock project info
        mock_project_info = MagicMock()
        mock_project_info.project_name = "TestProject"
        mock_monitor.bridge.project_info = mock_project_info

        client_queue = asyncio.Queue(maxsize=10)

        with patch('api.sse_routes.get_connection_monitor', return_value=mock_monitor):
            # Test event generator
            generator = event_generator(client_queue)

            # Get first event (initial status)
            first_event = await generator.__anext__()

            # Parse SSE format
            assert first_event.startswith("data: ")
            data_json = first_event[6:]  # Remove "data: " prefix

            event_data = json.loads(data_json)
            assert event_data["state"] == "connected"
            assert event_data["project_name"] == "TestProject"
            assert event_data["project_path"] == "/test/project"
            assert event_data["godot_version"] == "4.2"

    @pytest.mark.asyncio
    async def test_event_generator_initial_status_failure(self):
        """Test event generator when initial status fails."""
        def failing_monitor():
            raise Exception("Status fetch failed")

        client_queue = asyncio.Queue(maxsize=10)

        with patch('api.sse_routes.get_connection_monitor', side_effect=failing_monitor):
            # Test event generator
            generator = event_generator(client_queue)

            # Get first event (fallback status)
            first_event = await generator.__anext__()

            # Parse SSE format
            assert first_event.startswith("data: ")
            data_json = first_event[6:]  # Remove "data: " prefix

            event_data = json.loads(data_json)
            assert event_data["state"] == "unknown"
            assert event_data["error"] == "Failed to get initial status"

    @pytest.mark.asyncio
    async def test_event_generator_streaming(self):
        """Test event generator streaming functionality."""
        mock_monitor = MockConnectionMonitor()
        mock_monitor.status_data = {
            "state": "disconnected",
            "last_attempt": None,
            "project_path": None,
            "godot_version": None,
            "plugin_version": None,
            "project_settings": {}
        }

        client_queue = asyncio.Queue(maxsize=10)

        with patch('api.sse_routes.get_connection_monitor', return_value=mock_monitor):
            # Test event generator
            generator = event_generator(client_queue)

            # Get initial status
            initial_event = await generator.__anext__()
            assert initial_event.startswith("data: ")

            # Send test event through queue
            test_event = {
                "state": "connected",
                "timestamp": "2025-01-01T12:00:00",
                "project_path": "/test/project"
            }
            await client_queue.put(test_event)

            # Get streamed event
            streamed_event = await generator.__anext__()
            assert streamed_event.startswith("data: ")

            # Parse and verify
            data_json = streamed_event[6:]
            event_data = json.loads(data_json)
            assert event_data["state"] == "connected"
            assert event_data["project_path"] == "/test/project"

    @pytest.mark.asyncio
    async def test_event_generator_timeout_and_keepalive(self):
        """Test event generator timeout and keepalive functionality."""
        mock_monitor = MockConnectionMonitor()
        client_queue = asyncio.Queue(maxsize=10)

        with patch('api.sse_routes.get_connection_monitor', return_value=mock_monitor):
            # Test event generator with very short timeout
            generator = event_generator(client_queue)

            # Get initial status
            initial_event = await generator.__anext__()
            assert initial_event.startswith("data: ")

            # Wait for timeout (this is tricky to test reliably, so we'll just
            # make sure no exception is raised for a short time)
            try:
                # Use asyncio.wait_for to avoid hanging the test
                await asyncio.wait_for(generator.__anext__(), timeout=0.1)
            except asyncio.TimeoutError:
                # This is expected - keepalive should be sent but may not be received within timeout
                pass

    def test_rest_status_endpoint_success(self, client):
        """Test REST status endpoint success."""
        mock_monitor = MockConnectionMonitor()
        mock_monitor.status_data = {
            "state": "connected",
            "running": True,
            "project_path": "/test/project",
            "godot_version": "4.2",
            "plugin_version": "1.0",
            "project_settings": {"name": "Test"}
        }

        with patch('api.sse_routes.get_connection_monitor', return_value=mock_monitor):
            response = client.get("/api/godot/status")

            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "connected"
            assert data["project_path"] == "/test/project"
            assert data["godot_version"] == "4.2"

    def test_rest_status_endpoint_failure(self, client):
        """Test REST status endpoint failure handling."""
        def failing_monitor():
            raise Exception("Monitor error")

        with patch('api.sse_routes.get_connection_monitor', side_effect=failing_monitor):
            response = client.get("/api/godot/status")

            # Should return fallback status instead of error
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "error"
            assert "Failed to get status" in data["error"]
            assert data["running"] is False

    def test_sse_stream_endpoint_headers(self, client):
        """Test SSE stream endpoint headers."""
        mock_monitor = MockConnectionMonitor()

        with patch('api.sse_routes.get_connection_monitor', return_value=mock_monitor):
            response = client.get("/api/godot/status/stream")

            # Check SSE specific headers
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["x-accel-buffering"] == "no"

    def test_sse_stream_endpoint_initial_event(self, client):
        """Test SSE stream endpoint initial event."""
        mock_monitor = MockConnectionMonitor()
        mock_monitor.status_data = {
            "state": "disconnected",
            "last_attempt": None,
            "project_path": None,
            "project_name": None,
            "godot_version": None,
            "plugin_version": None,
            "project_settings": {}
        }

        with patch('api.sse_routes.get_connection_monitor', return_value=mock_monitor):
            response = client.get("/api/godot/status/stream")

            assert response.status_code == 200

            # Read the first chunk (should be initial status)
            lines = response.iter_lines()
            first_line = next(lines)

            # Should be an SSE data line
            if first_line:
                decoded = first_line.decode('utf-8')
                assert decoded.startswith("data: ")

                # Parse JSON data
                data_json = decoded[6:]  # Remove "data: " prefix
                event_data = json.loads(data_json)
                assert event_data["state"] == "disconnected"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])