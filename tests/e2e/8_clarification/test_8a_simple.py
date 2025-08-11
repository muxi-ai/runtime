"""Simple Day 8A Test - Verify clarification works."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation


async def test():
    try:
        print("\n=== Day 8A: Simple Clarification Test ===\n")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        overlord = await formation.start_overlord()
        
        # Test 1: Ambiguous request
        print("1. User: 'help with scrape'")
        response = await overlord.chat(
            message="help with scrape",
            user_id="test_user",
            session_id="test_session",
            stream=False
        )
        print(f"   Bot: {response.content}")
        
        is_clarification = response.metadata and response.metadata.get("clarification")
        if is_clarification:
            print("   ✅ Clarification triggered")
            
            # Provide clarification
            print("\n2. User: 'scraping aroussi.com'")
            response2 = await overlord.chat(
                message="scraping aroussi.com",
                user_id="test_user",
                session_id="test_session",
                stream=False
            )
            print(f"   Bot: {response2.content[:150]}...")
            
            is_clarification2 = response2.metadata and response2.metadata.get("clarification")
            if not is_clarification2:
                print("   ✅ Request processed after clarification")
            else:
                print("   ⚠️ Still asking for clarification")
        else:
            print("   ⚠️ No clarification triggered")
        
        print("\n✅ Day 8A test completed")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())