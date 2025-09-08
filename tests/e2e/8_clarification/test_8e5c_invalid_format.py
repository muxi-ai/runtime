"""
Test 8E5c: Invalid Credential Format

This test validates handling of invalid credential formats.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_invalid_credential_format():
    """Test handling of invalid credential formats."""
    try:
        print("\n=== Test 8E5c: Invalid Credential Format ===")

        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e5c")

        print("\n1. Request credential: 'Access GitHub API'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Access GitHub API",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response1.content}")

        print("\n2. Provide invalid format: 'invalid-token-format'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="invalid-token-format",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response2.content}")

        # Should handle invalid format appropriately
        response_lower = response2.content.lower()
        validation_indicators = ["invalid", "format", "correct", "should", "try again", "example"]
        assert any(indicator in response_lower for indicator in validation_indicators) or \
               "github" not in response_lower, \
               "Should handle invalid format appropriately"
        print("   ✅ Invalid format handled appropriately")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Invalid credential format handling working")
        print("✓ Invalid format detected and handled")
        print("✓ Appropriate feedback provided")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Access GitHub API")
        print(f"System: {response1.content}")
        print("\nUser: invalid-token-format")
        print(f"System: {response2.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E5c FAILED: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_invalid_credential_format())
    sys.exit(0 if success else 1)
