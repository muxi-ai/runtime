"""Test if clarification code path is reached."""

import asyncio
from pathlib import Path
import sys
import os

# Suppress MCP server output
os.environ['SUPPRESS_MCP_OUTPUT'] = '1'

sys.path.insert(0, str(Path(__file__).parent))

from src.muxi import Formation


async def test():
    try:
        print("Loading formation...")
        formation_path = Path(__file__).parent / "test-formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Check initial state
        print(f"\nInitial state:")
        print(f"  information_analyzer: {overlord.information_analyzer is not None}")
        print(f"  proactive_detector: {overlord.proactive_detector is not None}")
        print(f"  clarification_manager: {overlord.clarification_manager is not None}")
        print(f"  question_generator: {overlord.question_generator is not None}")
        
        print("\nSending test message...")
        
        # Start a task that will timeout
        task = asyncio.create_task(overlord.chat(
            message="Help with scraper",
            user_id="test_user",
            session_id="test_session",
            stream=False
        ))
        
        # Wait for just 2 seconds
        try:
            response = await asyncio.wait_for(task, timeout=2.0)
            print(f"\nGot response!")
            print(f"Content: {response.content[:100]}...")
            print(f"Metadata: {response.metadata}")
            
            if response.metadata and response.metadata.get("clarification"):
                print("\n✅ SUCCESS: Clarification triggered!")
            else:
                print("\n❌ FAIL: No clarification")
        except asyncio.TimeoutError:
            print("\n⏱️ TIMEOUT: Request is processing (likely going to agent)")
            print("❌ FAIL: Clarification not triggered quickly")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        import os
        os._exit(0)  # Force exit


if __name__ == "__main__":
    asyncio.run(test())