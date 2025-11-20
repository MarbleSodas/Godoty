"""
Quick diagnostic script to test streaming events from planning agent.
"""
import asyncio
import logging
from agents.planning_agent import PlanningAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_streaming():
    """Test streaming events."""
    agent = PlanningAgent()
    
    prompt = "What is 2+2?"
    
    print("\\n=== Testing Stream Events ===")
    print(f"Prompt: {prompt}\\n")
    
    events_received = []
    async for event in agent.plan_stream(prompt):
        event_type = event.get("type")
        event_data = event.get("data", {})
        events_received.append(event_type)
        
        print(f"Event Type: {event_type}")
        if event_type == "data":
            print(f"  Data: {event_data.get('text', '')[:50]}...")
        elif event_type == "tool_use":
            print(f"  Tool: {event_data.get('tool_name')}")
        elif event_type == "error":
            print(f"  Error: {event_data.get('error')}")
        print()
    
    print(f"\\nTotal events received: {len(events_received)}")
    print(f"Event types: {set(events_received)}")
    print(f"Event sequence: {events_received}")
    
    # Count event types
    from collections import Counter
    event_counts = Counter(events_received)
    print(f"\\nEvent counts: {dict(event_counts)}")


if __name__ == "__main__":
    asyncio.run(test_streaming())
