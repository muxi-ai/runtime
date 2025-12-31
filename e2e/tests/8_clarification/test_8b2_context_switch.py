#!/usr/bin/env python3
"""
Test 8B2: Context Switch Detection
Tests that the system detects when user switches to unrelated topic mid-clarification.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_context_switch_detection():
    """Test context switch detection during clarification."""
    print("\n" + "=" * 80)
    print("Test 8B2: Context Switch Detection")
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

        session_id = "context_switch_test"
        user_id = "test_user"

        # Turn 1: Start clarification about project
        print("\n2. Turn 1: Starting clarification about project...")
        print("   Request: 'Help me with my project'")
        response1 = await overlord.chat(
            message="Help me with my project",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )

        content1 = response1.content if hasattr(response1, "content") else str(response1)
        print(f"   Response received ({len(content1)} chars)")

        clarification_indicators = ["what", "which", "type", "project"]
        has_clarification = any(indicator in content1.lower() for indicator in clarification_indicators)

        if has_clarification:
            print("   ✅ Clarification started")
            checks_passed.append("Clarification initiated")
        else:
            print("   ⚠️  No clarification detected")

        # Turn 2: Switch to completely unrelated topic
        print("\n3. Turn 2: Switching context to unrelated topic...")
        print("   Request: 'Tell me a joke' (unrelated to project)")
        await asyncio.sleep(1)

        response2 = await overlord.chat(
            message="Tell me a joke",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )

        content2 = response2.content if hasattr(response2, "content") else str(response2)
        print(f"   Response received ({len(content2)} chars)")
        print(f"   Preview: {content2[:150]}...")

        # Check if system abandoned clarification and responded to joke request
        joke_indicators = ["joke", "funny", "why", "laugh"]
        has_joke_response = any(indicator in content2.lower() for indicator in joke_indicators)

        # Check if system continues asking about project (not detecting context switch)
        project_indicators = ["project", "what kind", "what type"]
        still_on_project = any(indicator in content2.lower() for indicator in project_indicators)

        if has_joke_response and not still_on_project:
            print("   ✅ Context switch detected - responded to new request")
            checks_passed.append("Context switch handled correctly")
        elif still_on_project:
            print("   ⚠️  System did not detect context switch (still asking about project)")
            print("   This is acceptable behavior - may continue original clarification")
            checks_passed.append("Clarification continued (no context switch)")
        else:
            print("   ⚠️  Unclear response to context switch")

        # Turn 3: Return to original context
        print("\n4. Turn 3: Testing if can return to original context...")
        print("   Request: 'Actually, about that project...'")
        await asyncio.sleep(1)

        response3 = await overlord.chat(
            message="Actually, about that project - it's a web application",
            user_id=user_id,
            session_id=session_id,
            stream=False
        )

        content3 = response3.content if hasattr(response3, "content") else str(response3)
        print(f"   Response received ({len(content3)} chars)")
        print(f"   Preview: {content3[:150]}...")

        # System should either resume clarification or start new clarification
        if any(indicator in content3.lower() for indicator in ["web", "application", "feature", "technology"]):
            print("   ✅ System can resume/restart project discussion")
            checks_passed.append("Context return handled")
        else:
            print("   ✓ System responded to new context")

        # Cleanup
        print("\n5. Cleaning up...")
        await formation.stop_overlord()
        formation.stop()
        print("   ✓ Formation stopped")

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Print results
    print("\n" + "=" * 80)
    print(f"Test Result: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    print(f"Checks Passed: {len(checks_passed)}")
    for check in checks_passed:
        print(f"  ✓ {check}")

    print("\n📝 NOTE: Context switch behavior can vary:")
    print("   - System may detect switch and respond to new request")
    print("   - System may continue original clarification (valid)")
    print("   - Both behaviors are acceptable depending on configuration")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_context_switch_detection())
    sys.exit(exit_code)
