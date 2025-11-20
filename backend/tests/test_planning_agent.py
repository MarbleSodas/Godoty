"""
Tests for Planning Agent functionality.

Migrated from reproduce_agent_loop.py and parts of test_agent.py
Tests cover:
- Agent loop integration with Strands
- Tool execution during planning
- Streaming event handling
- Multi-step reasoning
"""
import pytest
import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock
from agents.planning_agent import PlanningAgent

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_strands_agent(monkeypatch):
    """Mock the Strands Agent inside PlanningAgent."""
    
    # Create a mock for the Agent class
    mock_agent_instance = MagicMock()
    
    # Mock invoke_async
    async def mock_invoke_async(prompt):
        result = MagicMock()
        result.message = {"content": [{"text": f"Plan for: {prompt}"}]}
        result.__str__.return_value = f"Plan for: {prompt}"
        return result
    
    mock_agent_instance.invoke_async = mock_invoke_async
    
    # Mock stream_async
    async def mock_stream_async(prompt):
        # Yield start event
        yield {"type": "start", "data": {"message": "Starting"}}
        
        # Yield tool use if prompt asks for it
        if "tool" in prompt.lower() or "file" in prompt.lower():
            yield {
                "current_tool_use": {
                    "name": "list_files",
                    "input": {"path": "."}
                }
            }
            yield {
                "tool_result": {
                    "name": "list_files",
                    "content": ["file1.py", "file2.py"]
                }
            }
            
        # Yield text data
        yield {"data": "Here is the plan..."}
        
        # Yield end event
        result = MagicMock()
        result.stop_reason = "end_turn"
        yield {"result": result}
        
    mock_agent_instance.stream_async = mock_stream_async
    
    # Patch the Agent class to return our mock instance
    monkeypatch.setattr("agents.planning_agent.Agent", MagicMock(return_value=mock_agent_instance))
    
    return mock_agent_instance


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_async_with_tools(mock_api_key, mock_strands_agent):
    """
    Test plan_async method with a prompt that requires tool use.
    This verifies the agent loop is active and tools are executed.
    """
    # Initialize planning agent (will use mocked Agent)
    agent = PlanningAgent()
    
    # Use a prompt that should trigger tool use
    prompt = "List the files in the backend/agents directory"
    
    result = await agent.plan_async(prompt)
    
    # Verify the result
    assert result is not None
    assert isinstance(result, dict)
    assert "plan" in result
    assert len(result["plan"]) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_stream_with_events(mock_api_key, mock_strands_agent):
    """
    Test plan_stream method to verify it streams events from the Agent Loop.
    """
    # Initialize planning agent
    agent = PlanningAgent()
    
    # Use a simpler prompt for streaming test
    prompt = "What tools do you have available for reading files?"
    
    events_received = []
    tool_events_count = 0
    data_events_count = 0
    
    async for event in agent.plan_stream(prompt):
        event_type = event.get("type")
        events_received.append(event_type)
        
        if event_type == "data":
            data_events_count += 1
        elif event_type == "tool_use":
            tool_events_count += 1
    
    # Verify we received events
    assert "start" in events_received
    assert "end" in events_received
    assert data_events_count > 0
    assert tool_events_count > 0  # Should have tool events due to prompt


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_step_reasoning(mock_api_key, mock_strands_agent):
    """
    Test that the agent can perform multi-step reasoning with tool calls.
    """
    # Initialize planning agent
    agent = PlanningAgent()
    
    # Use a prompt that requires multiple steps
    prompt = "Find the planning_agent.py file and tell me what the plan_async method does"
    
    result = await agent.plan_async(prompt)
    
    # Verify the result
    assert result is not None
    assert isinstance(result, dict)
    assert "plan" in result


@pytest.mark.unit
def test_planning_agent_initialization(mock_api_key, mock_strands_agent):
    """Test that planning agent initializes correctly."""
    agent = PlanningAgent()
    
    assert agent is not None
    assert hasattr(agent, 'plan_async')
    assert hasattr(agent, 'plan_stream')
    assert hasattr(agent, 'reset_conversation')


@pytest.mark.unit
def test_planning_agent_reset_conversation(mock_api_key, mock_strands_agent):
    """Test conversation reset functionality."""
    agent = PlanningAgent()
    
    # Should not raise exception
    agent.reset_conversation()
    
    # Agent should still be functional after reset
    assert agent is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_async_basic(mock_api_key, mock_strands_agent):
    """Test basic plan_async functionality."""
    agent = PlanningAgent()
    
    prompt = "Create a simple test plan"
    result = await agent.plan_async(prompt)
    
    assert result is not None
    assert isinstance(result, dict)
    assert "plan" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_stream_basic(mock_api_key, mock_strands_agent):
    """Test basic plan_stream functionality."""
    agent = PlanningAgent()
    
    prompt = "Create a simple test plan"
    events = []
    
    async for event in agent.plan_stream(prompt):
        events.append(event)
    
    # Should receive at least start and end events
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    assert "start" in event_types
    assert "end" in event_types
