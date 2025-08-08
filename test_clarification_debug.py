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
        print(f"   Pending clarifications: {session_id in overlord._pending_clarifications}")
        
        # Message 2
        print("\n2. User: 'what do you mean?'")
        response2 = await overlord.chat(
            message="what do you mean?",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        print(f"   Bot: {response2.content[:150]}...")
        is_clarification = response2.metadata and response2.metadata.get("clarification")
        print(f"   Still clarifying: {is_clarification}")
        print(f"   Pending clarifications: {session_id in overlord._pending_clarifications}")
        
        # Message 3
        print("\n3. User: 'aroussi.com'")
        response3 = await overlord.chat(
            message="aroussi.com",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        print(f"   Bot: {response3.content[:150]}...")
        is_clarification = response3.metadata and response3.metadata.get("clarification")
        print(f"   Still clarifying: {is_clarification}")
        print(f"   Pending clarifications: {session_id in overlord._pending_clarifications}")
        
        # Message 4 - more specific
        print("\n4. User: 'I want to scrape stock prices from aroussi.com using Python'")
        response4 = await overlord.chat(
            message="I want to scrape stock prices from aroussi.com using Python",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        print(f"   Bot: {str(response4.content)[:150]}...")
        is_clarification = response4.metadata and response4.metadata.get("clarification")
        print(f"   Still clarifying: {is_clarification}")
        print(f"   Pending clarifications: {session_id in overlord._pending_clarifications}")
        
        print("\n=== Summary ===")
        if not is_clarification:
            print("✅ Clarification chain resolved after providing specific details")
        else:
            print("⚠️ Still in clarification loop - may need adjustment")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())
EOF < /dev/null