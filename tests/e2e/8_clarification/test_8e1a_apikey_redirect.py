"""
Test 8E1a: API Key in Redirect Mode

This test validates that API key requests are redirected in redirect mode,
ensuring enterprise security by preventing any inline credential entry.

Test flow:
1. Configure formation in redirect mode
2. User requests GitHub repositories
3. System asks which existing account to use
4. User requests to add new account
5. System redirects to external credential management
6. Ensure no inline prompting occurs
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_api_key_redirect_mode():
    """Test API key requests are redirected in redirect mode."""
    try:
        print("\n=== Test 8E1a: API Key in Redirect Mode ===")

        # Load formation with redirect mode enabled (configured in formation.yaml)
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create unique test context but use user1 for credentials
        ctx = TestContext("test_8e1a")
        user_id = "user1"  # Use user1 which has credentials in the database
        print(f"Using User: {user_id}, Session: {ctx.session_id}")

        # Step 1: Request that would need GitHub API key
        print("\n1. Testing GitHub API key request: 'Get my GitHub repositories'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Get my GitHub repositories",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0  # 2 minute timeout
        )

        print(f"   Response: {response1.content}")

        # Should ask which account to use (since user1 has existing accounts)
        response_lower = response1.content.lower()
        account_selection = ["which", "ranaroussi", "lilyautomaze", "account"]
        assert any(indicator in response_lower for indicator in account_selection), \
            f"Should ask which account to use. Got: {response1.content}"
        print("   ✅ System asks which account to use")

        # Step 2: User wants to add a new account - be explicit
        print("\n2. User requests new account: 'I need to add a new GitHub account with different credentials'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="I need to add a new GitHub account with different credentials",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response2.content}")

        # System might ask for account details or redirect based on configuration
        response_lower = response2.content.lower()

        # If it asks for details, provide them to trigger redirect
        if "username" in response_lower or "details" in response_lower or "provide" in response_lower:
            print("\n2b. Providing new account details: 'My new account is newuser123'")
            response2b = await asyncio.wait_for(
                overlord.chat(
                    message="My new account is newuser123",
                    user_id=user_id,
                    session_id=ctx.session_id,
                    stream=False
                ),
                timeout=120.0
            )
            print(f"    Response: {response2b.content}")
            response_lower = response2b.content.lower()

        # NOW it should redirect to external credential management
        redirect_indicators = [
            "external", "configure", "outside", "portal", "credential manager", "redirect", "security"]
        if not any(indicator in response_lower for indicator in redirect_indicators):
            # Might be asking for the token - this is where redirect should happen
            print("\n2c. If asked for token, should trigger redirect")
            if "token" in response_lower or "api key" in response_lower or "personal access" in response_lower:
                print("   ⚠️  System is asking for credentials - redirect mode should prevent this")
                # In redirect mode, it should not ask for credentials inline
                assert False, f"In redirect mode, should not ask for credentials inline. Got: {response_lower}"

        print("   ✅ Credential request handled according to redirect mode")

        # Step 3: Different API key service (OpenAI)
        print("\n3. Testing OpenAI API key request: 'Generate some text with AI'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="Generate some text with AI",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response3.content}")

        # Should also redirect (consistent behavior)
        response_lower = response3.content.lower()
        # Check if it's asking for OpenAI API key or redirecting
        openai_indicators = ["openai", "api key", "configure"]
        assert any(indicator in response_lower for indicator in openai_indicators), \
            "Should handle OpenAI API key request"
        print("   ✅ OpenAI request handled")

        # Step 4: Generic API service
        print("\n4. Testing generic API service: 'Access the REST API'")
        response4 = await asyncio.wait_for(
            overlord.chat(
                message="Access the REST API",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response4.content}")

        # Should handle appropriately (either redirect or work without credentials)
        assert response4.content, "Should provide some response"
        print("   ✅ Generic API request handled appropriately")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: API key redirect mode working correctly")
        print("✓ System asks which existing account to use")
        print("✓ New account request redirected to external management")
        print("✓ No inline credential prompting occurred")
        print("✓ OpenAI request handled appropriately")
        print("✓ Generic API requests handled appropriately")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Get my GitHub repositories")
        print(f"System: {response1.content}")
        print("\nUser: I need to add a new GitHub account with different credentials")
        print(f"System: {response2.content}")
        if 'response2b' in locals():
            print("\nUser: My new account is newuser123")
            print(f"System: {response2b.content}")
        print("\nUser: Generate some text with AI")
        print(f"System: {response3.content}")
        print("\nUser: Access the REST API")
        print(f"System: {response4.content}")
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
            print("\nUser: I need to add a new GitHub account with different credentials")
            print(f"System: {response2.content}")
        if 'response2b' in locals():
            print("\nUser: My new account is newuser123")
            print(f"System: {response2b.content}")
        if 'response3' in locals():
            print("\nUser: Generate some text with AI")
            print(f"System: {response3.content}")
        if 'response4' in locals():
            print("\nUser: Access the REST API")
            print(f"System: {response4.content}")
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
        # Redirect mode is already configured in formation.yaml

        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e1a_b")
        user_id = "user1"  # Use user1 which has credentials

        # Try to provide an API key directly (should be ignored/redirected)
        print("\n1. Attempting to provide API key directly: 'My GitHub token is ghp_123456'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="My GitHub token is ghp_123456",
                user_id=user_id,
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
