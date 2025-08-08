"""Simple clarification test."""

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
        
        print("\n=== Simple Clarification Test ===\n")
        
        session_id = "simple_test"
        user_id = "simple_user"
        
        # Test 1: Ambiguous request
        print("1. User: 'help with scrape'")
        response1 = await overlord.chat(
            message="help with scrape",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        print(f"   Bot: {response1.content}")
        print(f"   Clarification: {response1.metadata.get('clarification', False)}")
        
        # Test 2: Provide URL as clarification response
        print("\n2. User: 'aroussi.com' (responding to clarification)")
        response2 = await overlord.chat(
            message="aroussi.com",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        response_text = str(response2.content)[:150]
        print(f"   Bot: {response_text}...")
        print(f"   Clarification: {response2.metadata.get('clarification', False)}")
        
        print("\n✅ Test completed")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())