#!/usr/bin/env python3
"""Run all Area 1 foundation tests."""

import sys
import subprocess
from pathlib import Path
import time
def run_test(test_file):
    """Run a single test file and return result."""
    print(f"\n{'='*60}")
    print(f"Running: {test_file.name}")
    print("=" * 60)

    try:
        result = subprocess.run(
            [sys.executable, str(test_file)], capture_output=True, text=True, timeout=60
        )

        # Check for SUCCESS or FAILED in output
        if "SUCCESS" in result.stdout:
            print(f"✅ {test_file.name} - PASSED")
            return True
        else:
            print(f"❌ {test_file.name} - FAILED")
            if result.stderr:
                print(f"   Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️ {test_file.name} - TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ {test_file.name} - ERROR: {e}")
        return False
def main():
    """Run all tests and report results."""
    test_dir = Path(__file__).parent
    test_files = sorted(test_dir.glob("test_*.py"))

    print(f"\nFound {len(test_files)} test files")
    print("=" * 60)

    results = {}
    start_time = time.time()

    for test_file in test_files:
        results[test_file.name] = run_test(test_file)

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results.values() if r)
    failed = len(results) - passed

    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "-" * 60)
    print(f"Total: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {(passed/len(results)*100):.1f}%")
    print(f"Duration: {time.time() - start_time:.1f}s")

    # Return exit code
    return 0 if failed == 0 else 1
if __name__ == "__main__":
    sys.exit(main())
