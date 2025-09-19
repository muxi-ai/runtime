#!/usr/bin/env python3
"""
Test 12D1: Error Scenarios
Tests error handling for invalid scheduling requests.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_error_scenarios():
    """Test error handling for various invalid scheduling scenarios."""
    print("\n" + "="*60)
    print("TEST 12D1: Error Scenarios")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        test_cases = [
            {
                "name": "Invalid cron expression",
                "input": "Schedule task with cron: invalid_cron",
                "expect_error": True
            },
            {
                "name": "Past time scheduling",
                "input": "Schedule meeting yesterday at 3pm",
                "expect_error": True
            },
            {
                "name": "Ambiguous time",
                "input": "Schedule task sometime",
                "expect_error": False  # Should handle gracefully
            }
        ]

        passed = 0
        failed = 0

        for test_case in test_cases:
            print(f"\n[Test] {test_case['name']}")
            print(f"  Input: {test_case['input']}")

            try:
                # Add timeout to prevent infinite loops
                response = await asyncio.wait_for(
                    overlord.chat(
                        test_case['input'],
                        user_id="test_user",
                        session_id=f"test_session_{test_case['name'].replace(' ', '_')}",  # Unique session per test
                        use_async=False,
                        stream=False
                    ),
                    timeout=10.0  # 10 second timeout
                )

                content = response.content if hasattr(response, 'content') else str(response)

                if test_case['expect_error']:
                    # Should indicate error or not schedule
                    if "error" in content.lower() or "cannot" in content.lower() or \
                       "invalid" in content.lower() or "scheduled" not in content.lower():
                        print("  ✅ Correctly handled error case")
                        passed += 1
                    else:
                        print("  ❌ Should have indicated error")
                        print(f"     Got: {content[:100]}...")
                        failed += 1
                else:
                    # Should handle gracefully
                    if "error" not in content.lower():
                        print("  ✅ Handled gracefully")
                        passed += 1
                    else:
                        print("  ❌ Unexpected error")
                        print(f"     Got: {content[:100]}...")
                        failed += 1

            except Exception as e:
                if test_case['expect_error']:
                    print(f"  ✅ Raised expected error: {str(e)[:50]}")
                    passed += 1
                else:
                    print(f"  ❌ Unexpected exception: {str(e)[:50]}")
                    failed += 1

        print(f"\n{'='*60}")
        print(f"Results: {passed} passed, {failed} failed")

        # Cleanup
        try:
            if overlord:
                await formation.kill_overlord()
            # Note: shutdown() may cause issues, skip it for now
            # # formation.shutdown() removed - not async
        except Exception as cleanup_error:
            print(f"Warning: Cleanup error: {cleanup_error}")

        if failed == 0:
            print("✅ TEST PASSED: All error scenarios handled correctly")
            return 0
        else:
            print(f"❌ TEST FAILED: {failed} error scenarios not handled correctly")
            return 1

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_error_scenarios())
    sys.exit(exit_code)
