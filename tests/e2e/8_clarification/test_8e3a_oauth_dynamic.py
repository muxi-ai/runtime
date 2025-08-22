"""
Test 8E3a: OAuth Bearer without Hint in Dynamic Mode

This test validates that OAuth Bearer requests without allow_inline hint
are redirected even in dynamic mode, maintaining OAuth security.

Test flow:
1. Configure formation in dynamic mode
2. Simulate OAuth Bearer request without hint
3. Verify system redirects to OAuth flow
4. Test that inline entry is not offered
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation
from test_utils import TestContext


async def test_oauth_bearer_no_hint():
    """Test OAuth Bearer without hint redirects in dynamic mode."""
    try:
        print("\n=== Test 8E3a: OAuth Bearer without Hint ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        formation.config["user_credentials"] = {
            "mode": "dynamic",
            "inline_acceptance": {
                "oauth": False,  # OAuth never inline
                "bearer": "require_hint"
            }
        }
        
        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e3a")
        
        print("\n1. Testing OAuth Bearer: 'Connect to Google Drive'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Connect to Google Drive",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should redirect to OAuth flow
        response_lower = response1.content.lower()
        oauth_indicators = ["oauth", "authorize", "browser", "redirect", "consent"]
        assert any(indicator in response_lower for indicator in oauth_indicators), \
            "Should redirect to OAuth authorization"
        print("   ✅ Redirected to OAuth authorization")
        
        # Should NOT offer inline entry
        inline_indicators = ["provide", "enter", "paste", "token here"]
        assert not any(indicator in response_lower for indicator in inline_indicators), \
            "Should not offer inline entry for OAuth"
        print("   ✅ No inline entry offered for OAuth")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: OAuth Bearer without hint working correctly")
        print("✓ OAuth requests redirected to authorization flow")
        print("✓ No inline entry offered for OAuth tokens")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Connect to Google Drive")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E3a FAILED: {e}")
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: OAuth Bearer test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_oauth_bearer_no_hint())
    sys.exit(0 if success else 1)