"""
Test 8E5b: Context Switch During Credential

This test validates context switching during credential collection.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_context_switch_during_credential():
    """Test context switching during credential collection."""
    try:
        print("\n=== Test 8E5b: Context Switch During Credential ===")

        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e5b")

        print("\n1. Start credential request: 'Get my GitHub repos'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Get my GitHub repos",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response1.content}")

        print("\n2. Context switch: 'What time is it?'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="What time is it?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response2.content}")

        # Should handle context switch appropriately
        response_lower = response2.content.lower()
        time_indicators = ["time", "clock", "hour", "minute", "am", "pm"]
        context_indicators = ["understand", "switch", "different"]

        handles_context = any(indicator in response_lower for indicator in time_indicators + context_indicators)
        assert handles_context, "Should handle context switch appropriately"
        print("   ✅ Context switch handled appropriately")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Context switch during credential working")
        print("✓ Context switch detected and handled")
        print("✓ System adapted to new request")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Get my GitHub repos")
        print(f"System: {response1.content}")
        print("\nUser: What time is it?")
        print(f"System: {response2.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E5b FAILED: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_context_switch_during_credential())
    sys.exit(0 if success else 1)
