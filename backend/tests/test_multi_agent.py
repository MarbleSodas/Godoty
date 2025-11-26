"""
Tests for Multi-Agent Session Management.
"""

import pytest
import os
import shutil
from unittest.mock import MagicMock, patch
from agents.multi_agent_manager import MultiAgentManager

from strands import Agent

class MockAgent(Agent):
    """Mock agent for testing."""
    state = None
    _session_manager = None
    _interrupt_state = None
    messages = []

@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory."""
    dir_path = "temp_test_sessions"
    os.makedirs(dir_path, exist_ok=True)
    yield dir_path
    # Cleanup
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)

@pytest.fixture
def mock_agents():
    """Mock planning and executor agents."""
    with patch('agents.multi_agent_manager.get_planning_agent') as mock_planner, \
         patch('agents.multi_agent_manager.get_executor_agent') as mock_executor:
        
        # Setup mock agents
        planner_instance = MagicMock()
        # Create a mock agent that passes isinstance(obj, Agent) check
        mock_agent = MagicMock(spec=MockAgent)
        mock_agent.state.get.return_value = {} 
        mock_agent._session_manager = None  # Explicitly set to None
        
        # Configure stream_async to yield a result
        async def mock_stream_async(*args, **kwargs):
            result_mock = MagicMock()
            result_mock.stop_reason = "end_turn"
            result_mock.metrics = MagicMock()
            result_mock.metrics.accumulated_usage = {"inputTokens": 10, "outputTokens": 20, "totalTokens": 30}
            result_mock.metrics.accumulated_metrics = {"latencyMs": 100}
            result_mock.to_dict.return_value = {
                "stop_reason": "end_turn",
                "message": "test response",
                "metrics": {}
            }
            result_mock.__str__.return_value = "Agent response"
            yield {"result": result_mock}
            
        mock_agent.stream_async = mock_stream_async
        
        planner_instance.agent = mock_agent
        
        mock_planner.return_value = planner_instance
        
        executor_instance = MagicMock()
        executor_mock_agent = MagicMock(spec=MockAgent)
        executor_mock_agent.state.get.return_value = {}
        executor_mock_agent._session_manager = None
        executor_mock_agent.stream_async = mock_stream_async
        executor_instance.agent = executor_mock_agent
        
        mock_executor.return_value = executor_instance
        
        yield mock_planner, mock_executor

@pytest.mark.asyncio
async def test_create_session(temp_storage_dir, mock_agents):
    """Test session creation."""
    manager = MultiAgentManager(storage_dir=temp_storage_dir)
    session_id = "test_session_1"
    
    # Create session
    result_id = manager.create_session(session_id)
    
    assert result_id == session_id
    assert session_id in manager._active_graphs
    
    # Check if session file would be created (it's created by FileSessionManager on save, 
    # but we just initialized it. It might not exist yet until used.)
    # However, we can check if the session is in the manager.

@pytest.mark.asyncio
async def test_session_persistence(temp_storage_dir, mock_agents):
    """Test session persistence (simulated)."""
    manager = MultiAgentManager(storage_dir=temp_storage_dir)
    session_id = "test_session_persist"
    
    # Create session
    manager.create_session(session_id)
    
    # Simulate saving by creating a dummy file (since we mock the graph execution)
    with open(os.path.join(temp_storage_dir, f"{session_id}.json"), 'w') as f:
        f.write("{}")
    
    # Create new manager instance
    new_manager = MultiAgentManager(storage_dir=temp_storage_dir)
    
    # List sessions
    sessions = new_manager.list_sessions()
    assert len(sessions) == 1
    assert sessions[session_id]['session_id'] == session_id
    
    # Get session
    session = new_manager.get_session(session_id)
    assert session is not None
    assert session['session_id'] == session_id

@pytest.mark.asyncio
async def test_delete_session(temp_storage_dir, mock_agents):
    """Test session deletion."""
    manager = MultiAgentManager(storage_dir=temp_storage_dir)
    session_id = "test_session_delete"
    
    # Create session and dummy file
    manager.create_session(session_id)
    with open(os.path.join(temp_storage_dir, f"{session_id}.json"), 'w') as f:
        f.write("{}")
        
    # Delete session
    success = manager.delete_session(session_id)
    assert success is True
    
    # Verify deletion
    assert not os.path.exists(os.path.join(temp_storage_dir, f"{session_id}.json"))
    assert session_id not in manager._active_graphs

@pytest.mark.asyncio
async def test_process_message(temp_storage_dir, mock_agents):
    """Test message processing."""
    manager = MultiAgentManager(storage_dir=temp_storage_dir)
    session_id = "test_session_chat"
    
    manager.create_session(session_id)
    
    # Update mock_agents stream_async to yield a text event
    _, mock_executor = mock_agents
    executor_instance = mock_executor.return_value
    
    async def mock_text_stream(*args, **kwargs):
        yield {
            "contentBlockDelta": {
                "delta": {"text": "Agent response"}
            }
        }
        yield {"result": MagicMock(stop_reason="end_turn")}

    executor_instance.agent.stream_async = mock_text_stream
    
    # Process message
    response = await manager.process_message(session_id, "Hello", mode="fast")

    assert response == "Agent response"


@pytest.mark.asyncio
async def test_session_manager_sharing(temp_storage_dir, mock_agents):
    """Test that planning and executor graphs share the same session manager."""
    manager = MultiAgentManager(storage_dir=temp_storage_dir)
    session_id = "test_shared_session"

    # Create session
    manager.create_session(session_id)

    # Verify session manager is shared
    graphs = manager._active_graphs[session_id]

    # Both graphs should exist
    assert "planning" in graphs
    assert "executor" in graphs

    # Shared session reference should be stored
    assert "shared_session" in graphs
    assert graphs["shared_session"] is not None

    # Verify the session manager was set for both graphs
    # (This is a structural test - the actual session manager object is created by Strands)
