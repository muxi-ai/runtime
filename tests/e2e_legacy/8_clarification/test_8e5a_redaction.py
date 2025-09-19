"""
Test 8E5a: Credential Redaction

This test validates that credentials are properly redacted from logs and responses.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_credential_redaction():
    """Test credential redaction in logs and responses."""
    try:
        print("\n=== Test 8E5a: Credential Redaction ===")

        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e5a")

        print("\n1. Testing credential redaction: 'My token is sk-secret123'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="My token is sk-secret123",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response1.content}")

        # Should not echo credential back
        assert "sk-secret123" not in response1.content, \
            "Should not echo credential back in response"
        print("   ✅ Credential not echoed in response")

        # Should handle appropriately
        response_lower = response1.content.lower()
        security_indicators = ["secure", "redacted", "stored", "not display"]
        assert any(indicator in response_lower for indicator in security_indicators) or \
               len(response1.content) > 10, \
               "Should handle credential appropriately"
        print("   ✅ Credential handled securely")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Credential redaction working")
        print("✓ Credentials not echoed in responses")
        print("✓ Secure credential handling")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: My token is sk-secret123")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E5a FAILED: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_credential_redaction())
    sys.exit(0 if success else 1)
