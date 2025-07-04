#!/usr/bin/env python3
"""
Main test runner for credential system tests.
Run this to execute all credential tests in order.
"""

import os
import sys
import subprocess
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def run_test(test_file: str, description: str):
    """Run a single test file and report results."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"File: {test_file}")
    print('=' * 60)
    
    result = subprocess.run(
        [sys.executable, test_file],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✅ PASSED")
    else:
        print("❌ FAILED")
        if result.stdout:
            print("\nOutput:")
            print(result.stdout)
        if result.stderr:
            print("\nErrors:")
            print(result.stderr)
    
    return result.returncode == 0


def main():
    """Run all credential tests."""
    print("CREDENTIAL SYSTEM TEST SUITE")
    print("=" * 60)
    
    # Change to tests directory
    test_dir = Path(__file__).parent
    os.chdir(test_dir)
    
    # Define test order
    tests = [
        ("test_complete_system.py", "Complete System Test - All components with database"),
        ("test_flow_triggering.py", "Clarification Flow Triggering - Agent/Overlord integration"),
        ("test_edge_cases.py", "Edge Cases - Empty values, special characters, etc."),
        ("test_cleanup_mechanism.py", "Cleanup Mechanism - TTL-based memory leak prevention"),
        ("test_nested_resolution.py", "Nested Resolution - Recursive credential placeholder handling"),
        ("test_summary_credential_system.py", "Test Summary - What we tested"),
    ]
    
    # Optional/debug tests (not run by default)
    optional_tests = [
        ("test_credential_minimal.py", "Minimal logic test"),
        ("test_credential_generic.py", "Generic approach demo"),
        ("test_overlord_credential_flow.py", "Flow explanation"),
    ]
    
    passed = 0
    failed = 0
    
    print("\nRunning main tests...")
    for test_file, description in tests:
        if Path(test_file).exists():
            if run_test(test_file, description):
                passed += 1
            else:
                failed += 1
        else:
            print(f"\n⚠️  Skipping {test_file} - file not found")
    
    print(f"\n\n{'=' * 60}")
    print("TEST RESULTS")
    print(f"{'=' * 60}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Total: {passed + failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {failed} tests failed")
        sys.exit(1)
    
    print("\nOptional tests available:")
    for test_file, description in optional_tests:
        if Path(test_file).exists():
            print(f"  - {test_file}: {description}")


if __name__ == "__main__":
    main()