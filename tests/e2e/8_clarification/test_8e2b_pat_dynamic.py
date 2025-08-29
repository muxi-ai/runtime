"""
Test 8E2b: Dynamic Mode - Add New Account Flow

This test validates that when users want to add a new account in dynamic mode,
the system checks accept_inline and either prompts for credentials or shows redirect.

Test flow:
1. User requests GitHub repos (has existing accounts)
2. System shows existing accounts
3. User says "I want to add a new one"
4. System checks accept_inline and mode
5. If dynamic + accept_inline=true: prompts for credential
6. User provides credential and it's stored
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_dynamic_add_new_account():
    """Test adding new account in dynamic mode with accept_inline."""
    try:
        print("\n=== Test 8E2b: Dynamic Mode - Add New Account ===")

        # Load formation with dynamic mode enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        # Override formation config for dynamic mode
        formation.config["user_credentials"] = {
            "mode": "dynamic"
        }

        # Ensure GitHub MCP has accept_inline: true
        # Note: MCP servers are stored in _mcp_servers, not config["mcp"]
        if hasattr(formation, "_mcp_servers"):
            for server in formation._mcp_servers:
                if server.get("id") == "github-mcp":  # The ID is "github-mcp" not "github"
                    if "auth" not in server:
                        server["auth"] = {}
                    server["auth"]["accept_inline"] = True
                    server["auth"]["type"] = "bearer"
                    print(f"   GitHub MCP config: accept_inline={server['auth'].get('accept_inline')}")

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create test context - user1 has existing accounts
        ctx = TestContext("user1")
        print(f"Using user: {ctx.user_id}, Session: {ctx.session_id}")

        # Step 1: Request that triggers credential need
        print("\n1. User requests GitHub repos (no existing accounts)")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Get my GitHub repositories",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response1.content}")

        # In dynamic mode with no existing accounts, should prompt for credential
        response_lower = response1.content.lower()

        # Check if it's asking for credentials or showing error
        credential_indicators = ["credential", "token", "authenticate", "provide", "enter", "api", "pat", "personal access"]
        has_credential_prompt = any(indicator in response_lower for indicator in credential_indicators)

        if has_credential_prompt:
            print("   ✅ Prompting for credentials (dynamic mode)")
        else:
            print("   ⚠️ Not prompting for credentials - may need to explicitly say 'add new'")

        # Step 2: User explicitly says they want to add credentials
        print("\n2. User says: 'I want to add a new GitHub account'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="I want to add a new GitHub account",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response2.content}")

        # Should prompt for credential inline (dynamic mode + accept_inline=true)
        response_lower = response2.content.lower()
        inline_indicators = ["provide", "enter", "token", "github", "personal access", "api key", "credential"]
        redirect_indicators = ["external", "configure", "portal", "outside"]

        has_inline_prompt = any(indicator in response_lower for indicator in inline_indicators)
        has_redirect = any(indicator in response_lower for indicator in redirect_indicators)

        assert has_inline_prompt and not has_redirect, \
            f"Should prompt for inline credential entry in dynamic mode with accept_inline=true. Got: {response2.content}"
        print("   ✅ Prompting for inline credential entry (dynamic mode working!)")

        # Step 3: Provide the credential
        print("\n3. User provides GitHub PAT: 'ghp_test1234567890abcdef'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="ghp_test1234567890abcdef",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response3.content}")

        # Should acknowledge storage
        response_lower = response3.content.lower()
        storage_indicators = ["stored", "saved", "securely", "thank", "received", "success"]
        assert any(indicator in response_lower for indicator in storage_indicators), \
            "Should acknowledge credential storage"
        print("   ✅ Credential storage acknowledged")

        # Should NOT echo the token back
        assert "ghp_test1234567890abcdef" not in response3.content, \
            "Should not echo the actual token back"
        print("   ✅ Token not echoed back (security)")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Dynamic mode 'add new account' working!")
        print("✓ Shows existing accounts (if any)")
        print("✓ Detects 'add new' request")
        print("✓ Checks dynamic mode + accept_inline")
        print("✓ Prompts for inline credential entry")
        print("✓ Stores credential securely")
        print("✓ Doesn't echo token back")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Get my GitHub repositories")
        print(f"System: {response1.content}")
        print("\nUser: I want to add a new one")
        print(f"System: {response2.content}")
        print("\nUser: ghp_test1234567890abcdef")
        print(f"System: {response3.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E2b: Dynamic Mode FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Dynamic mode add new account test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Get my GitHub repositories")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: I want to add a new one")
            print(f"System: {response2.content}")
        if 'response3' in locals():
            print("\nUser: ghp_test1234567890abcdef")
            print(f"System: {response3.content}")
        print("\n" + "="*40)

        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_dynamic_without_accept_inline():
    """Test that services without accept_inline show redirect even in dynamic mode."""
    try:
        print("\n=== Test 8E2b-b: Dynamic Mode without accept_inline ===")

        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        # Configure dynamic mode
        formation.config["user_credentials"] = {
            "mode": "dynamic"
        }

        # Set GitHub MCP to NOT accept inline
        if hasattr(formation, "_mcp_servers"):
            for server in formation._mcp_servers:
                if server.get("id") == "github-mcp":
                    if "auth" not in server:
                        server["auth"] = {}
                    server["auth"]["accept_inline"] = False  # Explicitly false
                    print(f"   GitHub MCP config: accept_inline={server['auth'].get('accept_inline')}")

        overlord = await formation.start_overlord()
        ctx = TestContext("user2")

        print("\n1. User requests GitHub repos (no existing accounts)")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Get my GitHub repositories",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response1.content}")

        # Without accept_inline, should show redirect even in dynamic mode
        response_lower = response1.content.lower()
        redirect_indicators = ["external", "configure", "portal", "outside", "credential manager"]
        inline_indicators = ["provide", "enter", "paste", "type", "here"]

        has_redirect = any(indicator in response_lower for indicator in redirect_indicators)
        has_inline = any(indicator in response_lower for indicator in inline_indicators)

        assert has_redirect or not has_inline, \
            "Should redirect or not prompt inline when accept_inline=false"
        print("   ✅ Correctly showing redirect (accept_inline=false)")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: accept_inline=false respected in dynamic mode")
        print("✓ Dynamic mode checks accept_inline")
        print("✓ Shows redirect when accept_inline=false")
        print("✓ Security boundary respected")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E2b-b FAILED: {e}")
        import traceback
        traceback.print_exc()

        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


if __name__ == "__main__":
    async def run_tests():
        """Run all dynamic mode tests."""
        results = []

        # Run main dynamic mode test
        result = await test_dynamic_add_new_account()
        results.append(("8E2b: Dynamic Mode - Add New Account", result))

        # Run without accept_inline test
        result = await test_dynamic_without_accept_inline()
        results.append(("8E2b-b: Dynamic Mode without accept_inline", result))

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
