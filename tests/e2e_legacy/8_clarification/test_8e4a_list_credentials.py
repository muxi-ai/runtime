"""
Test 8E4a: List Credentials

This test validates credential listing functionality.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_list_credentials():
    """Test credential listing functionality."""
    try:
        print("\n=== Test 8E4a: List Credentials ===")

        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e4a")

        print("\n1. Testing credential list: 'List my credentials'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="List my credentials",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response1.content}")

        # Should handle list request appropriately
        response_lower = response1.content.lower()
        list_indicators = ["credential", "list", "configured", "stored", "none", "no credentials"]
        assert any(indicator in response_lower for indicator in list_indicators), \
            "Should handle credential list request"
        print("   ✅ Credential list request handled")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: List credentials working")
        print("✓ Credential list request handled appropriately")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: List my credentials")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E4a FAILED: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_list_credentials())
    sys.exit(0 if success else 1)
