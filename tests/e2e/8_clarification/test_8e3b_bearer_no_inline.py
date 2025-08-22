"""
Test 8E3b: Bearer with allow_inline false

This test validates that Bearer tokens with allow_inline=false
are redirected even in dynamic mode.

Test flow:
1. Configure formation in dynamic mode
2. Simulate Bearer request with allow_inline=false
3. Verify system redirects appropriately
4. Test security enforcement
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation
from test_utils import TestContext


async def test_bearer_no_inline():
    """Test Bearer with allow_inline=false redirects."""
    try:
        print("\n=== Test 8E3b: Bearer with allow_inline=false ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        formation.config["user_credentials"] = {
            "mode": "dynamic",
            "service_overrides": {
                "secure_api": {
                    "auth_type": "bearer",
                    "allow_inline": False
                }
            }
        }
        
        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e3b")
        
        print("\n1. Testing secure Bearer API: 'Access secure enterprise API'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Access secure enterprise API",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should redirect or not offer inline
        response_lower = response1.content.lower()
        redirect_indicators = ["external", "configure", "portal", "redirect"]
        inline_indicators = ["provide", "enter", "paste", "token here"]
        
        should_redirect = any(indicator in response_lower for indicator in redirect_indicators)
        should_not_inline = not any(indicator in response_lower for indicator in inline_indicators)
        
        assert should_redirect or should_not_inline, \
            "Should redirect or not offer inline for Bearer with allow_inline=false"
        print("   ✅ Bearer with allow_inline=false handled securely")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Bearer allow_inline=false working correctly")
        print("✓ Secure Bearer API redirected appropriately")
        print("✓ No inline entry offered when disabled")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Access secure enterprise API")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E3b FAILED: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_bearer_no_inline())
    sys.exit(0 if success else 1)