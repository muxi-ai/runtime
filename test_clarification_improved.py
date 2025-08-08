"""Test improved clarification with context-aware questions."""

import asyncio
from pathlib import Path
import sys

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
        
        # Test 1: Incomplete sentence
        print("\n=== TEST 1: Incomplete sentence ===")
        response1 = await overlord.chat(
            message="can you me a",
            user_id="test_user_1",
            session_id="test_session_1",
            stream=False
        )
        
        print(f"Input: 'can you me a'")
        print(f"Response: {response1.content}")
        if response1.metadata and response1.metadata.get("clarification"):
            print("✅ Clarification triggered")
        else:
            print("❌ No clarification")
            
        # Test 2: Vague request about scraper
        print("\n=== TEST 2: Vague scraper request ===")
        response2 = await overlord.chat(
            message="I need help with a scraper",
            user_id="test_user_2",
            session_id="test_session_2",
            stream=False
        )
        
        print(f"Input: 'I need help with a scraper'")
        print(f"Response: {response2.content}")
        if response2.metadata and response2.metadata.get("clarification"):
            print("✅ Clarification triggered")
        else:
            print("❌ No clarification")
            
        # Test 3: Clear request
        print("\n=== TEST 3: Clear request ===")
        response3 = await overlord.chat(
            message="Write a Python function to sort a list of numbers",
            user_id="test_user_3",
            session_id="test_session_3",
            stream=False
        )
        
        print(f"Input: 'Write a Python function to sort a list of numbers'")
        if response3.metadata and response3.metadata.get("clarification"):
            print(f"Response: {response3.content}")
            print("❌ Clarification triggered (shouldn't have)")
        else:
            print("✅ No clarification (correctly went to agent)")
            print(f"Response preview: {response3.content[:100]}...")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure we exit cleanly
        import sys
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())