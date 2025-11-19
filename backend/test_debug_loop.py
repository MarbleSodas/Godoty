"""Debug script to track agent loop execution in detail."""
import asyncio
import logging
from dotenv import load_dotenv

# Set up detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

from agents.planning_agent import PlanningAgent


async def main():
    print("\n" + "="*80)
    print("DEBUGGING AGENT LOOP")
    print("="*80 + "\n")

    agent = PlanningAgent()

    # Simple prompt that requires one tool call
    prompt = "Use the list_files tool to list files in the backend/agents directory"
    print(f"Prompt: {prompt}\n")
    print("Starting agent loop...\n")

    try:
        result = await asyncio.wait_for(
            agent.plan_async(prompt),
            timeout=30.0  # 30 second timeout
        )
        print(f"\n{'='*80}")
        print("RESULT:")
        print(f"{'='*80}")
        print(result)
    except asyncio.TimeoutError:
        print("\n[TIMEOUT] Agent loop took longer than 30 seconds")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
