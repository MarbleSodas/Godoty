
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from agents.multi_agent_manager import MultiAgentManager
from agents.execution_models import StreamEvent

@pytest.mark.asyncio
async def test_suppress_input_stream_error_with_plan():
    """
    Test that 'Error in input stream' is suppressed when a plan has been submitted,
    and that execution continues.
    """
    # Mock dependencies
    with patch('agents.multi_agent_manager.get_planning_agent') as mock_get_planner, \
         patch('agents.multi_agent_manager.get_executor_agent') as mock_get_executor, \
         patch('database.get_db_manager'):  # Mock DB to avoid errors
        
        mock_planner = AsyncMock()
        mock_get_planner.return_value = mock_planner
        
        mock_executor = AsyncMock()
        mock_get_executor.return_value = mock_executor
        
        # Setup mock planner stream
        # It yields plan text output THEN raises the error
        async def mock_plan_stream(message):
            # 1. Yield plan text with structured format
            plan_text = '''```execution-plan
{
  "title": "Test Plan",
  "description": "Test description",
  "steps": [
    {
      "title": "Step 1",
      "description": "Do something",
      "tool_calls": [],
      "depends_on": []
    }
  ]
}
```'''
            yield {
                "type": "data",
                "data": {"text": plan_text}
            }
            # 2. Yield the error that should be suppressed
            raise Exception("Error in input stream: connection closed")

        mock_planner.plan_stream = mock_plan_stream
        
        # Setup mock executor stream
        async def mock_execute_plan(plan):
            yield StreamEvent(type="execution_started", data={"id": "123"})
            yield StreamEvent(type="execution_completed", data={"status": "success"})
            
        mock_executor.execute_plan = mock_execute_plan

        manager = MultiAgentManager(storage_dir="temp_test_sessions")
        # Bypass create_session to avoid complex mocking of graph builder
        manager._active_graphs["session_1"] = MagicMock()
        
        # Collect events
        events = []
        async for event in manager.process_message_stream("session_1", "test message"):
            events.append(event)
            
        # Assertions
        
        # 1. Check that we got the plan_created event
        plan_created_events = [e for e in events if e["type"] == "plan_created"]
        assert len(plan_created_events) == 1, "Should have received plan_created event"
        
        # 2. Check that we did NOT get the error event
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 0, f"Should NOT have received error event, but got: {error_events}"
        
        # 3. Check that execution continued (we got execution events)
        exec_started = [e for e in events if e["type"] == "execution_started"]
        assert len(exec_started) == 1, "Should have proceeded to execution"

@pytest.mark.asyncio
async def test_propagate_input_stream_error_without_plan():
    """
    Test that 'Error in input stream' is propagated if NO plan was submitted.
    """
    with patch('agents.multi_agent_manager.get_planning_agent') as mock_get_planner, \
         patch('database.get_db_manager'):
        
        mock_planner = AsyncMock()
        mock_get_planner.return_value = mock_planner
        
        async def mock_plan_stream(message):
            # Just raise error immediately without submitting plan
            raise Exception("Error in input stream: connection closed")
            yield {} # unreachable

        mock_planner.plan_stream = mock_plan_stream
        
        manager = MultiAgentManager(storage_dir="temp_test_sessions")
        manager._active_graphs["session_2"] = MagicMock()
        
        events = []
        async for event in manager.process_message_stream("session_2", "test message"):
            events.append(event)
            
        # Should have the error
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "Error in input stream" in error_events[0]["data"]["message"]
