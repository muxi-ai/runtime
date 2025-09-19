#!/usr/bin/env python3
"""
Run all Area 1 foundation tests and report results.
"""

import subprocess
import sys
import time
from pathlib import Path

def run_test(test_file):
    """Run a single test file and return result."""
    print(f"\n{'='*60}")
    print(f"Running: {test_file.name}")
    print('='*60)

    start_time = time.time()
    try:
        # Run with timeout
        result = subprocess.run(
            [sys.executable, str(test_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        duration = time.time() - start_time

        # Check result
        if result.returncode == 0:
            print(f"✅ PASSED in {duration:.2f}s")
            # Show last few lines of output
            output_lines = result.stdout.split('\n')
            for line in output_lines[-5:]:
                if line.strip():
                    print(f"   {line}")
            return True
        else:
            print(f"❌ FAILED in {duration:.2f}s")
            print(f"   Error: {result.stderr[-200:] if result.stderr else 'Unknown error'}")
            return False

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        print(f"⏱️ TIMEOUT after {duration:.2f}s")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    """Run all tests in Area 1."""
    tests_dir = Path(__file__).parent
    test_files = sorted(tests_dir.glob('test_*.py'))

    print(f"Found {len(test_files)} tests in Area 1 Foundation")
    print(f"Running with 30s timeout per test...")

    results = {}
    start_time = time.time()

    # Run each test
    for test_file in test_files:
        results[test_file.name] = run_test(test_file)

    # Print summary
    duration = time.time() - start_time
    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed

    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)

    # List results
    for name, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {name}")

    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total time: {duration:.2f}s")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())