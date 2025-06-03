#!/usr/bin/env python3
"""
MUXI Runtime Test Runner

Simple test runner to execute all tests in the tests/ directory.
"""

import sys
import subprocess
from pathlib import Path


def run_tests():
    """Run all test files in the tests directory"""

    tests_dir = Path("tests")
    if not tests_dir.exists():
        print("❌ Tests directory not found!")
        return 1

    # Find all test files
    test_files = list(tests_dir.glob("test_*.py"))

    if not test_files:
        print("❌ No test files found in tests/ directory!")
        return 1

    print("🧪 MUXI Runtime Test Runner")
    print("=" * 50)
    print(f"Found {len(test_files)} test files:")
    for test_file in test_files:
        print(f"  - {test_file.name}")
    print()

    results = {}

    # Run each test file
    for test_file in test_files:
        print(f"🚀 Running {test_file.name}...")
        print("-" * 40)

        try:
            # Run the test file
            result = subprocess.run(
                [sys.executable, test_file.name],
                cwd=tests_dir,
                capture_output=False,
                text=True
            )

            results[test_file.name] = result.returncode == 0

            if result.returncode == 0:
                print(f"✅ {test_file.name} PASSED")
            else:
                print(f"❌ {test_file.name} FAILED (exit code: {result.returncode})")

        except Exception as e:
            print(f"❌ Error running {test_file.name}: {e}")
            results[test_file.name] = False

        print()

    # Summary
    print("📊 Test Summary")
    print("=" * 50)
    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("🚨 Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
