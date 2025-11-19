"""Quick test to verify tool execution works."""
import asyncio
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

from agents.planning_agent import PlanningAgent


async def main():
    agent = PlanningAgent()

    print("\n" + "="*80)
    print("Testing tool execution with Agent Loop")
    print("="*80 + "\n")

    prompt = "List files in the backend/agents directory"
    print(f"Prompt: {prompt}\n")

    result = await agent.plan_async(prompt)

    print(f"\nResult:\n{result}\n")

    # Check if result contains file names (indicating tools were executed)
    if "planning_agent.py" in result or ".py" in result:
        print("[SUCCESS] Tools were executed!")
    else:
        print("[FAILURE] Tools were not executed. Result:", result[:200])


if __name__ == "__main__":
    asyncio.run(main())
