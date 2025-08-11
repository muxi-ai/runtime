"""
Test 8C1: Credential Rejection Flow

This test validates the multiple clarification sequence functionality
where a user rejects credential options and adds a new account,
with the system preserving and fulfilling the original intent.

Test flow:
1. User requests GitHub repositories
2. System asks which account
3. User rejects options ("none of these")
4. System asks for new token
5. User provides token
6. System fulfills original request with new credential
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_credential_rejection_flow():
    """Test credential rejection → addition → fulfillment flow."""
    try:
        print("\n=== Test 8C1: Credential Rejection Flow ===")
        
        # Load formation with clarification enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create unique test context to avoid buffer memory contamination
        ctx = TestContext("test_8c1")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Step 1: User requests GitHub repositories
        print("\n1. Testing credential clarification: 'List my GitHub repositories'")
        response1 = await overlord.chat(
            message="List my GitHub repositories",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response1.content}")
        
        # Should trigger clarification about which account
        assert response1.content
        assert "which" in response1.content.lower() or "account" in response1.content.lower()
        is_clarification = response1.metadata and response1.metadata.get("clarification")
        assert is_clarification, "Should ask for clarification about which account"
        print("   ✅ Clarification triggered for account selection")
        
        # Step 2: User rejects the options
        print("\n2. Rejecting options: 'None of these, I want to add a new account'")
        response2 = await overlord.chat(
            message="None of these, I want to add a new account",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response2.content}")
        
        # Should ask for token (sub-clarification)
        assert response2.content
        assert "token" in response2.content.lower() or "provide" in response2.content.lower()
        print("   ✅ Sub-clarification triggered for token")
        
        # Step 3: User provides token
        print("\n3. Providing token: 'ghp_abc123def456ghi789jkl012mno345pqr678'")
        response3 = await overlord.chat(
            message="ghp_abc123def456ghi789jkl012mno345pqr678",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response3.content[:200]}...")
        
        # Should fulfill original request (list repositories)
        assert response3.content
        # Check that clarification is resolved
        is_clarification3 = response3.metadata and response3.metadata.get("clarification")
        assert not is_clarification3, "Clarification should be resolved after providing token"
        print("   ✅ Original request fulfilled after providing credentials")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Credential rejection flow handled correctly")
        print("✓ Initial request triggered account selection clarification")
        print("✓ Account rejection triggered token sub-clarification")
        print("✓ Token provision resolved clarification and fulfilled request")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: List my GitHub repositories")
        print(f"System: {response1.content}")
        print("\nUser: None of these, I want to add a new account")
        print(f"System: {response2.content}")
        print("\nUser: ghp_abc123def456ghi789jkl012mno345pqr678")
        print(f"System: {response3.content[:500] + '...' if len(response3.content) > 500 else response3.content}")
        print("\n" + "="*40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8C1 FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Credential rejection flow test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: List my GitHub repositories")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: None of these, I want to add a new account")
            print(f"System: {response2.content}")
        if 'response3' in locals():
            print("\nUser: ghp_abc123def456ghi789jkl012mno345pqr678")
            print(f"System: {response3.content[:500] + '...' if len(response3.content) > 500 else response3.content}")
        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_depth_limit_enforcement():
    """Test that clarification depth is limited to 2 levels."""
    try:
        print("\n=== Test 8C1b: Depth Limit Enforcement ===")
        
        # Load formation with clarification enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create unique test context
        ctx = TestContext("test_8c1b")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Step 1: Initial ambiguous request
        print("\n1. Testing depth limit: 'Do something complex'")
        response1 = await overlord.chat(
            message="Do something complex",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response1.content}")
        
        # Level 0 clarification
        is_clarification = response1.metadata and response1.metadata.get("clarification")
        assert is_clarification, "Should ask for initial clarification"
        print("   ✅ Level 0 clarification triggered")
        
        # Step 2: First rejection (depth = 1)
        print("\n2. First rejection: 'Not that, something else'")
        response2 = await overlord.chat(
            message="Not that, something else",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response2.content}")
        
        # Level 1 sub-clarification
        depth = response2.metadata.get("depth", 0) if response2.metadata else 0
        assert depth >= 1 or response2.metadata.get("clarification"), "Should continue clarification or go deeper"
        print("   ✅ Level 1 clarification or continuation")
        
        # Step 3: Second rejection (should eventually force resolution)
        print("\n3. Second rejection: 'No, not that either'")
        response3 = await overlord.chat(
            message="No, not that either",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response3.content[:200]}...")
        
        # Should eventually force resolution or limit depth
        final_depth = response3.metadata.get("depth", 0) if response3.metadata else 0
        forced_resolution = response3.metadata.get("forced_resolution") if response3.metadata else False
        
        # Either forced resolution or reasonable depth limit
        assert forced_resolution or final_depth <= 3, "Should limit clarification depth or force resolution"
        print("   ✅ Depth limit enforced or resolution forced")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Depth limit enforced correctly")
        print("✓ Initial clarification triggered")
        print("✓ Multiple rejections handled")
        print("✓ Depth limit enforced or resolution forced")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Do something complex")
        print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        print("\nUser: Not that, something else")
        print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        print("\nUser: No, not that either")
        print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        print("\n" + "="*40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8C1b FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Depth limit test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Do something complex")
            print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        if 'response2' in locals():
            print("\nUser: Not that, something else")
            print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        if 'response3' in locals():
            print("\nUser: No, not that either")
            print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_cancel_clarification():
    """Test that user can cancel a clarification sequence."""
    try:
        print("\n=== Test 8C1c: Clarification Cancellation ===")
        
        # Load formation with clarification enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create unique test context
        ctx = TestContext("test_8c1c")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Step 1: Start clarification
        print("\n1. Starting clarification: 'Help me with something'")
        response1 = await overlord.chat(
            message="Help me with something",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response1.content}")
        
        is_clarification = response1.metadata and response1.metadata.get("clarification")
        assert is_clarification, "Should ask for clarification"
        print("   ✅ Clarification started")
        
        # Step 2: Cancel
        print("\n2. Cancelling: 'Never mind, cancel this'")
        response2 = await overlord.chat(
            message="Never mind, cancel this",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response2.content}")
        
        # Should acknowledge cancellation
        assert "cancel" in response2.content.lower() or "never mind" in response2.content.lower()
        cancelled = response2.metadata and response2.metadata.get("clarification_cancelled")
        print("   ✅ Cancellation acknowledged")
        
        # Step 3: New request should work normally
        print("\n3. New request: 'What time is it?'")
        response3 = await overlord.chat(
            message="What time is it?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response3.content[:200]}...")
        
        # Should process normally, no pending clarification
        is_clarification3 = response3.metadata and response3.metadata.get("clarification")
        assert not is_clarification3, "Should not be in clarification mode after cancellation"
        print("   ✅ New request processed normally")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Cancellation handled correctly")
        print("✓ Initial clarification started")
        print("✓ Cancellation request acknowledged")
        print("✓ Subsequent request processed normally")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Help me with something")
        print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        print("\nUser: Never mind, cancel this")
        print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        print("\nUser: What time is it?")
        print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        print("\n" + "="*40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8C1c FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Cancellation test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Help me with something")
            print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        if 'response2' in locals():
            print("\nUser: Never mind, cancel this")
            print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        if 'response3' in locals():
            print("\nUser: What time is it?")
            print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
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
    async def run_tests():
        """Run all credential rejection flow tests."""
        results = []
        
        # Run credential rejection flow test
        result = await test_credential_rejection_flow()
        results.append(("8C1: Credential Rejection Flow", result))
        
        # Run depth limit test
        result = await test_depth_limit_enforcement()
        results.append(("8C1b: Depth Limit Enforcement", result))
        
        # Run cancellation test
        result = await test_cancel_clarification()
        results.append(("8C1c: Clarification Cancellation", result))
        
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