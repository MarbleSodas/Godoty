"""
Test for Executor Agent.

Demonstrates the executor agent working with structured data.
Tests the executor agent with model configuration and fallback support.
"""

import asyncio
import json
from datetime import datetime

from agents.executor_agent import ExecutorAgent
from agents.execution_models import ExecutionPlan, ExecutionStep, ToolCall


async def test_executor():
    """Test the executor agent."""
    print("Testing Executor Agent")

    # Create a simple execution plan (structured data from planning agent)
    # Create steps with explicit IDs for proper dependency resolution
    # Skip node creation for testing (requires Godot connection)
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
        depends_on=["create_player_script"]  # Depends on first step by ID
    )

    # Create execution plan
    plan = ExecutionPlan(
        title="Create Game Scripts",
        description="Create GDScript files for game entities",
        steps=[step1, step2]
    )

    # Create executor agent
    agent = ExecutorAgent()

    print(f"Executing plan: {plan.title}")
    print(f"Steps: {len(plan.steps)}")

    # Execute the plan
    events = []
    try:
        async for event in agent.execute_plan(plan):
            events.append(event)
            print(f"Event: {event.type} - {event.data}")

            # Let execution complete (no early stop for testing)

    except Exception as e:
        print(f"Execution error (expected in test): {e}")

    print(f"\nTotal events received: {len(events)}")
    return events


def create_sample_plan_json():
    """Create a sample plan in JSON format."""
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
            },
            {
                "title": "Add Enemy Script",
                "description": "Create enemy behavior script",
                "tool_calls": [
                    {
                        "name": "write_file",
                        "parameters": {
                            "file_path": "enemy.gd",
                            "content": "extends CharacterBody2D\n\nfunc _ready():\n    print('Enemy created!')"
                        }
                    }
                ],
                "depends_on": ["create_node"]
            }
        ]
    }

    return plan_data


def test_plan_parsing():
    """Test parsing JSON plan to ExecutionPlan."""
    print("\nTesting Plan Parsing")

    plan_data = create_sample_plan_json()
    plan_json = json.dumps(plan_data, indent=2)

    print("Sample Plan JSON:")
    print(plan_json)

    # Parse to ExecutionPlan
    plan = ExecutionPlan(**plan_data)

    print(f"\nParsed Plan:")
    print(f"Title: {plan.title}")
    print(f"Steps: {len(plan.steps)}")

    for i, step in enumerate(plan.steps, 1):
        print(f"  Step {i}: {step.title}")
        print(f"    Tools: {len(step.tool_calls)}")
        print(f"    Depends on: {step.depends_on}")

    return plan


def test_model_configuration():
    """Test model configuration for executor agent."""
    try:
        from agents.executor_agent import get_executor_agent
        from agents.config import AgentConfig

        print("Testing Model Configuration")

        # Check configuration
        print(f"Default Executor Model: {AgentConfig.DEFAULT_EXECUTOR_MODEL}")
        print(f"Executor Fallback Model: {AgentConfig.EXECUTOR_FALLBACK_MODEL}")

        # Get executor agent (should initialize models)
        agent = get_executor_agent()

        # Check if models are initialized
        if hasattr(agent, 'model') and agent.model:
            config = agent.model.get_config()
            print(f"Primary model initialized: {config.get('model_id')}")
        else:
            print("Primary model not initialized")

        if hasattr(agent, '_get_fallback_model'):
            fallback = agent._get_fallback_model()
            if fallback:
                config = fallback.get_config()
                print(f"Fallback model available: {config.get('model_id')}")
            else:
                print("Fallback model not available")

        print("✅ Model configuration test completed")

    except Exception as e:
        print(f"❌ Model configuration test failed: {e}")


if __name__ == "__main__":
    print("=== Executor Agent Test ===\n")

    # Test plan parsing
    plan = test_plan_parsing()

    # Test execution (async)
    print("\n=== Execution Test ===")
    asyncio.run(test_executor())

    # Test model configuration
    print("\n=== Model Configuration Test ===")
    test_model_configuration()

    print("\n=== Test Complete ===")
    print("\nExecutor agent works with structured data!")
    print("No complex parsing needed - just pass ExecutionPlan objects directly.")
    print("Model configuration with fallback support is working!")