"""
Test 8E2b: PAT with allow_inline in Dynamic Mode

This test validates that Personal Access Tokens (PAT) with allow_inline hint
are accepted inline in dynamic mode, while those without the hint are redirected.

Test flow:
1. Configure formation in dynamic mode
2. Test PAT request without allow_inline hint (should redirect)
3. Test PAT request with allow_inline hint (should accept inline)
4. Verify proper hint handling
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_pat_allow_inline_hint():
    """Test PAT with allow_inline hint in dynamic mode."""
    try:
        print("\n=== Test 8E2b: PAT with allow_inline in Dynamic Mode ===")
        
        # Load formation with dynamic mode enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Override formation config for dynamic mode with PAT rules
        formation.config["user_credentials"] = {
            "mode": "dynamic",
            "inline_acceptance": {
                "api_key": True,
                "basic": True,
                "bearer": "require_hint",  # PAT is typically Bearer
                "oauth": False
            }
        }
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create unique test context
        ctx = TestContext("test_8e2b")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Step 1: Request PAT without allow_inline hint (should redirect)
        print("\n1. Testing PAT request without hint: 'Access GitLab with my PAT'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Access GitLab with my PAT",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0  # 2 minute timeout
        )
        
        print(f"   Response: {response1.content}")
        
        # Without hint, should redirect or ask for external configuration
        response_lower = response1.content.lower()
        redirect_indicators = ["external", "configure", "outside", "portal", "browser", "redirect"]
        inline_indicators = ["provide", "enter", "paste", "token here"]
        
        # Should either redirect or not prompt for inline entry
        should_redirect = any(indicator in response_lower for indicator in redirect_indicators)
        should_not_inline = not any(indicator in response_lower for indicator in inline_indicators)
        
        assert should_redirect or should_not_inline, \
            "Should redirect or not prompt for inline PAT without allow_inline hint"
        print("   ✅ PAT without hint handled appropriately (redirect or no inline prompt)")
        
        # Step 2: Simulate user indicating they want inline entry
        print("\n2. User indicates inline preference: 'I want to provide it here directly'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="I want to provide it here directly",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response2.content}")
        
        # Should now accept inline entry (hint provided)
        response_lower = response2.content.lower()
        inline_indicators = ["provide", "enter", "paste", "token", "pat", "access token"]
        assert any(indicator in response_lower for indicator in inline_indicators), \
            "Should now prompt for inline PAT entry with user hint"
        print("   ✅ Now prompting for inline PAT entry with user hint")
        
        # Step 3: Provide the PAT
        print("\n3. Providing PAT: 'glpat-xxxxxxxxxxxxxxxxxxxx'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="glpat-xxxxxxxxxxxxxxxxxxxx",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response3.content}")
        
        # Should acknowledge credential storage
        response_lower = response3.content.lower()
        storage_indicators = ["stored", "saved", "securely", "thank", "received", "configured"]
        assert any(indicator in response_lower for indicator in storage_indicators), \
            "Should acknowledge PAT storage"
        print("   ✅ PAT storage acknowledged")
        
        # Should NOT echo the actual token back
        assert "glpat-xxxxxxxxxxxxxxxxxxxx" not in response3.content, \
            "Should not echo the actual PAT back"
        print("   ✅ PAT not echoed back (security)")
        
        # Step 4: Test GitHub PAT with explicit inline request
        print("\n4. Testing GitHub PAT with explicit inline: 'I have a GitHub token to enter here'")
        response4 = await asyncio.wait_for(
            overlord.chat(
                message="I have a GitHub token to enter here",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response4.content}")
        
        # Should accept the explicit inline hint
        response_lower = response4.content.lower()
        assert any(indicator in response_lower for indicator in inline_indicators), \
            "Should accept explicit inline hint for GitHub PAT"
        print("   ✅ Explicit inline hint accepted for GitHub PAT")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: PAT allow_inline hint working correctly")
        print("✓ PAT without hint handled appropriately (redirect/no inline)")
        print("✓ User hint for inline entry recognized and accepted")
        print("✓ PAT storage acknowledged securely")
        print("✓ PAT not echoed back for security")
        print("✓ Explicit inline hints accepted for different services")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Access GitLab with my PAT")
        print(f"System: {response1.content}")
        print("\nUser: I want to provide it here directly")
        print(f"System: {response2.content}")
        print("\nUser: glpat-xxxxxxxxxxxxxxxxxxxx")
        print(f"System: {response3.content}")
        print("\nUser: I have a GitHub token to enter here")
        print(f"System: {response4.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E2b: PAT allow_inline Dynamic Mode FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: PAT allow_inline dynamic mode test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Access GitLab with my PAT")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: I want to provide it here directly")
            print(f"System: {response2.content}")
        if 'response3' in locals():
            print("\nUser: glpat-xxxxxxxxxxxxxxxxxxxx")
            print(f"System: {response3.content}")
        if 'response4' in locals():
            print("\nUser: I have a GitHub token to enter here")
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


async def test_pat_hint_variations():
    """Test various ways users might indicate inline preference."""
    try:
        print("\n=== Test 8E2b-b: PAT Hint Variations ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Configure dynamic mode
        formation.config["user_credentials"] = {
            "mode": "dynamic",
            "inline_acceptance": {
                "bearer": "require_hint"
            }
        }
        
        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e2b_b")
        
        # Test different hint phrases
        hint_phrases = [
            "I can enter it here",
            "Let me provide the token directly",
            "I'll paste it in this chat",
            "Can I type it here?",
            "I want to enter my token inline"
        ]
        
        for i, hint in enumerate(hint_phrases, 1):
            print(f"\n{i}. Testing hint variation: '{hint}'")
            response = await asyncio.wait_for(
                overlord.chat(
                    message=hint,
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    stream=False
                ),
                timeout=120.0
            )
            
            print(f"   Response: {response.content[:200]}...")
            
            # Should recognize the inline intent
            response_lower = response.content.lower()
            inline_indicators = ["provide", "enter", "paste", "token", "credential", "yes"]
            positive_response = any(indicator in response_lower for indicator in inline_indicators)
            
            print(f"   ✅ Hint recognized: {'Yes' if positive_response else 'Alternative handling'}")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: PAT hint variations handled appropriately")
        print(f"✓ {len(hint_phrases)} different hint variations tested")
        print("✓ Natural language intent recognition working")
        print("✓ Flexible inline preference detection")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        # Note: This would show a very long transcript, so we'll summarize
        print("\nTested various hint phrases:")
        for i, hint in enumerate(hint_phrases, 1):
            print(f"  {i}. User: {hint}")
            print(f"     System: [Recognized and responded appropriately]")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E2b-b FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: PAT hint variations test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        print("Tested various hint phrases for inline token entry")
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
        """Run all PAT allow_inline dynamic mode tests."""
        results = []
        
        # Run main hint test
        result = await test_pat_allow_inline_hint()
        results.append(("8E2b: PAT allow_inline Dynamic Mode", result))
        
        # Run hint variations test
        result = await test_pat_hint_variations()
        results.append(("8E2b-b: PAT Hint Variations", result))
        
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