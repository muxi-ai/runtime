#!/usr/bin/env python3
"""
Test 8A1: Ambiguous Request Clarification
Tests that ambiguous requests trigger the clarification system appropriately.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_ambiguous_request_clarification():
    """Test that ambiguous requests trigger clarification questions."""
    print("\n" + "=" * 80)
    print("Test 8A1: Ambiguous Request Clarification")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"
    all_passed = True
    checks_passed = []

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")

        # Check clarification system is enabled
        if overlord.clarification:
            print("   ✓ Clarification system initialized")
            checks_passed.append("Clarification system initialized")
        else:
            print("   ⚠️  Clarification system not found")
            all_passed = False

        # Test 1: Ambiguous "Build it" should trigger clarification
        print("\n2. Testing ambiguous request: 'Build it'...")
        response = await overlord.chat(
            message="Build it",
            user_id="test_user",
            session_id="test_ambiguous_1",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        print(f"   Response received ({len(content)} chars)")

        # Check for clarification indicators
        clarification_indicators = ["what", "which", "clarify", "specific", "more information"]
        has_clarification = any(indicator in content.lower() for indicator in clarification_indicators)

        if has_clarification:
            print("   ✅ Clarification requested for ambiguous 'Build it'")
            checks_passed.append("Ambiguous request triggered clarification")
        else:
            print("   ⚠️  No clarification detected")
            print(f"   Response preview: {content[:200]}...")
            all_passed = False

        # Test 2: Ambiguous "Fix the issue" should trigger clarification
        print("\n3. Testing ambiguous request: 'Fix the issue'...")
        response = await overlord.chat(
            message="Fix the issue",
            user_id="test_user_2",
            session_id="test_ambiguous_2",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        has_clarification = any(indicator in content.lower() for indicator in clarification_indicators)

        if has_clarification:
            print("   ✅ Clarification requested for ambiguous 'Fix the issue'")
            checks_passed.append("Multiple ambiguous requests handled")
        else:
            print("   ⚠️  No clarification detected for second request")

        # Cleanup
        print("\n4. Cleaning up...")
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
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    import os
    exit_code = asyncio.run(test_ambiguous_request_clarification())
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
