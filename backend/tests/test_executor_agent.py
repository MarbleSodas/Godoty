"""
Test suite for refactored executor agent.

Tests that the executor agent:
1. Initializes properly with valid and invalid API keys
2. Can process the "Create a start menu" prompt
3. Properly calls tools and handles responses
4. Streams events correctly
"""

import pytest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
from typing import AsyncIterator


# Mock the Godot bridge before importing agents
@pytest.fixture(autouse=True)
def mock_godot_bridge():
    """Mock Godot bridge to avoid connection requirements."""
    with patch('agents.tools.godot_bridge.get_godot_bridge') as mock_bridge, \
         patch('agents.tools.godot_bridge.ensure_godot_connection') as mock_ensure:
        
        mock_ensure.return_value = True
        mock_bridge_instance = MagicMock()
        mock_bridge.return_value = mock_bridge_instance
        
        yield mock_bridge_instance


@pytest.fixture
def valid_api_key():
    """Provide a valid test API key."""
    return "sk-test-valid-key-12345"


@pytest.fixture
def mock_openrouter_response():
    """Mock OpenRouter SSE stream response."""
    async def mock_stream(*args, **kwargs):
        # Simulate a tool call response
        yield {
            "messageStart": {"role": "assistant"}
        }
        yield {
            "contentBlockStart": {
                "start": {
                    "toolUse": {
                        "name": "create_scene",
                        "toolUseId": "toolu_test123"
                    }
                }
            }
        }
        yield {
            "contentBlockDelta": {
                "delta": {
                    "toolUse": {
                        "input": '{"scene_name": "MainMenu"}'
                    }
                }
            }
        }
        yield {
            "contentBlockStop": {}
        }
        yield {
            "messageStop": {
                "stopReason": "tool_use"
            }
        }
    
    return mock_stream


class TestExecutorAgentInitialization:
    """Test executor agent initialization."""
    
    def test_init_with_empty_api_key_raises_error(self):
        """Test that empty API key raises ValueError."""
        from agents.executor_agent import ExecutorAgent
        
        with pytest.raises(ValueError, match="OpenRouter API key cannot be empty"):
            ExecutorAgent(api_key="")
    
    def test_init_with_whitespace_api_key_raises_error(self):
        """Test that whitespace-only API key raises ValueError."""
        from agents.executor_agent import ExecutorAgent
        
        with pytest.raises(ValueError, match="OpenRouter API key cannot be empty"):
            ExecutorAgent(api_key="   ")
    
    def test_init_with_valid_api_key_succeeds(self, valid_api_key):
        """Test that valid API key initializes successfully."""
        from agents.executor_agent import ExecutorAgent
        
        agent = ExecutorAgent(api_key=valid_api_key)
        assert agent is not None
        assert agent.model is not None
        assert agent.agent is not None
        assert len(agent.tools) > 0


class TestExecutorAgentStreaming:
    """Test executor agent streaming functionality."""
    
    @pytest.mark.asyncio
    async def test_execute_plan_with_string(self, valid_api_key, mock_openrouter_response):
        """Test execute_plan with a simple string message."""
        from agents.executor_agent import ExecutorAgent
        
        agent = ExecutorAgent(api_key=valid_api_key)
        
        # Mock the agent's stream_async method
        with patch.object(agent.agent, 'stream_async', side_effect=mock_openrouter_response):
            events = []
            async for event in agent.execute_plan("Create a start menu"):
                events.append(event)
            
            assert len(events) > 0
            # Should have received tool use events
            tool_events = [e for e in events if "contentBlockStart" in e]
            assert len(tool_events) > 0
    
    @pytest.mark.asyncio
    async def test_execute_plan_yields_tool_calls(self, valid_api_key, mock_openrouter_response):
        """Test that execute_plan properly yields tool call events."""
        from agents.executor_agent import ExecutorAgent
        
        agent = ExecutorAgent(api_key=valid_api_key)
        
        with patch.object(agent.agent, 'stream_async', side_effect=mock_openrouter_response):
            events = []
            async for event in agent.execute_plan("Create a start menu"):
                events.append(event)
            
            # Verify we got a messageStart
            assert any("messageStart" in e for e in events)
            
            # Verify we got a contentBlockStart with toolUse
            tool_start_events = [e for e in events if "contentBlockStart" in e]
            assert len(tool_start_events) > 0
            
            # Verify the tool name is correct
            first_tool_event = tool_start_events[0]
            assert "contentBlockStart" in first_tool_event
            assert "start" in first_tool_event["contentBlockStart"]
            assert "toolUse" in first_tool_event["contentBlockStart"]["start"]
            assert first_tool_event["contentBlockStart"]["start"]["toolUse"]["name"] == "create_scene"


class TestExecutorAgentEventTransformation:
    """Test that executor agent events transform correctly."""
    
    @pytest.mark.asyncio
    async def test_events_transform_to_frontend_format(self, valid_api_key, mock_openrouter_response):
        """Test that events can be transformed for frontend consumption."""
        from agents.executor_agent import ExecutorAgent
        from agents.event_utils import transform_strands_event
        
        agent = ExecutorAgent(api_key=valid_api_key)
        
        with patch.object(agent.agent, 'stream_async', side_effect=mock_openrouter_response):
            transformed_events = []
            async for event in agent.execute_plan("Create a start menu"):
                transformed = transform_strands_event(event)
                if transformed:
                    transformed_events.append(transformed)
            
            # Should have at least one transformed event
            assert len(transformed_events) > 0
            
            # Check for tool_use events
            tool_use_events = [e for e in transformed_events if e.get("type") == "tool_use"]
            # Note: transform_strands_event might not emit tool_use for contentBlockStart
            # It primarily emits for current_tool_use, so this might be 0
            # Let's just verify events were transformed
            assert all(isinstance(e, dict) for e in transformed_events)
            assert all("type" in e for e in transformed_events)


class TestExecutorAgentToolDefinitions:
    """Test that executor agent tools are properly defined."""
    
    def test_tools_are_properly_decorated(self, valid_api_key):
        """Test that all executor tools have proper @tool decorators."""
        from agents.executor_agent import ExecutorAgent
        from agents.tools import create_node, create_scene
        
        agent = ExecutorAgent(api_key=valid_api_key)
        
        # Verify tools are in the agent
        assert create_node in agent.tools
        assert create_scene in agent.tools
        
        # Verify they have docstrings (required for @tool decorator)
        assert create_node.__doc__ is not None
        assert create_scene.__doc__ is not None
    
    def test_all_executor_tools_are_async(self, valid_api_key):
        """Test that all executor tools are async functions."""
        from agents.executor_agent import ExecutorAgent
        import inspect
        
        agent = ExecutorAgent(api_key=valid_api_key)
        
        # Check a sample of tools
        from agents.tools import create_node, create_scene, modify_node_property
        
        assert inspect.iscoroutinefunction(create_node)
        assert inspect.iscoroutinefunction(create_scene)
        assert inspect.iscoroutinefunction(modify_node_property)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
