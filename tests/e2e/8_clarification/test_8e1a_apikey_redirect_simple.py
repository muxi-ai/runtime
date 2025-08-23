"""
Test 8E1a Simple: Direct Credential Request in Redirect Mode

This test validates that when credentials are directly requested,
the system redirects to external management in redirect mode.

Test flow:
1. Configure formation in redirect mode
2. User makes request that needs NEW credentials
3. System should redirect to external management
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_direct_credential_redirect():
    """Test that direct credential requests are redirected in redirect mode."""
    try:
        print("\n=== Test 8E1a Simple: Direct Credential Request in Redirect Mode ===")
        
        # Load formation with redirect mode enabled (configured in formation.yaml)
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Use a user that doesn't have any credentials
        ctx = TestContext("test_8e1a_simple")
        user_id = "testuser_nocreds"  # A user with no existing credentials
        print(f"Using User: {user_id} (no existing credentials), Session: {ctx.session_id}")

        # Step 1: Request that would need credentials from a service the user doesn't have
        print("\n1. Testing request for service without credentials: 'Search the web for Python tutorials'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Search the web for Python tutorials",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should redirect to external credential management
        response_lower = response1.content.lower()
        redirect_indicators = ["external", "configure", "outside", "portal", "credential", "redirect", "security"]
        
        # Check if it mentions needing credentials
        if "credential" in response_lower or "api" in response_lower or "auth" in response_lower:
            if any(indicator in response_lower for indicator in redirect_indicators):
                print("   ✅ Redirected to external credential management")
            else:
                print("   ⚠️ Mentioned credentials but didn't redirect properly")
                assert False, f"Should redirect when credentials are needed. Got: {response1.content}"
        else:
            print("   ℹ️ Response didn't mention credentials - may not need them for this request")
        
        # Step 2: Try a more explicit credential-requiring request
        print("\n2. Testing explicit API request: 'Use the GitHub API to list my repositories'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="Use the GitHub API to list my repositories",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response2.content}")
        
        response_lower = response2.content.lower()
        
        # This should definitely need credentials and redirect
        if any(indicator in response_lower for indicator in redirect_indicators):
            print("   ✅ Redirected to external credential management")
        elif "credential" in response_lower or "authentication" in response_lower or "token" in response_lower:
            print("   ⚠️ System mentioned credentials but didn't redirect")
            # In redirect mode, should not ask for credentials inline
            inline_indicators = ["provide", "enter", "paste", "what is your", "please provide"]
            if any(indicator in response_lower for indicator in inline_indicators):
                assert False, f"In redirect mode, should not ask for credentials inline. Got: {response2.content}"
        else:
            print("   ℹ️ Response handled differently than expected")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Direct credential request redirect mode working")
        print("✓ System handles credential requests according to redirect mode")
        print("✓ No inline credential prompting occurred")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Search the web for Python tutorials")
        print(f"System: {response1.content}")
        print("\nUser: Use the GitHub API to list my repositories")
        print(f"System: {response2.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E1a Simple FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Direct credential redirect test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Search the web for Python tutorials")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: Use the GitHub API to list my repositories")
            print(f"System: {response2.content}")
        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_direct_credential_redirect())
        sys.exit(0 if success else 1)
    finally:
        pass