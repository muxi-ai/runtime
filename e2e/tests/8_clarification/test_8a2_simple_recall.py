#!/usr/bin/env python3
"""
Simple recall test - just one iteration to debug
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_simple_recall():
    """Simple single recall test."""
    print("\n" + "=" * 80)
    print("Simple Recall Test")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        #Turn 1: Store name
        print("\n✓ Turn 1: Storing 'My name is Bob'...")
        response1 = await overlord.chat(
            message="My name is Bob",
            user_id="simple_test_user",
            session_id="simple_session",
            stream=False
        )
        print(f"  Response: {response1.content[:150]}...")
        
        # Wait for extraction
        print("  Waiting 8 seconds for memory extraction...")
        await asyncio.sleep(8)
        
        # Turn 2: Recall name
        print("\n✓ Turn 2: Asking 'What is my name?'...")
        response2 = await overlord.chat(
            message="What is my name?",
            user_id="simple_test_user",
            session_id="simple_session",
            stream=False
        )
        
        content = response2.content if hasattr(response2, "content") else str(response2)
        print(f"\n  Full response:\n{content}\n")
        
        # Check result
        has_bob = "bob" in content.lower()
        has_clarification = any(ind in content.lower() for ind in [
            "could you specify",
            "could you clarify",
            "what do you mean",
            "need more information"
        ])
        
        if has_bob and not has_clarification:
            print("✅ SUCCESS: Bob mentioned, no clarification!")
        elif has_bob and has_clarification:
            print("⚠️  PARTIAL: Bob mentioned but also clarification")
        elif not has_bob and has_clarification:
            print("❌ FAILED: Clarification triggered, no Bob")
        else:
            print("❓ UNCLEAR: Unexpected response")
        
        # Cleanup
        await formation.stop_overlord()
        formation.stop()
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_simple_recall())
    sys.exit(exit_code)
