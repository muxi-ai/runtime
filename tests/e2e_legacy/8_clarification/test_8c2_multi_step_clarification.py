#!/usr/bin/env python3
"""
Area 8 - Test Group 8C: Multiple Clarification Sequences
Test 8C2: Multi-step Clarification

Tests handling of multiple clarification steps where each clarification
may lead to additional clarifications.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_8c2_nested_clarifications():
    """Test nested clarification sequences."""
    print("\n=== Test 8C2: Multi-step Clarification ===")

    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    # Create unique test context
    ctx = TestContext("test_8c2")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

    try:
        # Step 1: Initial ambiguous request
        print("\n1. Initial ambiguous request...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "Set up the integration",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,  # 2 minute timeout
        )
        print(f"Response: {response1.content}")

        # Should ask what kind of integration
        response_lower = response1.content.lower()
        assert any(
            word in response_lower
            for word in ["what", "which", "integration", "service", "system", "clarify"]
        ), "Should ask for clarification about integration type"

        # Step 2: Provide partial clarification (still ambiguous)
        print("\n2. Partial clarification (payment integration)...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "Payment integration", user_id=ctx.user_id, session_id=ctx.session_id, stream=False
            ),
            timeout=120.0,  # 2 minute timeout
        )
        print(f"Response: {response2.content}")

        # Should ask which payment provider
        response_lower = response2.content.lower()
        assert any(
            word in response_lower
            for word in ["which", "what", "provider", "stripe", "paypal", "square"]
        ), "Should ask for clarification about payment provider"

        # Step 3: Another clarification needed
        print("\n3. Specifying payment provider...")
        response3 = await asyncio.wait_for(
            overlord.chat("Stripe", user_id=ctx.user_id, session_id=ctx.session_id, stream=False),
            timeout=120.0,  # 2 minute timeout
        )
        print(f"Response: {response3.content}")

        # Might ask about environment or implementation details
        response_lower = response3.content.lower()
        # Should now have enough context to provide guidance
        assert any(
            term in response_lower
            for term in ["stripe", "api", "key", "webhook", "checkout", "payment"]
        ), "Should provide Stripe-specific guidance"

        # Step 4: Follow-up question using full context
        print("\n4. Follow-up with all context available...")
        response4 = await asyncio.wait_for(
            overlord.chat(
                "What test cards should I use?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,  # 2 minute timeout
        )
        print(f"Response: {response4.content}")

        # Should provide Stripe test card information
        response_lower = response4.content.lower()
        assert any(
            term in response_lower for term in ["4242", "test", "card", "stripe"]
        ), "Should provide Stripe test card information"

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Multi-step clarification handled correctly")
        print("✓ Initial request triggered integration type clarification")
        print("✓ Payment integration triggered provider clarification")
        print("✓ Stripe selection provided specific guidance")
        print("✓ Test card question used full Stripe context")
        print("\n" + "=" * 40)

        print("\n### Chat transcript:")
        print("\nUser: Set up the integration")
        print(
            f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}"
        )
        print("\nUser: Payment integration")
        print(
            f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}"
        )
        print("\nUser: Stripe")
        print(
            f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
        )
        print("\nUser: What test cards should I use?")
        print(
            f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}"
        )
        print("\n" + "=" * 40)
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8C2 FAILED: {e}")
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
            print(
                f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}"
            )
        if "response2" in locals():
            print("\nUser: Payment integration")
            print(
                f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}"
            )
        if "response3" in locals():
            print("\nUser: Stripe")
            print(
                f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
            )
        if "response4" in locals():
            print("\nUser: What test cards should I use?")
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


async def test_8c2_branching_clarifications():
    """Test clarification that branches into multiple paths."""
    print("\n=== Test 8C2b: Branching Clarification Paths ===")

    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    # Create unique test context
    ctx = TestContext("test_8c2b")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

    try:
        # Initial request with multiple ambiguities
        print("\n1. Request with multiple ambiguities...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "Deploy the application",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,  # 2 minute timeout
        )
        print(f"Response: {response1.content}")

        # Should ask about deployment target
        response_lower = response1.content.lower()
        assert any(
            word in response_lower
            for word in ["where", "which", "platform", "aws", "cloud", "environment"]
        ), "Should ask about deployment target"

        # Branch 1: Specify cloud provider
        print("\n2. Branch 1: Specifying AWS...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "Deploy to AWS", user_id=ctx.user_id, session_id=ctx.session_id, stream=False
            ),
            timeout=120.0,  # 2 minute timeout
        )
        print(f"Response: {response2.content}")

        # Should ask about AWS service or application type
        response_lower = response2.content.lower()
        assert any(
            term in response_lower
            for term in ["ec2", "ecs", "lambda", "elastic", "service", "which"]
        ), "Should ask about AWS service or need more details"

        # Branch 2: Specify application type
        print("\n3. Branch 2: Specifying containerized app...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                "It's a containerized Node.js application",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,  # 2 minute timeout
        )
        print(f"Response: {response3.content}")

        # Should now provide specific deployment guidance
        response_lower = response3.content.lower()
        assert any(
            term in response_lower for term in ["ecs", "eks", "fargate", "docker", "container"]
        ), "Should suggest container services for AWS"

        # Final clarification based on both branches
        print("\n4. Question using both clarifications...")
        response4 = await asyncio.wait_for(
            overlord.chat(
                "Should I use ECS or EKS?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0,  # 2 minute timeout
        )
        print(f"Response: {response4.content}")

        # Should compare ECS vs EKS for Node.js containers
        response_lower = response4.content.lower()
        assert (
            "ecs" in response_lower and "eks" in response_lower
        ), "Should compare both ECS and EKS"
        assert any(
            term in response_lower for term in ["node", "container", "docker"]
        ), "Should maintain Node.js container context"

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Branching clarifications handled correctly")
        print("✓ Initial request triggered deployment platform clarification")
        print("✓ AWS selection triggered service type clarification")
        print("✓ Container app info provided specific guidance")
        print("✓ ECS vs EKS question maintained full context")
        print("\n" + "=" * 40)

        print("\n### Chat transcript:")
        print("\nUser: Deploy the application")
        print(
            f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}"
        )
        print("\nUser: Deploy to AWS")
        print(
            f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}"
        )
        print("\nUser: It's a containerized Node.js application")
        print(
            f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
        )
        print("\nUser: Should I use ECS or EKS?")
        print(
            f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}"
        )
        print("\n" + "=" * 40)
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8C2b FAILED: {e}")
        import traceback

        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("❌ FAILED: Branching clarification test failed")
        print(f"✗ Error: {e}")
        print("\n" + "=" * 40)

        print("\n### Partial Chat transcript (before failure):")
        if "response1" in locals():
            print("\nUser: Deploy the application")
            print(
                f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}"
            )
        if "response2" in locals():
            print("\nUser: Deploy to AWS")
            print(
                f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}"
            )
        if "response3" in locals():
            print("\nUser: It's a containerized Node.js application")
            print(
                f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}"
            )
        if "response4" in locals():
            print("\nUser: Should I use ECS or EKS?")
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


if __name__ == "__main__":

    async def run_tests():
        """Run all multi-step clarification tests."""
        results = []

        # Run nested clarifications test
        result = await test_8c2_nested_clarifications()
        results.append(("8C2: Nested Clarifications", result))

        # Run branching clarifications test
        result = await test_8c2_branching_clarifications()
        results.append(("8C2b: Branching Clarifications", result))

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
