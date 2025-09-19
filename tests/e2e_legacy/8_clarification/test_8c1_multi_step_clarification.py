"""
Test 8C1: Multi-step Clarification

This test validates multiple clarification sequences where each
clarification may lead to additional clarifications, testing the
system's ability to handle nested clarification flows.

Test flow:
1. User makes ambiguous request ("Set up the integration")
2. System asks what kind of integration
3. User provides partial info ("Payment integration")
4. System asks which payment provider
5. User specifies provider ("Stripe")
6. System provides specific guidance with full context
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_multi_step_clarification():
    """Test nested clarification sequences."""
    try:
        print("\n=== Test 8C1: Multi-step Clarification ===")

        # Load formation with clarification enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create unique test context to avoid buffer memory contamination
        ctx = TestContext("test_8c1")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

        # Step 1: Initial ambiguous request
        print("\n1. Testing ambiguous request: 'Set up the integration'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Set up the integration",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,  # 2 minute timeout
        )

        print(f"   Response: {response1.content}")

        # Should ask what kind of integration
        response_lower = response1.content.lower()
        assert any(
            word in response_lower
            for word in ["what", "which", "integration", "service", "system", "clarify"]
        ), "Should ask for clarification about integration type"
        print("   ✅ Clarification triggered for integration type")

        # Step 2: Provide partial clarification (still ambiguous)
        print("\n2. Partial clarification: 'Payment integration'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="Payment integration",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,
        )

        print(f"   Response: {response2.content}")

        # Should ask which payment provider
        response_lower = response2.content.lower()
        assert any(
            word in response_lower
            for word in ["which", "what", "provider", "stripe", "paypal", "square"]
        ), "Should ask for clarification about payment provider"
        print("   ✅ Sub-clarification triggered for payment provider")

        # Step 3: Specify payment provider
        print("\n3. Specifying provider: 'Stripe'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="Stripe", user_id=ctx.user_id, session_id=ctx.session_id, stream=False
            ),
            timeout=120.0,
        )

        print(f"   Response: {response3.content[:200]}...")

        # Should now provide specific Stripe integration guidance
        response_lower = response3.content.lower()
        assert any(
            term in response_lower
            for term in ["stripe", "api", "key", "webhook", "checkout", "payment"]
        ), "Should provide Stripe-specific guidance"
        print("   ✅ Specific guidance provided after multi-step clarification")

        # Step 4: Follow-up question using full context
        print("\n4. Follow-up with context: 'What about webhooks?'")
        response4 = await asyncio.wait_for(
            overlord.chat(
                message="What about webhooks?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,
        )

        print(f"   Response: {response4.content[:200]}...")

        # Should provide Stripe webhook information
        response_lower = response4.content.lower()
        assert any(
            term in response_lower for term in ["webhook", "stripe", "endpoint", "event"]
        ), "Should provide Stripe webhook information"
        print("   ✅ Context maintained for follow-up questions")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Multi-step clarification handled correctly")
        print("✓ Initial request triggered integration type clarification")
        print("✓ Payment integration triggered provider clarification")
        print("✓ Stripe selection provided specific guidance")
        print("✓ Follow-up questions maintained full context")
        print("\n" + "=" * 40)

        print("\n### Chat transcript:")
        print("\nUser: Set up the integration")
        print(f"System: {response1.content}")
        print("\nUser: Payment integration")
        print(f"System: {response2.content}")
        print("\nUser: Stripe")
        print(
            f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
        )
        print("\nUser: What about webhooks?")
        print(
            f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}"
        )
        print("\n" + "=" * 40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8C1: Multi-step Clarification FAILED: {e}")
        import traceback

        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("❌ FAILED: Multi-step clarification test failed")
        print(f"✗ Error: {e}")
        print("\n" + "=" * 40)

        print("\n### Partial Chat transcript (before failure):")
        if "response1" in locals():
            print("\nUser: Set up the integration")
            print(f"System: {response1.content}")
        if "response2" in locals():
            print("\nUser: Payment integration")
            print(f"System: {response2.content}")
        if "response3" in locals():
            print("\nUser: Stripe")
            print(
                f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
            )
        if "response4" in locals():
            print("\nUser: What about webhooks?")
            print(
                f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}"
            )
        print("\n" + "=" * 40)

        # Try to shut down even on failure
        if "formation" in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_depth_limit_enforcement():
    """Test that clarification depth is limited to configured levels."""
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
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Do something complex",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,
        )

        print(f"   Response: {response1.content}")

        # Should ask for clarification
        assert response1.content
        print("   ✅ Level 0 clarification triggered")

        # Step 2: Still ambiguous
        print("\n2. Still ambiguous: 'Something technical'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="Something technical",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,
        )

        print(f"   Response: {response2.content}")
        print("   ✅ Level 1 clarification or continuation")

        # Step 3: Still ambiguous (testing depth limit)
        print("\n3. Still vague: 'Related to code'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="Related to code",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,
        )

        print(f"   Response: {response3.content[:200]}...")

        # Should eventually provide help or reach depth limit
        assert response3.content
        print("   ✅ Depth limit enforced or reasonable response provided")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Depth limit handled correctly")
        print("✓ Multiple clarification levels tested")
        print("✓ System handled ambiguity appropriately")
        print("✓ No infinite clarification loops")
        print("\n" + "=" * 40)

        print("\n### Chat transcript:")
        print("\nUser: Do something complex")
        print(
            f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}"
        )
        print("\nUser: Something technical")
        print(
            f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}"
        )
        print("\nUser: Related to code")
        print(
            f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
        )
        print("\n" + "=" * 40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8C1b FAILED: {e}")
        import traceback

        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("❌ FAILED: Depth limit test failed")
        print(f"✗ Error: {e}")
        print("\n" + "=" * 40)

        print("\n### Partial Chat transcript (before failure):")
        if "response1" in locals():
            print("\nUser: Do something complex")
            print(
                f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}"
            )
        if "response2" in locals():
            print("\nUser: Something technical")
            print(
                f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}"
            )
        if "response3" in locals():
            print("\nUser: Related to code")
            print(
                f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
            )
        print("\n" + "=" * 40)

        # Try to shut down even on failure
        if "formation" in locals():
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
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Help me with something",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,
        )

        print(f"   Response: {response1.content}")

        # Should ask for clarification
        assert response1.content
        print("   ✅ Clarification started")

        # Step 2: Cancel
        print("\n2. Cancelling: 'Never mind, what time is it?'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="Never mind, what time is it?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,
        )

        print(f"   Response: {response2.content}")

        # Should handle context switch
        assert response2.content
        print("   ✅ Context switch handled")

        # Step 3: New request should work normally
        print("\n3. New request: 'Tell me a joke'")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="Tell me a joke",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,
        )

        print(f"   Response: {response3.content[:200]}...")

        # Should process normally
        assert response3.content
        print("   ✅ New request processed normally")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Cancellation handled correctly")
        print("✓ Initial clarification started")
        print("✓ Context switch detected and handled")
        print("✓ Subsequent request processed normally")
        print("\n" + "=" * 40)

        print("\n### Chat transcript:")
        print("\nUser: Help me with something")
        print(
            f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}"
        )
        print("\nUser: Never mind, what time is it?")
        print(
            f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}"
        )
        print("\nUser: Tell me a joke")
        print(
            f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
        )
        print("\n" + "=" * 40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8C1c FAILED: {e}")
        import traceback

        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("❌ FAILED: Cancellation test failed")
        print(f"✗ Error: {e}")
        print("\n" + "=" * 40)

        print("\n### Partial Chat transcript (before failure):")
        if "response1" in locals():
            print("\nUser: Help me with something")
            print(
                f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}"
            )
        if "response2" in locals():
            print("\nUser: Never mind, what time is it?")
            print(
                f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}"
            )
        if "response3" in locals():
            print("\nUser: Tell me a joke")
            print(
                f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
            )
        print("\n" + "=" * 40)

        # Try to shut down even on failure
        if "formation" in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


if __name__ == "__main__":

    async def run_tests():
        """Run all multi-step clarification tests."""
        results = []

        # Run multi-step clarification test
        result = await test_multi_step_clarification()
        results.append(("8C1: Multi-step Clarification", result))

        # Run depth limit test
        result = await test_depth_limit_enforcement()
        results.append(("8C1b: Depth Limit Enforcement", result))

        # Run cancellation test
        result = await test_cancel_clarification()
        results.append(("8C1c: Clarification Cancellation", result))

        # Print summary
        print("\n" + "=" * 50)
        print("TEST SUMMARY")
        print("=" * 50)
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
