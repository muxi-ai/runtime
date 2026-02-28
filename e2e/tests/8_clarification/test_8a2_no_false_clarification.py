#!/usr/bin/env python3
"""
Test 8A2: No False Clarification Requests
Tests that clear declarative statements and direct questions do NOT trigger clarification.

This addresses issues found in IMPORTANT_PROMPTS_TO_TEST.md where the clarification
system was incorrectly triggering on unambiguous statements.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_no_false_clarification():
    """Test that clear statements do NOT trigger clarification (false positives)."""
    print("\n" + "=" * 80)
    print("Test 8A2: No False Clarification Requests")
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

        # Test 1: Declarative statement should NOT trigger clarification
        print("\n2. Testing declarative statement (should NOT clarify)...")
        response = await overlord.chat(
            message=(
                "I am a PostgreSQL test user. My favorite database is PostgreSQL "
                "and I work with distributed systems."
            ),
            user_id="test_user",
            session_id="test_declarative_1",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        print(f"   Response received ({len(content)} chars)")

        # Check for clarification indicators (should NOT be present)
        # Use specific multi-word phrases to avoid false positives on common words
        clarification_indicators = [
            "could you specify", "could you clarify", "what assistance",
            "need more information", "what do you mean", "could you please clarify",
            "what would you like", "to better assist",
        ]
        has_clarification = any(indicator in content.lower() for indicator in clarification_indicators)

        if not has_clarification:
            print("   ✅ Declarative statement processed without false clarification")
            checks_passed.append("Declarative statement: no false clarification")
        else:
            print("   ❌ FALSE POSITIVE: Clarification triggered on clear statement")
            print(f"   Response: {content[:200]}...")
            all_passed = False

        # Wait for memory storage
        await asyncio.sleep(2)

        # Test 2: Recall question should NOT trigger clarification
        print("\n3. Testing recall question (should NOT clarify)...")
        response = await overlord.chat(
            message="What is my favorite database and what do I work with?",
            user_id="test_user",
            session_id="test_declarative_1",  # Same session
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        has_clarification = any(indicator in content.lower() for indicator in clarification_indicators)

        if not has_clarification:
            print("   ✅ Recall question processed without false clarification")
            checks_passed.append("Recall question: no false clarification")
        else:
            print("   ❌ FALSE POSITIVE: Clarification triggered on clear recall question")
            print(f"   Response: {content[:200]}...")
            all_passed = False

        # Test 3: Simple preference statement
        print("\n4. Testing preference statement (should NOT clarify)...")
        response = await overlord.chat(
            message="I prefer dark mode in my IDE",
            user_id="test_user_2",
            session_id="test_declarative_2",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        has_clarification = any(indicator in content.lower() for indicator in clarification_indicators)

        if not has_clarification:
            print("   ✅ Preference statement processed without false clarification")
            checks_passed.append("Preference statement: no false clarification")
        else:
            print("   ❌ FALSE POSITIVE: Clarification triggered on preference statement")
            all_passed = False

        # Test 4: Critical health information should NOT trigger clarification
        print("\n5. Testing critical health information (should NOT clarify)...")
        response = await overlord.chat(
            message="I'm allergic to peanuts - this is very important!",
            user_id="test_user_3",
            session_id="test_declarative_3",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        has_clarification = any(indicator in content.lower() for indicator in clarification_indicators)

        if not has_clarification:
            print("   ✅ Critical health info processed without false clarification")
            checks_passed.append("Critical health info: no false clarification")
        else:
            print("   ❌ FALSE POSITIVE: Clarification triggered on critical health statement")
            all_passed = False

        # Cleanup
        print("\n6. Cleaning up...")
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
    print(f"Checks Passed: {len(checks_passed)}/{4}")
    for check in checks_passed:
        print(f"  ✓ {check}")

    if not all_passed:
        print("\n⚠️  NOTE: False positives indicate clarification system is too aggressive.")
        print("   Clear statements should be processed directly, not questioned.")

    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_no_false_clarification())
    import os
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
