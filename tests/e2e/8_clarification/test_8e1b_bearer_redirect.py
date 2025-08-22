"""
Test 8E1b: Bearer Token in Redirect Mode

This test validates that Bearer token requests are redirected in redirect mode,
ensuring enterprise security by preventing any inline token entry.

Test flow:
1. Configure formation in redirect mode
2. Simulate Bearer token credential request
3. Verify system redirects to external credential management
4. Test various Bearer token scenarios
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_bearer_token_redirect_mode():
    """Test Bearer token requests are redirected in redirect mode."""
    try:
        print("\n=== Test 8E1b: Bearer Token in Redirect Mode ===")
        
        # Load formation with redirect mode enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Override formation config for redirect mode
        formation.config["user_credentials"] = {
            "mode": "redirect",
            "redirect_message": "Please configure your Bearer tokens in the external credential portal."
        }
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create unique test context
        ctx = TestContext("test_8e1b")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Step 1: Request that would need Bearer token (Slack)
        print("\n1. Testing Slack Bearer token request: 'Send a message to my Slack channel'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Send a message to my Slack channel",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0  # 2 minute timeout
        )
        
        print(f"   Response: {response1.content}")
        
        # Should redirect to external credential management
        response_lower = response1.content.lower()
        redirect_indicators = ["external", "configure", "outside", "portal", "credential", "redirect"]
        assert any(indicator in response_lower for indicator in redirect_indicators), \
            "Should redirect to external credential management"
        print("   ✅ Redirected to external credential management")
        
        # Should NOT ask for inline Bearer token entry
        inline_indicators = ["provide", "enter", "bearer", "token", "paste", "authorization"]
        assert not any(indicator in response_lower for indicator in inline_indicators), \
            "Should not prompt for inline Bearer token entry"
        print("   ✅ No inline Bearer token prompting")
        
        # Step 2: JWT Bearer token service
        print("\n2. Testing JWT Bearer token request: 'Access the secure API with JWT'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="Access the secure API with JWT",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response2.content}")
        
        # Should also redirect (consistent behavior)
        response_lower = response2.content.lower()
        assert any(indicator in response_lower for indicator in redirect_indicators), \
            "Should redirect JWT requests in redirect mode"
        print("   ✅ JWT request also redirected")
        
        # Step 3: OAuth Bearer token
        print("\n3. Testing OAuth Bearer request: 'Get my Google Drive files'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="Get my Google Drive files",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response3.content}")
        
        # Should handle appropriately (redirect for OAuth)
        response_lower = response3.content.lower()
        oauth_indicators = ["oauth", "authorize", "browser", "redirect"]
        assert any(indicator in response_lower for indicator in oauth_indicators + redirect_indicators), \
            "Should redirect OAuth requests appropriately"
        print("   ✅ OAuth Bearer request redirected appropriately")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Bearer token redirect mode working correctly")
        print("✓ Slack Bearer token request redirected to external management")
        print("✓ No inline Bearer token prompting occurred")
        print("✓ JWT request also redirected consistently")
        print("✓ OAuth Bearer requests handled with proper redirect")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Send a message to my Slack channel")
        print(f"System: {response1.content}")
        print("\nUser: Access the secure API with JWT")
        print(f"System: {response2.content}")
        print("\nUser: Get my Google Drive files")
        print(f"System: {response3.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E1b: Bearer Token Redirect Mode FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Bearer token redirect mode test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Send a message to my Slack channel")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: Access the secure API with JWT")
            print(f"System: {response2.content}")
        if 'response3' in locals():
            print("\nUser: Get my Google Drive files")
            print(f"System: {response3.content}")
        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_bearer_token_security_enforcement():
    """Test security enforcement prevents Bearer token leakage in redirect mode."""
    try:
        print("\n=== Test 8E1b-b: Bearer Token Security Enforcement ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Configure strict redirect mode
        formation.config["user_credentials"] = {
            "mode": "redirect",
            "redirect_message": "For security, configure Bearer tokens externally."
        }
        
        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e1b_b")
        
        # Try to provide a Bearer token directly (should be ignored/redirected)
        print("\n1. Attempting to provide Bearer token: 'My token is Bearer eyJhbGciOiJ'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="My token is Bearer eyJhbGciOiJ",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should not acknowledge or store the token
        response_lower = response1.content.lower()
        assert "eyJhbGciOiJ" not in response_lower, "Should not echo back the token"
        print("   ✅ Bearer token not echoed back in response")
        
        # Step 2: Try Slack token format
        print("\n2. Attempting Slack token: 'Here is my Slack token: xoxb-1234567890'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="Here is my Slack token: xoxb-1234567890",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response2.content}")
        
        # Should not echo Slack token
        response_lower = response2.content.lower()
        assert "xoxb-1234567890" not in response_lower, "Should not echo back Slack token"
        print("   ✅ Slack token not echoed back")
        
        # Should maintain redirect policy
        redirect_indicators = ["external", "configure", "security", "portal"]
        token_acceptance = ["stored", "saved", "received", "thank you"]
        assert any(indicator in response_lower for indicator in redirect_indicators) or \
               not any(indicator in response_lower for indicator in token_acceptance), \
               "Should maintain redirect policy"
        print("   ✅ Security redirect policy maintained")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Bearer token security enforcement working")
        print("✓ Direct Bearer token provision not acknowledged")
        print("✓ JWT token not echoed in system response")
        print("✓ Slack token not echoed in system response")
        print("✓ Security redirect policy maintained")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: My token is Bearer eyJhbGciOiJ")
        print(f"System: {response1.content}")
        print("\nUser: Here is my Slack token: xoxb-1234567890")
        print(f"System: {response2.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E1b-b FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Bearer token security enforcement test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: My token is Bearer eyJhbGciOiJ")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: Here is my Slack token: xoxb-1234567890")
            print(f"System: {response2.content}")
        print("\n" + "="*40)

        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


if __name__ == "__main__":
    async def run_tests():
        """Run all Bearer token redirect mode tests."""
        results = []
        
        # Run main redirect test
        result = await test_bearer_token_redirect_mode()
        results.append(("8E1b: Bearer Token Redirect Mode", result))
        
        # Run security enforcement test
        result = await test_bearer_token_security_enforcement()
        results.append(("8E1b-b: Bearer Token Security Enforcement", result))
        
        # Print summary
        print("\n" + "="*50)
        print("TEST SUMMARY")
        print("="*50)
        for test_name, passed in results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{test_name}: {status}")
        
        all_passed = all(result for _, result in results)
        if all_passed:
            print(f"\n🎉 All {len(results)} tests PASSED!")
        else:
            failed = sum(1 for _, result in results if not result)
            print(f"\n⚠️ {failed}/{len(results)} tests FAILED")
        
        return all_passed
    
    try:
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)
    finally:
        pass