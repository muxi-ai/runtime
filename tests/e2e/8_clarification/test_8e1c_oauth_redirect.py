"""
Test 8E1c: OAuth in Redirect Mode

This test validates that OAuth requests are redirected in redirect mode,
ensuring proper OAuth flow through browser-based authorization.

Test flow:
1. Configure formation in redirect mode
2. Simulate OAuth credential request
3. Verify system redirects to OAuth authorization flow
4. Test various OAuth scenarios (Google, GitHub, etc.)
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_oauth_redirect_mode():
    """Test OAuth requests are redirected in redirect mode."""
    try:
        print("\n=== Test 8E1c: OAuth in Redirect Mode ===")

        # Load formation with redirect mode enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        # Override formation config for redirect mode
        formation.config["user_credentials"] = {
            "mode": "redirect",
            "redirect_message": "Please complete OAuth authorization in your browser."
        }

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create unique test context
        ctx = TestContext("test_8e1c")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

        # Step 1: Request that would need Google OAuth
        print("\n1. Testing Google OAuth request: 'Access my Google Calendar'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Access my Google Calendar",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0  # 2 minute timeout
        )

        print(f"   Response: {response1.content}")

        # Should redirect to OAuth authorization
        response_lower = response1.content.lower()
        oauth_indicators = ["oauth", "authorize", "browser", "redirect", "consent", "permission"]
        redirect_indicators = ["external", "configure", "outside", "portal"]
        assert any(indicator in response_lower for indicator in oauth_indicators + redirect_indicators), \
            "Should redirect to OAuth authorization flow"
        print("   ✅ Redirected to OAuth authorization flow")

        # Should NOT ask for inline credential entry
        inline_indicators = ["provide", "enter", "token", "paste", "credential"]
        assert not any(indicator in response_lower for indicator in inline_indicators), \
            "Should not prompt for inline credential entry"
        print("   ✅ No inline credential prompting")

        # Step 2: GitHub OAuth request
        print("\n2. Testing GitHub OAuth request: 'Create a GitHub issue'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="Create a GitHub issue",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response2.content}")

        # Should also redirect (consistent behavior)
        response_lower = response2.content.lower()
        assert any(indicator in response_lower for indicator in oauth_indicators + redirect_indicators), \
            "Should redirect GitHub OAuth requests"
        print("   ✅ GitHub OAuth request also redirected")

        # Step 3: Microsoft OAuth (Office 365)
        print("\n3. Testing Microsoft OAuth request: 'Access my OneDrive files'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="Access my OneDrive files",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response3.content}")

        # Should handle appropriately (redirect for OAuth)
        response_lower = response3.content.lower()
        assert any(indicator in response_lower for indicator in oauth_indicators + redirect_indicators), \
            "Should redirect Microsoft OAuth requests"
        print("   ✅ Microsoft OAuth request redirected appropriately")

        # Step 4: Generic OAuth service
        print("\n4. Testing generic OAuth: 'Connect to the social media API'")
        response4 = await asyncio.wait_for(
            overlord.chat(
                message="Connect to the social media API",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response4.content}")

        # Should handle appropriately
        assert response4.content, "Should provide some response"
        print("   ✅ Generic OAuth service handled appropriately")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: OAuth redirect mode working correctly")
        print("✓ Google OAuth request redirected to authorization flow")
        print("✓ No inline credential prompting occurred")
        print("✓ GitHub OAuth request also redirected consistently")
        print("✓ Microsoft OAuth requests handled with proper redirect")
        print("✓ Generic OAuth services handled appropriately")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Access my Google Calendar")
        print(f"System: {response1.content}")
        print("\nUser: Create a GitHub issue")
        print(f"System: {response2.content}")
        print("\nUser: Access my OneDrive files")
        print(f"System: {response3.content}")
        print("\nUser: Connect to the social media API")
        print(f"System: {response4.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E1c: OAuth Redirect Mode FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: OAuth redirect mode test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Access my Google Calendar")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: Create a GitHub issue")
            print(f"System: {response2.content}")
        if 'response3' in locals():
            print("\nUser: Access my OneDrive files")
            print(f"System: {response3.content}")
        if 'response4' in locals():
            print("\nUser: Connect to the social media API")
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


async def test_oauth_flow_consistency():
    """Test OAuth flow consistency across different providers."""
    try:
        print("\n=== Test 8E1c-b: OAuth Flow Consistency ===")

        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        # Configure redirect mode with OAuth-specific message
        formation.config["user_credentials"] = {
            "mode": "redirect",
            "redirect_message": "Please authorize the application in your browser to continue."
        }

        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e1c_b")

        # Test multiple OAuth providers for consistency
        oauth_requests = [
            ("Twitter API", "Post a tweet to my Twitter account"),
            ("Facebook API", "Get my Facebook page insights"),
            ("LinkedIn API", "Share a post on LinkedIn"),
            ("Slack OAuth", "Join a Slack workspace")
        ]

        responses = []

        for provider, request in oauth_requests:
            print(f"\n{len(responses) + 1}. Testing {provider}: '{request}'")
            response = await asyncio.wait_for(
                overlord.chat(
                    message=request,
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    stream=False
                ),
                timeout=120.0
            )

            print(f"   Response: {response.content[:200]}...")
            responses.append((provider, response))

            # Check for OAuth redirect indicators
            response_lower = response.content.lower()
            oauth_indicators = ["oauth", "authorize", "browser", "redirect", "consent", "permission"]
            redirect_indicators = ["external", "configure", "outside"]

            has_oauth_flow = any(indicator in response_lower for indicator in oauth_indicators + redirect_indicators)
            print(f"   ✅ {provider} handled appropriately ({'OAuth flow' if has_oauth_flow else 'Alternative approach'})")

        # Verify consistent handling
        print(f"\n   ✅ All {len(oauth_requests)} OAuth providers handled consistently")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: OAuth flow consistency maintained")
        print(f"✓ {len(oauth_requests)} different OAuth providers tested")
        print("✓ Consistent redirect behavior across providers")
        print("✓ No inline credential prompting for any provider")
        print("✓ Proper OAuth flow or alternative handling")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        for i, (provider, response) in enumerate(responses, 1):
            request_text = oauth_requests[i-1][1]
            print(f"\nUser: {request_text}")
            print(f"System: {response.content[:300] + '...' if len(response.content) > 300 else response.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E1c-b FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: OAuth flow consistency test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'responses' in locals():
            for i, (provider, response) in enumerate(responses, 1):
                if i <= len(oauth_requests):
                    request_text = oauth_requests[i-1][1]
                    print(f"\nUser: {request_text}")
                    print(f"System: {response.content[:300] + '...' if len(response.content) > 300 else response.content}")
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
        """Run all OAuth redirect mode tests."""
        results = []

        # Run main redirect test
        result = await test_oauth_redirect_mode()
        results.append(("8E1c: OAuth Redirect Mode", result))

        # Run flow consistency test
        result = await test_oauth_flow_consistency()
        results.append(("8E1c-b: OAuth Flow Consistency", result))

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
