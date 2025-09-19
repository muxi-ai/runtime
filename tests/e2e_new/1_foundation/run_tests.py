#!/usr/bin/env python3
"""Runner for Area 1 foundation tests."""

import sys
import time

# Import test modules
from test_1a6_simple_formation import TestSimpleFormation
from test_1b1_single_agent_response import TestSingleAgentResponse
from test_1b4_simple_chat import TestSimpleChat


def run_all_tests():
    """Run all Area 1 foundation tests."""
    print("\n" + "="*60)
    print("AREA 1: FOUNDATION TESTS (Standardized)")
    print("="*60)

    tests_passed = []
    tests_failed = []

    # List of tests to run
    test_cases = [
        (TestSimpleFormation, "test_1a6_simple_formation"),
        (TestSingleAgentResponse, "test_1b1_single_agent_response"),
        (TestSingleAgentResponse, "test_1b1_response_consistency"),
        (TestSimpleChat, "test_1b4_simple_chat"),
    ]

    total_start = time.time()

    for test_class, test_method in test_cases:
        print(f"\n{'='*40}")
        print(f"Running: {test_class.__name__}.{test_method}")
        print(f"{'='*40}")

        try:
            test_instance = test_class()
            method = getattr(test_instance, test_method)
            method()
            tests_passed.append(f"{test_class.__name__}.{test_method}")
        except Exception as e:
            tests_failed.append(f"{test_class.__name__}.{test_method}: {str(e)}")
            print(f"\n❌ Test failed: {str(e)}")

    total_duration = time.time() - total_start

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total Duration: {total_duration:.2f}s")
    print(f"Tests Passed: {len(tests_passed)}")
    print(f"Tests Failed: {len(tests_failed)}")

    if tests_passed:
        print("\n✅ Passed Tests:")
        for test in tests_passed:
            print(f"  - {test}")

    if tests_failed:
        print("\n❌ Failed Tests:")
        for test in tests_failed:
            print(f"  - {test}")

    return len(tests_failed) == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)