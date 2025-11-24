import pytest
import os
import shutil
from unittest.mock import MagicMock, patch, AsyncMock
from agents.multi_agent_manager import MultiAgentManager
from agents.execution_models import StreamEvent
from datetime import datetime

@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory."""
    dir_path = "temp_test_streaming"
    os.makedirs(dir_path, exist_ok=True)
    yield dir_path
    # Cleanup
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)

@pytest.fixture
def mock_agents_streaming():
    with patch('agents.multi_agent_manager.get_planning_agent') as mock_planner, \
         patch('agents.multi_agent_manager.get_executor_agent') as mock_executor:
        
        # Mock Planning Agent
        planner_instance = MagicMock()
        
        # Configure agent.state.get() to return a serializable dict
        mock_planner_agent = MagicMock()
        mock_planner_agent.state.get.return_value = {}
        planner_instance.agent = mock_planner_agent
        
        mock_planner.return_value = planner_instance
        
        # Mock Executor Agent
        executor_instance = MagicMock()
        
        # Configure agent.state.get() to return a serializable dict (FIX FOR ERROR)
        mock_executor_agent = MagicMock()
        mock_executor_agent.state.get.return_value = {}
        executor_instance.agent = mock_executor_agent
        
        mock_executor.return_value = executor_instance
        
        yield mock_planner, mock_executor

@pytest.mark.asyncio
async def test_process_message_stream_orchestration(temp_storage_dir, mock_agents_streaming):
    manager = MultiAgentManager(storage_dir=temp_storage_dir)
    session_id = "test_session"
    
    # Create session (this will use the mock agents)
    manager.create_session(session_id)
    
    # Now replace the real graphs with mock graphs that yield the events we want to test
    # This bypasses the real Graph execution but tests MultiAgentManager's event handling
    
    mock_planning_graph = MagicMock()
    mock_fast_graph = MagicMock()
    
    # Define events for planning graph
    async def mock_planning_stream(message):
        # 1. Node start event
        yield {
            "type": "multi_agent_node_start",
            "data": {"node": "planner"}
        }

        # 2. Streaming text event with analysis (wrapped in multi_agent_node_stream)
        yield {
            "type": "multi_agent_node_stream",
            "data": {
                "node": "planner",
                "event": {
                    "type": "data",
                    "data": {"text": "Analyzing your request...\n\n"}
                }
            }
        }

        # 3. Streaming text event with plan explanation
        yield {
            "type": "multi_agent_node_stream",
            "data": {
                "node": "planner",
                "event": {
                    "type": "data",
                    "data": {"text": "I've created a plan to help you.\n\n"}
                }
            }
        }

        # 4. Streaming text event with execution plan in structured format
        plan_json = '''```execution-plan
{
  "title": "Test Plan",
  "description": "A test plan",
  "steps": [
    {
      "title": "Step 1",
      "description": "Do it",
      "tool_calls": [],
      "depends_on": []
    }
  ]
}
```'''
        yield {
            "type": "multi_agent_node_stream",
            "data": {
                "node": "planner",
                "event": {
                    "type": "data",
                    "data": {"text": plan_json}
                }
            }
        }

        # 5. Node stop event
        yield {
            "type": "multi_agent_node_stop",
            "data": {"node": "planner"}
        }
        
    mock_planning_graph.stream_async = mock_planning_stream
    
    # Define events for executor graph
    async def mock_executor_stream(message):
        # 1. Node start
        yield {
            "type": "multi_agent_node_start",
            "data": {"node": "executor"}
        }
        
        # 2. Execution events (simulating what ExecutorAgent would yield via event_utils)
        # Note: ExecutorAgent now yields transformed events via event_utils if we updated it?
        # Wait, we didn't update ExecutorAgent to use event_utils explicitly in execute_plan?
        # But MultiAgentManager calls fast_graph.stream_async.
        # The fast_graph runs ExecutorAgent.
        # ExecutorAgent.agent is a Strands Agent.
        # So Strands Agent yields raw events.
        # MultiAgentManager transforms them.
        
        # So here we simulate RAW Strands events coming from the graph
        
        # Text delta
        yield {
            "type": "multi_agent_node_stream",
            "data": {
                "node": "executor",
                "event": {
                    "event": {
                        "contentBlockDelta": {
                            "delta": {"text": "Executing step 1..."}
                        }
                    }
                }
            }
        }
        
        # Node stop
        yield {
            "type": "multi_agent_node_stop",
            "data": {"node": "executor"}
        }

    mock_fast_graph.stream_async = mock_executor_stream
    
    # Inject mock graphs
    manager._active_graphs[session_id] = {
        "planning": mock_planning_graph,
        "fast": mock_fast_graph
    }
    
    events = []
    async for event in manager.process_message_stream(session_id, "do it"):
        events.append(event)
        
    # Verify events
    types = [e["type"] for e in events]
    print(f"Event types received: {types}")

    # Check for transformed events
    assert "data" in types, "Should have data events"
    assert "plan_created" in types, "Should have plan_created event"
    assert "execution_started" in types, "Should have execution_started event"
    assert "execution_completed" in types, "Should have execution_completed event"

    # Verify plan creation event data
    plan_event = next(e for e in events if e["type"] == "plan_created")
    assert plan_event["data"]["title"] == "Test Plan"
    assert plan_event["data"]["steps"] == 1

    # Verify text content
    texts = [e["data"]["text"] for e in events if e["type"] == "data" and "text" in e["data"]]
    assert "Analyzing your request..." in texts, "Should have analysis text"
    assert "Executing step 1..." in texts, "Should have execution text"
