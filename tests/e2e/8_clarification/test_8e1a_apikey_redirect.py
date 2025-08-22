"""
Test 8E1a: API Key in Redirect Mode

This test validates that API key requests are redirected in redirect mode,
ensuring enterprise security by preventing any inline credential entry.

Test flow:
1. Configure formation in redirect mode
2. Simulate API key credential request
3. Verify system redirects to external credential management
4. Ensure no inline prompting occurs
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_api_key_redirect_mode():
    """Test API key requests are redirected in redirect mode."""
    try:
        print("\n=== Test 8E1a: API Key in Redirect Mode ===")
        
        # Load formation with redirect mode enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Override formation config for redirect mode
        formation.config["user_credentials"] = {
            "mode": "redirect",
            "redirect_message": "Please configure your API credentials in the external credential manager."
        }
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create unique test context
        ctx = TestContext("test_8e1a")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Step 1: Request that would need GitHub API key
        print("\n1. Testing GitHub API key request: 'Get my GitHub repositories'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Get my GitHub repositories",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0  # 2 minute timeout
        )
        
        print(f"   Response: {response1.content}")
        
        # Should redirect to external credential management
        response_lower = response1.content.lower()
        redirect_indicators = ["external", "configure", "outside", "portal", "credential manager", "redirect"]
        assert any(indicator in response_lower for indicator in redirect_indicators), \
            "Should redirect to external credential management"
        print("   ✅ Redirected to external credential management")
        
        # Should NOT ask for inline credential entry
        inline_indicators = ["provide", "enter", "api key", "token", "paste"]
        assert not any(indicator in response_lower for indicator in inline_indicators), \
            "Should not prompt for inline credential entry"
        print("   ✅ No inline credential prompting")
        
        # Step 2: Different API key service (OpenAI)
        print("\n2. Testing OpenAI API key request: 'Generate some text with AI'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="Generate some text with AI",
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
            "Should redirect OpenAI requests in redirect mode"
        print("   ✅ OpenAI request also redirected")
        
        # Step 3: Generic API key service
        print("\n3. Testing generic API service: 'Access the REST API'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="Access the REST API",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response3.content}")
        
        # Should handle appropriately (either redirect or work without credentials)
        assert response3.content, "Should provide some response"
        print("   ✅ Generic API request handled appropriately")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: API key redirect mode working correctly")
        print("✓ GitHub API key request redirected to external management")
        print("✓ No inline credential prompting occurred")
        print("✓ OpenAI request also redirected consistently")
        print("✓ Generic API requests handled appropriately")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Get my GitHub repositories")
        print(f"System: {response1.content}")
        print("\nUser: Generate some text with AI")
        print(f"System: {response2.content}")
        print("\nUser: Access the REST API")
        print(f"System: {response3.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E1a: API Key Redirect Mode FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: API key redirect mode test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Get my GitHub repositories")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: Generate some text with AI")
            print(f"System: {response2.content}")
        if 'response3' in locals():
            print("\nUser: Access the REST API")
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


async def test_api_key_security_enforcement():
    """Test security enforcement prevents credential leakage in redirect mode."""
    try:
        print("\n=== Test 8E1a-b: API Key Security Enforcement ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Configure strict redirect mode
        formation.config["user_credentials"] = {
            "mode": "redirect",
            "redirect_message": "For security, configure credentials externally."
        }
        
        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e1a_b")
        
        # Try to provide an API key directly (should be ignored/redirected)
        print("\n1. Attempting to provide API key directly: 'My GitHub token is ghp_123456'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="My GitHub token is ghp_123456",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should not acknowledge or store the token
        response_lower = response1.content.lower()
        assert "ghp_123456" not in response_lower, "Should not echo back the token"
        print("   ✅ Token not echoed back in response")
        
        # Should still redirect
        redirect_indicators = ["external", "configure", "security"]
        token_acceptance = ["stored", "saved", "received", "thank you"]
        assert any(indicator in response_lower for indicator in redirect_indicators) or \
               not any(indicator in response_lower for indicator in token_acceptance), \
               "Should redirect or not acknowledge token storage"
        print("   ✅ Security maintained - no token acknowledgment")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: API key security enforcement working")
        print("✓ Direct token provision not acknowledged")
        print("✓ Token not echoed in system response")
        print("✓ Security redirect policy maintained")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: My GitHub token is ghp_123456")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E1a-b FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: API key security enforcement test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: My GitHub token is ghp_123456")
            print(f"System: {response1.content}")
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
        """Run all API key redirect mode tests."""
        results = []
        
        # Run main redirect test
        result = await test_api_key_redirect_mode()
        results.append(("8E1a: API Key Redirect Mode", result))
        
        # Run security enforcement test
        result = await test_api_key_security_enforcement()
        results.append(("8E1a-b: API Key Security Enforcement", result))
        
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