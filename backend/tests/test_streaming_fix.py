import pytest
import asyncio
from unittest.mock import MagicMock, patch
from agents.planning_agent import PlanningAgent

class MockStrandsAgent:
    """Mock Strands agent for testing."""
    def __init__(self):
        self.state = MagicMock()
        self.state.get.return_value = {}

    async def stream_async(self, prompt):
        """Simulate streaming events including a message event with tool calls."""
        # 1. Yield start event
        yield {"type": "start", "data": {"message": "Starting..."}}
        
        # 2. Yield message event with tool calls (simulating the bug scenario)
        tool_call = MagicMock()
        tool_call.name = "submit_execution_plan"
        tool_call.parameters = {"title": "Test Plan", "steps": []}
        
        message = MagicMock()
        message.tool_calls = [tool_call]
        
        yield {"message": message}
        
        # 3. Yield end event
        yield {"result": MagicMock(stop_reason="end_turn")}

@pytest.fixture
def mock_planning_agent():
    with patch('agents.planning_agent.Agent') as MockAgentClass:
        # Setup mock Strands agent
        mock_strands_agent = MockStrandsAgent()
        MockAgentClass.return_value = mock_strands_agent
        
        # Create planning agent
        agent = PlanningAgent(api_key="test", model_id="test")
        # Inject mock agent directly to bypass initialization logic if needed
        agent.agent = mock_strands_agent
        
        yield agent

@pytest.mark.asyncio
async def test_streaming_message_conversion(mock_planning_agent):
    """Verify that message events with tool calls are converted to tool_use events."""
    events = []
    async for event in mock_planning_agent.plan_stream("Test prompt"):
        events.append(event)
        
    # Check if we got the tool_use event extracted from the message
    tool_use_events = [e for e in events if e.get("type") == "tool_use"]
    assert len(tool_use_events) == 1
    assert tool_use_events[0]["data"]["tool_name"] == "submit_execution_plan"
    assert tool_use_events[0]["data"]["tool_input"]["title"] == "Test Plan"
