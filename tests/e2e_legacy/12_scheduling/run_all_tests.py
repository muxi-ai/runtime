#!/usr/bin/env python3
"""
Run all Area 12 Scheduling tests according to the comprehensive test plan.
"""

import asyncio
import subprocess
import sys
from pathlib import Path


def run_test(test_file: str) -> tuple[str, bool]:
    """Run a single test file and return result."""
    print(f"\n{'='*60}")
    print(f"Running: {test_file}")
    print('='*60)

    result = subprocess.run(
        [sys.executable, test_file],
        capture_output=True,
        text=True
    )

    success = result.returncode == 0
    return test_file, success


async def main():
    """Run all scheduling tests."""
    print("\n" + "="*80)
    print("AREA 12: SCHEDULING - COMPREHENSIVE TEST SUITE")
    print("="*80)

    test_dir = Path(__file__).parent
    test_files = sorted(test_dir.glob("test_12*.py"))

    # Group tests (only chat-based tests, no API-exclusive tests)
    test_groups = {
        "12A: One-time Scheduled Tasks": [],
        "12B: Recurring Jobs": [],
        "12D: Error Handling": []
    }

    for test_file in test_files:
        name = test_file.name
        if name.startswith("test_12a"):
            test_groups["12A: One-time Scheduled Tasks"].append(test_file)
        elif name.startswith("test_12b"):
            test_groups["12B: Recurring Jobs"].append(test_file)
        elif name.startswith("test_12d"):
            test_groups["12D: Error Handling"].append(test_file)

    results = []

    for group_name, group_tests in test_groups.items():
        if group_tests:
            print(f"\n{'='*60}")
            print(f"TEST GROUP: {group_name}")
            print('='*60)

            for test_file in group_tests:
                test_name, success = run_test(str(test_file))
                results.append((test_name, success))

                if success:
                    print(f"✅ {test_file.name} PASSED")
                else:
                    print(f"❌ {test_file.name} FAILED")

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\nTotal: {passed}/{total} tests passed")

    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {Path(test_name).name}")

    if passed == total:
        print(f"\n🎉 ALL {total} TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)