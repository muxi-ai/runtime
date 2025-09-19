#!/usr/bin/env python3
"""
Test 12B5: Capital Question Test
Tests whether A2A loop detection happens with a simple knowledge question.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_capital_question():
    """Test capital question to see if delegation happens."""
    print("\n" + "=" * 60)
    print("TEST 12B5: Capital Question Test")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Test: Simple knowledge question
        print("\n" + "=" * 40)
        print("TEST: SIMPLE KNOWLEDGE QUESTION")
        print("=" * 40)
        print('[Request] Sending: "what\'s the capital of France?" (sync)')

        response = await overlord.chat(
            message="what's the capital of France?",
            user_id="capital_test",
            session_id="capital_session",
            use_async=False,
            stream=False,
        )

        print(f"[Response] Result: {response}")

        # Check if it's a delegation message
        if "delegated the task to an external agent" in str(response):
            print("⚠️ Got delegation message for capital question!")
        else:
            print("✅ Got direct response (no delegation)")

        # Cleanup
        await formation.kill_overlord()

        print("\n✅ TEST COMPLETED: Capital question test done")
        print(
            f"\nRESULT: {'Delegation detected' if 'delegated the task' in str(response) else 'Direct response'}"
        )

        return 0

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_capital_question())
    sys.exit(exit_code)
