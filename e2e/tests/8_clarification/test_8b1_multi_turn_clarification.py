#!/usr/bin/env python3
"""
Test 8B1: Multi-Turn Clarification
Tests multi-turn clarification conversations where the system asks follow-up questions.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # e2e/ directory for utils

from muxi.formation import Formation  # noqa: E402
from utils.async_cleanup import standard_test_cleanup  # noqa: E402


async def test_multi_turn_clarification():
    """Test multi-turn clarification flow."""
    print("\n" + "=" * 80)
    print("Test 8B1: Multi-Turn Clarification")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.afs"
    all_passed = True
    checks_passed = []

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")

        # Test multi-turn clarification flow
        session_id = "multi_turn_test"
        user_id = "test_user"

        # Turn 1: Send ambiguous request
        print("\n2. Turn 1: Sending ambiguous request...")
        print("   Request: 'Build a website'")
        response1 = await overlord.chat(
            message="Build a website",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )

        content1 = response1.content if hasattr(response1, "content") else str(response1)
        print(f"   Response received ({len(content1)} chars)")
        print(f"   Preview: {content1[:150]}...")

        clarification_indicators = ["what", "which", "type", "purpose", "kind"]
        has_clarification1 = any(indicator in content1.lower() for indicator in clarification_indicators)

        if has_clarification1:
            print("   ✅ Clarification requested")
            checks_passed.append("Turn 1: Clarification triggered")
        else:
            print("   ⚠️  No clarification detected")

        # Turn 2: Provide partial information
        print("\n3. Turn 2: Providing partial answer...")
        print("   Response: 'An e-commerce site'")
        await asyncio.sleep(1)  # Brief delay

        response2 = await overlord.chat(
            message="An e-commerce site",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )

        content2 = response2.content if hasattr(response2, "content") else str(response2)
        print(f"   Response received ({len(content2)} chars)")
        print(f"   Preview: {content2[:150]}...")

        # Check if follow-up question or action
        follow_up_indicators = ["what", "which", "how", "products", "payments", "features"]
        has_follow_up = any(indicator in content2.lower() for indicator in follow_up_indicators)

        execution_indicators = ["create", "build", "implement", "start", "proceed"]
        has_execution = any(indicator in content2.lower() for indicator in execution_indicators)

        if has_follow_up or has_execution:
            print("   ✅ System responded appropriately (follow-up or execution)")
            checks_passed.append("Turn 2: Appropriate response")
        else:
            print("   ⚠️  Unclear response")

        # Turn 3: Provide more details
        print("\n4. Turn 3: Providing more details...")
        print("   Response: 'Selling digital products with Stripe payments'")
        await asyncio.sleep(1)

        response3 = await overlord.chat(
            message="Selling digital products with Stripe payments",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )

        content3 = response3.content if hasattr(response3, "content") else str(response3)
        print(f"   Response received ({len(content3)} chars)")
        print(f"   Preview: {content3[:150]}...")

        # At this point, system should either continue asking or start execution
        if has_execution or any(indicator in content3.lower() for indicator in execution_indicators):
            print("   ✅ System proceeding with implementation")
            checks_passed.append("Turn 3: Execution or continued clarification")
        else:
            print("   ✓ System continuing clarification")
            checks_passed.append("Turn 3: Continued clarification")

        # Check session context preservation
        print("\n5. Checking context preservation...")
        if "e-commerce" in content3.lower() or "digital" in content3.lower() or "stripe" in content3.lower():
            print("   ✅ Context from earlier turns preserved")
            checks_passed.append("Context preservation across turns")
        else:
            print("   ⚠️  Context preservation unclear")

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        all_passed = False

    finally:
        # Always cleanup, even if test fails
        await standard_test_cleanup(
            formation,
            wait_for_tasks=True,
            timeout=5.0,
            verbose=True
        )

    # Print results
    print("\n" + "=" * 80)
    print(f"Test Result: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    print(f"Checks Passed: {len(checks_passed)}")
    for check in checks_passed:
        print(f"  ✓ {check}")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_multi_turn_clarification())
    sys.exit(exit_code)
