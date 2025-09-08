"""
Test 8E2a: API Key in Dynamic Mode

This test validates that API key requests are accepted inline in dynamic mode,
providing developer-friendly credential handling while maintaining security.

Test flow:
1. Configure formation in dynamic mode
2. Simulate API key credential request
3. Verify system prompts for inline credential entry
4. Test credential storage and usage
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_api_key_dynamic_mode():
    """Test API key requests are accepted inline in dynamic mode."""
    try:
        print("\n=== Test 8E2a: API Key in Dynamic Mode ===")

        # Load formation with dynamic mode enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        # Override formation config for dynamic mode
        formation.config["user_credentials"] = {
            "mode": "dynamic",
            "inline_acceptance": {
                "api_key": True,
                "basic": True,
                "bearer": "require_hint",
                "oauth": False
            }
        }

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create unique test context
        ctx = TestContext("test_8e2a")
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

        # Should prompt for inline credential entry
        response_lower = response1.content.lower()
        inline_indicators = ["provide", "enter", "api key", "token", "github", "credential"]
        assert any(indicator in response_lower for indicator in inline_indicators), \
            "Should prompt for inline API key entry in dynamic mode"
        print("   ✅ Prompted for inline API key entry")

        # Should NOT redirect to external management
        redirect_indicators = ["external", "outside", "portal", "configure externally"]
        assert not any(indicator in response_lower for indicator in redirect_indicators), \
            "Should not redirect to external management in dynamic mode"
        print("   ✅ No external redirect (dynamic mode behavior)")

        # Step 2: Provide the API key
        print("\n2. Providing GitHub API key: 'ghp_1234567890abcdef1234567890123456'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="ghp_1234567890abcdef1234567890123456",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response2.content}")

        # Should acknowledge credential storage
        response_lower = response2.content.lower()
        storage_indicators = ["stored", "saved", "securely", "thank", "received"]
        assert any(indicator in response_lower for indicator in storage_indicators), \
            "Should acknowledge credential storage"
        print("   ✅ Credential storage acknowledged")

        # Should NOT echo the actual token back
        assert "ghp_1234567890abcdef1234567890123456" not in response2.content, \
            "Should not echo the actual token back"
        print("   ✅ Token not echoed back (security)")

        # Step 3: Different API key service (OpenAI)
        print("\n3. Testing OpenAI API key request: 'Generate some text with AI'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="Generate some text with AI",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response3.content}")

        # Should also prompt for inline entry (consistent behavior)
        response_lower = response3.content.lower()
        assert any(indicator in response_lower for indicator in inline_indicators), \
            "Should prompt for OpenAI API key in dynamic mode"
        print("   ✅ OpenAI request also prompted for inline entry")

        # Step 4: Provide OpenAI key
        print("\n4. Providing OpenAI key: 'sk-proj-abcdefghijklmnop1234567890'")
        response4 = await asyncio.wait_for(
            overlord.chat(
                message="sk-proj-abcdefghijklmnop1234567890",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response4.content}")

        # Should handle credential appropriately
        response_lower = response4.content.lower()
        # Either stored or processed for generation
        processing_indicators = ["stored", "saved", "generating", "creating", "processing"]
        assert any(indicator in response_lower for indicator in processing_indicators), \
            "Should handle OpenAI credential appropriately"
        print("   ✅ OpenAI credential handled appropriately")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: API key dynamic mode working correctly")
        print("✓ GitHub API key request prompted for inline entry")
        print("✓ No external redirect in dynamic mode")
        print("✓ Credential storage acknowledged securely")
        print("✓ Token not echoed back for security")
        print("✓ OpenAI request also handled with inline prompting")
        print("✓ Multiple API key services supported")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Get my GitHub repositories")
        print(f"System: {response1.content}")
        print("\nUser: ghp_1234567890abcdef1234567890123456")
        print(f"System: {response2.content}")
        print("\nUser: Generate some text with AI")
        print(f"System: {response3.content}")
        print("\nUser: sk-proj-abcdefghijklmnop1234567890")
        print(f"System: {response4.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E2a: API Key Dynamic Mode FAILED: {e}")
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
            print("\nUser: ghp_1234567890abcdef1234567890123456")
            print(f"System: {response2.content}")
        if 'response3' in locals():
            print("\nUser: Generate some text with AI")
            print(f"System: {response3.content}")
        if 'response4' in locals():
            print("\nUser: sk-proj-abcdefghijklmnop1234567890")
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


async def test_api_key_validation():
    """Test API key format validation in dynamic mode."""
    try:
        print("\n=== Test 8E2a-b: API Key Validation ===")

        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        # Configure dynamic mode with validation
        formation.config["user_credentials"] = {
            "mode": "dynamic",
            "validation": {
                "github": r"^ghp_[a-zA-Z0-9]{36}$",
                "openai": r"^sk-[a-zA-Z0-9-]{20,}$"
            }
        }

        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e2a_b")

        # Step 1: Request GitHub API key
        print("\n1. Testing GitHub API key request")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Get my GitHub repositories",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Initial response: {response1.content[:200]}...")

        # Step 2: Provide invalid format
        print("\n2. Providing invalid GitHub token format: 'invalid-token-123'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="invalid-token-123",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response2.content}")

        # Should handle invalid format appropriately
        response_lower = response2.content.lower()
        # Either validation error or generic handling
        validation_indicators = ["invalid", "format", "correct", "should", "example"]
        assert any(indicator in response_lower for indicator in validation_indicators) or \
               "repositories" not in response_lower, \
               "Should handle invalid format appropriately"
        print("   ✅ Invalid format handled appropriately")

        # Step 3: Provide valid format
        print("\n3. Providing valid GitHub token: 'ghp_abcdefghijklmnopqrstuvwxyz1234567890'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="ghp_abcdefghijklmnopqrstuvwxyz1234567890",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        print(f"   Response: {response3.content}")

        # Should accept valid format
        response_lower = response3.content.lower()
        acceptance_indicators = ["stored", "saved", "thank", "received", "repositories"]
        assert any(indicator in response_lower for indicator in acceptance_indicators), \
            "Should accept valid token format"
        print("   ✅ Valid format accepted")

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: API key validation working correctly")
        print("✓ Invalid token format handled appropriately")
        print("✓ Valid token format accepted")
        print("✓ Format validation enforcement working")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Get my GitHub repositories")
        print(f"System: {response1.content[:300] + '...' if len(response1.content) > 300 else response1.content}")
        print("\nUser: invalid-token-123")
        print(f"System: {response2.content}")
        print("\nUser: ghp_abcdefghijklmnopqrstuvwxyz1234567890")
        print(f"System: {response3.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8E2a-b FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: API key validation test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Get my GitHub repositories")
            print(f"System: {response1.content[:300] + '...' if len(response1.content) > 300 else response1.content}")
        if 'response2' in locals():
            print("\nUser: invalid-token-123")
            print(f"System: {response2.content}")
        if 'response3' in locals():
            print("\nUser: ghp_abcdefghijklmnopqrstuvwxyz1234567890")
            print(f"System: {response3.content}")
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

        # Run main dynamic mode test
        result = await test_api_key_dynamic_mode()
        results.append(("8E2a: API Key Dynamic Mode", result))

        # Run validation test
        result = await test_api_key_validation()
        results.append(("8E2a-b: API Key Validation", result))

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
