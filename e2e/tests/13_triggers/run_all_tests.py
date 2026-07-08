#!/usr/bin/env python3
"""
Run all trigger system E2E tests.

Test Suite 13: Trigger System
- 13A: Basic functionality tests
- 13B: Error handling tests

Tests are discovered dynamically from test_13*.py files in this directory.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def run_test(test_file: Path) -> Tuple[str, bool, str]:
    """
    Run a single test file.
    
    Returns:
        Tuple of (test_name, success, output)
    """
    test_name = test_file.stem
    print(f"\n{'='*70}")
    print(f"Running: {test_name}")
    print(f"{'='*70}\n")
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_file)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        success = result.returncode == 0
        output = result.stdout + result.stderr
        
        if success:
            print(f"✅ {test_name} PASSED")
        else:
            print(f"❌ {test_name} FAILED")
            print(f"\nOutput:\n{output[-500:]}")  # Last 500 chars
        
        return test_name, success, output
        
    except subprocess.TimeoutExpired:
        print(f"⏱️ {test_name} TIMEOUT")
        return test_name, False, "Test timed out after 60 seconds"
    except Exception as e:
        print(f"💥 {test_name} ERROR: {e}")
        return test_name, False, str(e)


def main():
    """Run all trigger tests."""
    print("🚀 MUXI Runtime - Trigger System E2E Test Suite")
    print("="*70)
    
    test_dir = Path(__file__).parent

    # Discover tests dynamically (sorted for deterministic order)
    test_files = sorted(test_dir.glob("test_13*.py"))

    print(f"\nFound {len(test_files)} test files")

    results: List[Tuple[str, bool, str]] = []

    for test_file in test_files:
        test_name, success, output = run_test(test_file)
        results.append((test_name, success, output))
        
        # Small delay between tests to allow cleanup
        import time
        time.sleep(2)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUITE SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, success, _ in results if success)
    failed = len(results) - passed
    
    print(f"\nTotal: {len(results)} tests")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    
    print("\nDetailed Results:")
    for test_name, success, _ in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - {test_name}")
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
