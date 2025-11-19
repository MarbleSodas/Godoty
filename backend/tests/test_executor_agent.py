"""
Tests for Executor Agent functionality.

Migrated from test_executor.py
Tests cover:
- Executor agent initialization
- Plan execution with structured data
- Model fallback support
- Execute_with_fallback method
"""
import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock

from agents.executor_agent import ExecutorAgent, get_executor_agent
from agents.execution_models import ExecutionPlan, ExecutionStep, ToolCall
from agents.config import AgentConfig


@pytest.fixture
def sample_execution_plan():
    """Create a sample execution plan for testing."""
    step1 = ExecutionStep(
        id="create_player_script",
        title="Create Player Script",
        description="Create a GDScript for the player",
        tool_calls=[
            ToolCall(
                name="write_file",
                parameters={
                    "file_path": "player.gd",
                    "content": """
extends CharacterBody2D

func _ready():
    print("Player created!")

func _physics_process(delta):
    # Basic movement
    pass
"""
                }
            )
        ]
    )
    
    step2 = ExecutionStep(
        id="create_enemy_script",
        title="Create Enemy Script",
        description="Create a GDScript for an enemy",
        tool_calls=[
            ToolCall(
                name="write_file",
                parameters={
                    "file_path": "enemy.gd",
                    "content": """
extends CharacterBody2D

func _ready():
    print("Enemy created!")

func _physics_process(delta):
    # Basic enemy AI
    pass
"""
                }
            )
        ],
        depends_on=["create_player_script"]
    )
    
    plan = ExecutionPlan(
        title="Create Game Scripts",
        description="Create GDScript files for game entities",
        steps=[step1, step2]
    )
    
    return plan


@pytest.mark.unit
def test_executor_agent_initialization():
    """Test that executor agent initializes correctly."""
    agent = ExecutorAgent()
    
    assert agent is not None
    assert hasattr(agent, 'execute_plan')
    assert hasattr(agent, 'execution_engine')


@pytest.mark.unit
def test_get_executor_agent_singleton():
    """Test that get_executor_agent returns singleton."""
    agent1 = get_executor_agent()
    agent2 = get_executor_agent()
    
    assert agent1 is agent2


@pytest.mark.unit
def test_plan_parsing():
    """Test parsing JSON to ExecutionPlan."""
    plan_data = {
        "title": "Create Enemy",
        "description": "Create a simple enemy character",
        "steps": [
            {
                "title": "Create Enemy Node",
                "description": "Create enemy CharacterBody2D",
                "tool_calls": [
                    {
                        "name": "create_node",
                        "parameters": {
                            "node_type": "CharacterBody2D",
                            "parent_path": "Root",
                            "node_name": "Enemy"
                        }
                    }
                ]
            }
        ]
    }
    
    plan = ExecutionPlan(**plan_data)
    
    assert plan.title == "Create Enemy"
    assert len(plan.steps) == 1
    assert plan.steps[0].title == "Create Enemy Node"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_plan_basic(sample_execution_plan):
    """Test basic plan execution."""
    agent = ExecutorAgent()
    
    events = []
    async for event in agent.execute_plan(sample_execution_plan):
        events.append(event)
    
    # Should receive some events
    assert len(events) > 0
    event_types = [e.type for e in events]
    assert len(event_types) > 0


@pytest.mark.unit
def test_model_configuration():
    """Test model configuration for executor agent."""
    assert AgentConfig.DEFAULT_EXECUTOR_MODEL is not None
    assert AgentConfig.EXECUTOR_FALLBACK_MODEL is not None
    
    # Agent should initialize with configuration
    agent = get_executor_agent()
    assert agent is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_with_fallback_primary_success():
    """Test execute_with_fallback with primary model success."""
    agent = get_executor_agent()
    
    # Save original model
    original_model = agent.model
    
    try:
        # Mock primary model
        mock_primary = AsyncMock()
        mock_primary.complete.return_value = {
            "message": {"content": [{"text": "Primary success"}]}
        }
        
        agent.model = mock_primary
        agent.fallback_model = None
        
        messages = [{"role": "user", "content": "test"}]
        result = await agent.execute_with_fallback(messages)
        
        assert result["message"]["content"][0]["text"] == "Primary success"
        mock_primary.complete.assert_called_once()
        
    finally:
        agent.model = original_model


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_with_fallback_fallback_used():
    """Test execute_with_fallback when primary fails and fallback is used."""
    agent = get_executor_agent()
    
    # Save original models
    original_model = agent.model
    original_fallback = agent.fallback_model
    
    try:
        # Mock primary to fail
        mock_primary = AsyncMock()
        mock_primary.complete.side_effect = Exception("Primary failed")
        
        # Mock fallback to succeed
        mock_fallback = AsyncMock()
        mock_fallback.complete.return_value = {
            "message": {"content": [{"text": "Fallback success"}]}
        }
        
        agent.model = mock_primary
        agent.fallback_model = mock_fallback
        
        messages = [{"role": "user", "content": "test"}]
        result = await agent.execute_with_fallback(messages)
        
        assert result["message"]["content"][0]["text"] == "Fallback success"
        mock_primary.complete.assert_called_once()
        mock_fallback.complete.assert_called_once()
        
    finally:
        agent.model = original_model
        agent.fallback_model = original_fallback


@pytest.mark.unit
def test_execution_status():
    """Test getting execution status."""
    agent = get_executor_agent()
    
    # Non-existent execution should return None
    status = agent.get_execution_status("non_existent_id")
    assert status is None


@pytest.mark.unit
def test_list_active_executions():
    """Test listing active executions."""
    agent = get_executor_agent()
    
    # Should return a list (even if empty)
    executions = agent.list_active_executions()
    assert isinstance(executions, list)
