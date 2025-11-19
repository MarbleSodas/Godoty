"""
Quick debug script to see what format OpenRouter returns for tool calls.
"""

import asyncio
import logging
from dotenv import load_dotenv

# Configure logging to see debug messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

from agents.planning_agent import PlanningAgent


async def main():
    print("\n" + "="*80)
    print("DEBUG: Testing OpenRouter tool call format")
    print("="*80 + "\n")

    agent = PlanningAgent()

    # Simple prompt that should trigger a tool call
    prompt = "List files in the backend directory"

    print(f"Prompt: {prompt}\n")
    print("Checking what format OpenRouter uses for tool calls...\n")

    try:
        result = await agent.plan_async(prompt)
        print(f"\nResult: {result}")
    except Exception as e:
        print(f"\nError (expected): {e}")
        print("\nCheck the logs above to see the tool call format")


if __name__ == "__main__":
    asyncio.run(main())
