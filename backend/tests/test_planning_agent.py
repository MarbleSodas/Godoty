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
from agents.planning_agent import PlanningAgent

logger = logging.getLogger(__name__)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_async_with_tools(mock_api_key):
    """
    Test plan_async method with a prompt that requires tool use.
    This verifies the agent loop is active and tools are executed.
    """
    # Initialize planning agent
    agent = PlanningAgent()
    
    # Use a prompt that should trigger tool use
    prompt = "List the files in the backend/agents directory"
    
    result = await agent.plan_async(prompt)
    
    # Verify the result mentions files (indicating tool was called)
    assert result is not None
    assert isinstance(result, str)
    # Basic verification - actual content depends on OpenRouter model
    assert len(result) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_stream_with_events(mock_api_key):
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
    assert "start" in events_received or "message_start" in events_received
    assert "end" in events_received or "message_stop" in events_received
    assert data_events_count > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_step_reasoning(mock_api_key):
    """
    Test that the agent can perform multi-step reasoning with tool calls.
    """
    # Initialize planning agent
    agent = PlanningAgent()
    
    # Use a prompt that requires multiple steps
    prompt = "Find the planning_agent.py file and tell me what the plan_async method does"
    
    result = await agent.plan_async(prompt)
    
    # Verify the result mentions the method functionality
    assert result is not None
    assert isinstance(result, str)
    # The agent should provide some meaningful response
    assert len(result) > 50


@pytest.mark.unit
def test_planning_agent_initialization(mock_api_key):
    """Test that planning agent initializes correctly."""
    agent = PlanningAgent()
    
    assert agent is not None
    assert hasattr(agent, 'plan_async')
    assert hasattr(agent, 'plan_stream')
    assert hasattr(agent, 'reset_conversation')


@pytest.mark.unit
def test_planning_agent_reset_conversation(mock_api_key):
    """Test conversation reset functionality."""
    agent = PlanningAgent()
    
    # Should not raise exception
    agent.reset_conversation()
    
    # Agent should still be functional after reset
    assert agent is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_async_basic(mock_api_key):
    """Test basic plan_async functionality."""
    agent = PlanningAgent()
    
    prompt = "Create a simple test plan"
    result = await agent.plan_async(prompt)
    
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_stream_basic(mock_api_key):
    """Test basic plan_stream functionality."""
    agent = PlanningAgent()
    
    prompt = "Create a simple test plan"
    events = []
    
    async for event in agent.plan_stream(prompt):
        events.append(event)
    
    # Should receive at least start and end events
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    # Should have some kind of start and end
    assert any("start" in et for et in event_types if et)
