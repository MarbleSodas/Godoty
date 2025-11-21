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
        mock_agent = MagicMock()
        mock_agent.state.get.return_value = {}
        planner_instance.agent = mock_agent
        
        async def mock_plan_stream(message):
            # Yield normal text
            yield {"type": "data", "data": {"text": "Thinking..."}}
            
            # Yield plan submission
            yield {
                "type": "tool_use",
                "data": {
                    "tool_name": "submit_execution_plan",
                    "tool_input": {
                        "title": "Test Plan",
                        "description": "A test plan",
                        "steps": [
                            {
                                "title": "Step 1",
                                "description": "Do something",
                                "tool_calls": [{"name": "test_tool", "parameters": {"arg": "val"}}]
                            }
                        ]
                    }
                }
            }
            
            yield {"type": "data", "data": {"text": "Plan submitted."}}
            
        planner_instance.plan_stream = mock_plan_stream
        mock_planner.return_value = planner_instance
        
        # Mock Executor Agent
        executor_instance = MagicMock()
        
        async def mock_execute_plan(plan):
            yield StreamEvent(
                type="execution_started",
                data={"plan_id": plan.id},
                timestamp=datetime.now()
            )
            yield StreamEvent(
                type="step_started",
                data={"step_id": plan.steps[0].id, "title": plan.steps[0].title},
                timestamp=datetime.now()
            )
            yield StreamEvent(
                type="execution_completed",
                data={"plan_id": plan.id, "status": "completed"},
                timestamp=datetime.now()
            )
            
        executor_instance.execute_plan = mock_execute_plan
        mock_executor.return_value = executor_instance
        
        yield mock_planner, mock_executor

@pytest.mark.asyncio
async def test_process_message_stream_orchestration(temp_storage_dir, mock_agents_streaming):
    manager = MultiAgentManager(storage_dir=temp_storage_dir)
    session_id = "test_session"
    
    # Create session to ensure it exists in active graphs
    # We need to mock create_session or ensure it works with mocked agents
    # Since we mocked get_planning_agent, create_session should work fine
    manager.create_session(session_id)
    
    events = []
    async for event in manager.process_message_stream(session_id, "do it"):
        events.append(event)
        
    # Verify events
    types = [e["type"] for e in events]
    print(f"Event types received: {types}")
    
    assert "data" in types
    assert "tool_use" in types
    assert "plan_created" in types
    assert "execution_started" in types
    assert "step_started" in types
    assert "execution_completed" in types
    
    # Verify plan creation event data
    plan_event = next(e for e in events if e["type"] == "plan_created")
    assert plan_event["data"]["title"] == "Test Plan"
    assert plan_event["data"]["steps"] == 1
