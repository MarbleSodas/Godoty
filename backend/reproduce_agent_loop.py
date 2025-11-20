"""
Test script to verify the Strands Agent Loop integration with OpenRouter.

This script tests that:
1. plan_async uses the Strands Agent Loop for multi-step reasoning
2. plan_stream properly streams events from the Agent Loop
3. Tools are executed correctly within the loop
4. The agent can perform recursive tool calls
"""

import asyncio
import os
import logging
import warnings
from dotenv import load_dotenv

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

from agents.planning_agent import PlanningAgent


async def test_plan_async_with_tools():
    """
    Test plan_async method with a prompt that requires tool use.
    This verifies the agent loop is active and tools are executed.
    """
    print("\n" + "="*80)
    print("TEST 1: Testing plan_async with Tool Execution")
    print("="*80 + "\n")

    try:
        # Initialize planning agent
        agent = PlanningAgent()

        # Use a prompt that should trigger tool use
        # The agent has access to search_codebase, read_file, etc.
        prompt = "List the files in the backend/agents directory"

        print(f"Prompt: {prompt}\n")
        print("Calling plan_async (should use Agent Loop with tools)...\n")

        result = await agent.plan_async(prompt)

        print(f"\nResult:\n{result}\n")

        # Verify the result mentions files (indicating tool was called)
        if "planning_agent.py" in result or "models" in result or "tools" in result:
            print("[SUCCESS] Agent loop executed tools and returned file information!")
            return True
        else:
            print("[FAILURE] Result doesn't indicate tool execution")
            return False

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_plan_stream_with_events():
    """
    Test plan_stream method to verify it streams events from the Agent Loop.
    """
    print("\n" + "="*80)
    print("TEST 2: Testing plan_stream Event Streaming")
    print("="*80 + "\n")

    try:
        # Initialize planning agent
        agent = PlanningAgent()

        # Use a simpler prompt for streaming test
        prompt = "What tools do you have available for reading files?"

        print(f"Prompt: {prompt}\n")
        print("Calling plan_stream (should stream events from Agent Loop)...\n")

        events_received = []
        tool_events_count = 0
        data_events_count = 0

        async for event in agent.plan_stream(prompt):
            event_type = event.get("type")
            events_received.append(event_type)

            if event_type == "start":
                print(f"-> START: {event.get('data', {}).get('message')}")
            elif event_type == "data":
                text = event.get("data", {}).get("text", "")
                data_events_count += 1
                print(f"-> DATA: {text[:50]}..." if len(text) > 50 else f"-> DATA: {text}")
            elif event_type == "tool_use":
                tool_events_count += 1
                tool_name = event.get("data", {}).get("tool_name")
                print(f"-> TOOL_USE: {tool_name}")
            elif event_type == "tool_result":
                tool_name = event.get("data", {}).get("tool_name")
                print(f"-> TOOL_RESULT: {tool_name}")
            elif event_type == "end":
                stop_reason = event.get("data", {}).get("stop_reason")
                print(f"-> END: {stop_reason}")
            elif event_type == "error":
                error = event.get("data", {}).get("error")
                print(f"-> ERROR: {error}")

        print(f"\nEvents received: {events_received}")
        print(f"Data events: {data_events_count}")
        print(f"Tool events: {tool_events_count}")

        # Verify we received events
        if "start" in events_received and "end" in events_received and data_events_count > 0:
            print("\n[SUCCESS] Streaming events received from Agent Loop!")
            return True
        else:
            print("\n[FAILURE] Expected streaming events not received")
            return False

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_multi_step_reasoning():
    """
    Test that the agent can perform multi-step reasoning with tool calls.
    """
    print("\n" + "="*80)
    print("TEST 3: Testing Multi-Step Reasoning")
    print("="*80 + "\n")

    try:
        # Initialize planning agent
        agent = PlanningAgent()

        # Use a prompt that requires multiple steps
        prompt = "Find the planning_agent.py file and tell me what the plan_async method does"

        print(f"Prompt: {prompt}\n")
        print("Calling plan_async (should require multiple tool calls)...\n")

        result = await agent.plan_async(prompt)

        print(f"\nResult:\n{result}\n")

        # Verify the result mentions the method functionality
        if "plan_async" in result.lower() or "asynchron" in result.lower():
            print("[SUCCESS] Agent performed multi-step reasoning!")
            return True
        else:
            print("[PARTIAL] Result received but may not indicate multi-step reasoning")
            return False

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """
    Run all tests and report results.
    """
    print("\n" + "="*80)
    print("STRANDS AGENT LOOP INTEGRATION TEST SUITE")
    print("="*80)

    results = []

    # Test 1: plan_async with tools
    results.append(await test_plan_async_with_tools())

    # Test 2: plan_stream with events
    results.append(await test_plan_stream_with_events())

    # Test 3: Multi-step reasoning
    results.append(await test_multi_step_reasoning())

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Tests passed: {sum(results)}/{len(results)}")

    if all(results):
        print("\n[SUCCESS] ALL TESTS PASSED - Agent Loop is properly integrated!")
    else:
        print("\n[FAILURE] SOME TESTS FAILED - Please review the output above")

    print("="*80 + "\n")

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
