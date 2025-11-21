import pytest
import asyncio
from unittest.mock import MagicMock, patch
from agents.multi_agent_manager import MultiAgentManager
from agents.execution_models import ExecutionPlan

class MockAgent:
    """Mock agent for testing."""
    def __init__(self):
        self.state = MagicMock()
        self.state.get.return_value = {}
        self._session_manager = None

    async def stream_async(self, prompt):
        """Simulate streaming events including a tool call."""
        # 1. Yield start event
        yield {"type": "start", "data": {"message": "Starting..."}}
        
        # 2. Yield tool use event for submit_execution_plan
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
                            "tool_calls": [
                                {"name": "create_node", "parameters": {"type": "Node2D"}}
                            ]
                        }
                    ]
                }
            }
        }
        
        # 3. Yield tool result (simulated)
        yield {
            "type": "tool_result",
            "data": {
                "tool_name": "submit_execution_plan",
                "result": "Plan submitted."
            }
        }
        
        # 4. Yield end event
        yield {"type": "end", "data": {"stop_reason": "end_turn"}}

    async def execute_plan(self, plan: ExecutionPlan):
        """Simulate executing a plan."""
        yield MagicMock(type="step_started", data={"step": "Step 1"}, timestamp=MagicMock(isoformat=lambda: "2023-01-01T00:00:00"))
        yield MagicMock(type="tool_started", data={"tool": "create_node"}, timestamp=MagicMock(isoformat=lambda: "2023-01-01T00:00:00"))
        yield MagicMock(type="tool_completed", data={"result": "Node created"}, timestamp=MagicMock(isoformat=lambda: "2023-01-01T00:00:00"))
        yield MagicMock(type="step_completed", data={"step": "Step 1"}, timestamp=MagicMock(isoformat=lambda: "2023-01-01T00:00:00"))

@pytest.fixture
def mock_manager_deps():
    with patch('agents.multi_agent_manager.get_planning_agent') as mock_planner, \
         patch('agents.multi_agent_manager.get_executor_agent') as mock_executor:
        
        # Setup Planner Mock
        planner = MagicMock()
        
        # Mock the internal Strands agent
        mock_strands_agent = MagicMock()
        mock_strands_agent.state.get.return_value = {}  # Must be JSON serializable
        planner.agent = mock_strands_agent
        
        # Mock the plan_stream method
        planner.plan_stream = MockAgent().stream_async
        mock_planner.return_value = planner
        
        # Setup Executor Mock
        executor = MagicMock()
        executor.execute_plan = MockAgent().execute_plan
        mock_executor.return_value = executor
        
        yield mock_planner, mock_executor

@pytest.mark.asyncio
async def test_workflow_transition(mock_manager_deps):
    """Verify that MultiAgentManager detects plan submission and triggers execution."""
    manager = MultiAgentManager(storage_dir="temp_test_sessions_workflow")
    session_id = "test_workflow_session"
    manager.create_session(session_id)
    
    events = []
    async for event in manager.process_message_stream(session_id, "Make a plan"):
        events.append(event)
        
    # Check if we got the plan_created event
    plan_created_events = [e for e in events if e.get("type") == "plan_created"]
    assert len(plan_created_events) == 1
    assert plan_created_events[0]["data"]["title"] == "Test Plan"
    
    # Check if we got execution events (from executor agent)
    step_started_events = [e for e in events if e.get("type") == "step_started"]
    assert len(step_started_events) > 0
    
    # Clean up
    import shutil
    import os
    if os.path.exists("temp_test_sessions_workflow"):
        shutil.rmtree("temp_test_sessions_workflow")
