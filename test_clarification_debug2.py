"""Debug clarification flow."""

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
        
        print("\n=== Clarification Debug Test ===\n")
        
        session_id = "debug_session"
        user_id = "debug_user"
        
        # Message 1
        print("1. User: 'help with scrape'")
        response1 = await overlord.chat(
            message="help with scrape",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        print(f"   Bot: {response1.content}")
        print(f"   Is clarification: {response1.metadata.get('clarification', False)}")
        print(f"   Pending clarifications: {session_id in overlord._pending_clarifications}")
        
        if session_id in overlord._pending_clarifications:
            info = overlord._pending_clarifications[session_id]
            print(f"   Stored question: {info.get('last_question', 'N/A')[:50]}...")
            print(f"   Original message: {info.get('original_message', 'N/A')[:50]}...")
        
        # Message 2
        print("\n2. User: 'aroussi.com' (providing website)")
        response2 = await overlord.chat(
            message="aroussi.com",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        print(f"   Bot: {response2.content[:150]}...")
        print(f"   Is clarification: {response2.metadata.get('clarification', False)}")
        print(f"   Pending clarifications: {session_id in overlord._pending_clarifications}")
        
        print("\n✅ Test completed")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())