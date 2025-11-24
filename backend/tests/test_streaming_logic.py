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
        """Simulate streaming events including plan output."""
        # 1. Yield start event
        yield {"type": "start", "data": {"message": "Starting..."}}

        # 2. Yield text data with plan
        plan_text = '''Here's the plan:

```execution-plan
{
  "title": "Test Plan",
  "description": "A test plan",
  "steps": []
}
```'''
        yield {
            "event": {
                "contentBlockDelta": {
                    "delta": {"text": plan_text}
                }
            }
        }

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
async def test_streaming_plan_output(mock_planning_agent):
    """Verify that planning agent outputs plans in structured format."""
    events = []
    async for event in mock_planning_agent.plan_stream("Test prompt"):
        events.append(event)

    # Check if we got data events with plan text
    data_events = [e for e in events if e.get("type") == "data"]
    assert len(data_events) >= 1

    # Verify plan text is present in one of the data events
    all_text = "".join([e["data"].get("text", "") for e in data_events])
    assert "execution-plan" in all_text
    assert "Test Plan" in all_text
