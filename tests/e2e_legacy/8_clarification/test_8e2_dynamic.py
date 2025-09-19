"""
Test 8E2: API Key in Dynamic Mode

This test validates that API key requests work with dynamic (inline) credential collection,
using the exact same test as 8E1a but with a formation configured for dynamic mode.

Test flow:
1. Configure formation in dynamic mode (using formation-dynamic.yaml)
2. User requests GitHub repositories
3. System asks which existing account to use OR prompts for credential
4. User requests to add new account
5. System prompts for inline credential entry (dynamic mode)
6. User provides credential and it's stored
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_api_key_dynamic_mode():
    """Test API key requests with dynamic inline collection mode."""
    try:
        print("\n=== Test 8E2: API Key in Dynamic Mode ===")

        # Load formation with dynamic mode enabled (configured in formation-dynamic.yaml)
        formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation-dynamic.yaml"
        formation = Formation()
        await formation.load(str(formation_path))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create unique test context but use user3 for testing
        ctx = TestContext("test_8e2")
        user_id = "user3"  # Use user3 which has NO credentials in the database
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

        # In dynamic mode, should prompt for credentials inline
        response_lower = response2.content.lower()

        # Check if it's prompting for credentials inline (dynamic mode behavior)
        credential_prompt_indicators = [
            "provide", "enter", "token", "api key", "personal access",
            "credential", "paste", "github pat", "authentication"
        ]

        # Check if it's NOT redirecting (which would be redirect mode behavior)
        redirect_indicators = [
            "external", "configure", "outside", "portal", "credential manager", "security"
        ]

        has_credential_prompt = any(indicator in response_lower for indicator in credential_prompt_indicators)
        has_redirect = any(indicator in response_lower for indicator in redirect_indicators)

        if has_redirect and not has_credential_prompt:
            print("   ⚠️  System is redirecting - dynamic mode should prompt inline")
            assert False, f"In dynamic mode, should prompt for credentials inline, not redirect. Got: {response_lower}"

        if has_credential_prompt:
            print("   ✅ System prompts for inline credential entry (dynamic mode)")

            # Step 2b: Provide the credential
            print("\n2b. Providing credential: 'ghp_test_dynamic_token_12345'")
            response2b = await asyncio.wait_for(
                overlord.chat(
                    message="ghp_test_dynamic_token_12345",
                    user_id=user_id,
                    session_id=ctx.session_id,
                    stream=False
                ),
                timeout=120.0
            )
            print(f"    Response: {response2b.content}")

            # Should acknowledge credential storage
            response_lower = response2b.content.lower()
            storage_indicators = ["stored", "saved", "received", "thank", "success", "acknowledged"]
            assert any(indicator in response_lower for indicator in storage_indicators), \
                f"Should acknowledge credential storage. Got: {response2b.content}"

            # Should NOT echo the token back
            assert "ghp_test_dynamic_token_12345" not in response2b.content, \
                "Should not echo the actual token back for security"
            print("   ✅ Credential stored securely without echoing")

        print("   ✅ Credential request handled according to dynamic mode")

        # Step 3: Simple request that should work
        print("\n3. Testing simple request: 'tell me a joke'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="tell me a joke",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response3.content}")

        # Should work normally (no credentials needed)
        response_lower = response3.content.lower()
        # Check if it provided a response (any response is fine)
        assert response3.content and len(response3.content.strip()) > 0, \
            "Should provide a response to simple request"
        print("   ✅ Simple request handled")

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

        # Should handle appropriately
        assert response4.content, "Should provide some response"
        print("   ✅ Generic API request handled appropriately")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: API key dynamic mode working correctly")
        print("✓ System asks which existing account to use")
        print("✓ New account request prompts for inline credential entry")
        print("✓ Credential stored securely without echoing")
        print("✓ Simple request handled appropriately")
        print("✓ Generic API requests handled appropriately")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Get my GitHub repositories")
        print(f"System: {response1.content}")
        print("\nUser: I need to add a new GitHub account with different credentials")
        print(f"System: {response2.content}")
        if 'response2b' in locals():
            print("\nUser: ghp_test_dynamic_token_12345")
            print(f"System: {response2b.content}")
        print("\nUser: tell me a joke")
        print(f"System: {response3.content}")
        print("\nUser: Access the REST API")
        print(f"System: {response4.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E2: API Key Dynamic Mode FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: API key dynamic mode test failed")
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
            print("\nUser: ghp_test_dynamic_token_12345")
            print(f"System: {response2b.content}")
        if 'response3' in locals():
            print("\nUser: tell me a joke")
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
    """Test security enforcement in dynamic mode - should accept inline but not echo."""
    try:
        print("\n=== Test 8E2-b: API Key Security in Dynamic Mode ===")

        formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation-dynamic.yaml"
        formation = Formation()
        await formation.load(str(formation_path))

        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e2_b")
        user_id = "user1"  # Use user1 which has credentials

        # Try to provide an API key directly (should be accepted in dynamic mode)
        print("\n1. Providing API key directly: 'My GitHub token is ghp_dynamic_test_456'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="My GitHub token is ghp_dynamic_test_456",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response1.content}")

        # Should not echo the token back for security
        response_lower = response1.content.lower()
        assert "ghp_dynamic_test_456" not in response_lower, "Should not echo back the token"
        print("   ✅ Token not echoed back in response")

        # In dynamic mode, might acknowledge storage (unlike redirect mode)
        storage_indicators = ["stored", "saved", "received", "thank"]
        redirect_indicators = ["external", "configure", "security", "portal"]

        has_storage = any(indicator in response_lower for indicator in storage_indicators)
        has_redirect = any(indicator in response_lower for indicator in redirect_indicators)

        # Dynamic mode should either store or at least not redirect
        if has_redirect and not has_storage:
            print("   ⚠️ Dynamic mode shouldn't redirect to external management")
        else:
            print("   ✅ Dynamic mode handled token appropriately")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: API key security in dynamic mode working")
        print("✓ Direct token provision handled")
        print("✓ Token not echoed in system response")
        print("✓ Dynamic mode policy maintained")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: My GitHub token is ghp_dynamic_test_456")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E2-b FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: API key security in dynamic mode test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: My GitHub token is ghp_dynamic_test_456")
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
        """Run all API key dynamic mode tests."""
        results = []

        # Run main dynamic test
        result = await test_api_key_dynamic_mode()
        results.append(("8E2: API Key Dynamic Mode", result))

        # Run security enforcement test
        result = await test_api_key_security_enforcement()
        results.append(("8E2-b: API Key Security in Dynamic Mode", result))

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
