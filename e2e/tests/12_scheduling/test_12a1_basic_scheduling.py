#!/usr/bin/env python3
"""
Test 12a1: Basic Scheduling Detection and Creation
Tests that the scheduler correctly detects and creates both recurring and one-off schedules.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_basic_scheduling():
    """Test basic scheduling functionality."""
    print("\n" + "="*60)
    print("TEST 12a1: Basic Scheduling Detection and Creation")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Initializing formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Test cases
        test_cases = [
            {
                "name": "Recurring Daily Schedule",
                "message": "Remind me every day at 9am to check emails",
                "expected": "scheduled successfully",
                "type": "recurring"
            },
            {
                "name": "One-off Tomorrow Schedule",
                "message": "Schedule a project review tomorrow at 3pm",
                "expected": "scheduled successfully",
                "type": "one-off"
            },
            {
                "name": "Recurring Weekly Schedule",
                "message": "Schedule team sync every Monday at 2pm",
                "expected": "scheduled successfully",
                "type": "recurring"
            },
        ]

        results = []

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[Test {i}/{len(test_cases)}] {test_case['name']}")
            print(f"  Input: {test_case['message']}")
            print(f"  Type: {test_case['type']}")

            try:
                # Send the scheduling request
                response = await overlord.chat(
                    message=test_case['message'],
                    user_id=f"test_user_{i}",
                    session_id=f"session_{i}",
                    use_async=False,
                    stream=False
                )

                # Check the response
                content = response.content if hasattr(response, 'content') else str(response)

                if test_case['expected'] in content.lower():
                    print("  ✅ SUCCESS: Job created successfully")
                    # Extract job ID if present
                    if "job id:" in content.lower():
                        job_id_start = content.lower().index("job id:") + 7
                        job_id_end = content.find(")", job_id_start) if ")" in content[job_id_start:] else len(content)
                        job_id = content[job_id_start:job_id_end].strip()
                        print(f"     Job ID: {job_id}")
                    results.append(True)
                else:
                    print(f"  ❌ FAILED: Expected '{test_case['expected']}' in response")
                    print(f"     Got: {content[:150]}...")
                    results.append(False)

            except Exception as e:
                print(f"  ❌ ERROR: {str(e)[:100]}")
                results.append(False)

        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)

        passed = sum(results)
        total = len(results)

        print(f"Passed: {passed}/{total}")

        if all(results):
            print("🎉 ALL TESTS PASSED!")
        else:
            print(f"⚠️ {total - passed} test(s) failed")

        # Cleanup
        await formation.stop_overlord()
        # # formation.stop() removed - not async  # Not async, commented out to avoid issues

        return 0 if all(results) else 1

    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_basic_scheduling())
    import os; os._exit(exit_code)
