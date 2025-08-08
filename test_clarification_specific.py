"""Test specific clarification sequence."""

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
        
        print("\n=== Testing Specific Clarification Sequence ===\n")
        
        session_id = "test_specific"
        user_id = "test_user_specific"
        
        # First message
        print("1. Initial request")
        print("   User: 'help with scrape'")
        
        response1 = await overlord.chat(
            message="help with scrape",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        
        is_clarification1 = response1.metadata and response1.metadata.get("clarification")
        print(f"   Bot: {response1.content}")
        print(f"   Status: {'🔄 Asking for clarification' if is_clarification1 else '✅ Processing'}")
        
        if not is_clarification1:
            print("   ❌ Expected clarification but got processing")
            return
        
        print()
        
        # Second message - deflecting back with a question
        print("2. Deflecting clarification")
        print("   User: 'what do you mean?'")
        
        response2 = await overlord.chat(
            message="what do you mean?",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        
        is_clarification2 = response2.metadata and response2.metadata.get("clarification")
        response2_text = str(response2.content)
        if len(response2_text) > 200:
            response2_text = response2_text[:200] + "..."
        print(f"   Bot: {response2_text}")
        print(f"   Status: {'🔄 Still asking for clarification' if is_clarification2 else '✅ Processing'}")
        
        print()
        
        # Third message - finally providing a specific website
        print("3. Providing specific website")
        print("   User: 'aroussi.com'")
        
        response3 = await overlord.chat(
            message="aroussi.com",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )
        
        is_clarification3 = response3.metadata and response3.metadata.get("clarification")
        response3_text = str(response3.content)
        if len(response3_text) > 200:
            response3_text = response3_text[:200] + "..."
        print(f"   Bot: {response3_text}")
        print(f"   Status: {'🔄 STILL asking for clarification' if is_clarification3 else '✅ Processing request'}")
        
        print("\n=== Analysis ===")
        print("The conversation flow:")
        print("1. 'help with scrape' - ambiguous, triggered clarification")
        print("2. 'what do you mean?' - user deflected, system should ask again or explain")
        print("3. 'aroussi.com' - specific website provided, should process")
        
        print("\nCombined context at each stage:")
        print("Stage 1: 'help with scrape'")
        print("Stage 2: 'help with scrape. what do you mean?'")
        print("Stage 3: 'help with scrape. what do you mean?. aroussi.com'")
        print("\nThe LLM interprets this progressively and decides when enough context exists.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())