#\!/usr/bin/env python3
"""Run all Day 8 tests for clarification system."""

import asyncio
import subprocess
import sys
from pathlib import Path

# Test files for Day 8A
DAY_8A_TESTS = [
    "test_8a1_ambiguous_request.py",
    "test_8a2_multi_agent_clarification.py", 
    "test_8a3_credential_clarification.py",
]

async def run_test(test_file):
    """Run a single test file."""
    print(f"\n{'='*60}")
    print(f"Running {test_file}")
    print('='*60)
    
    test_path = Path(__file__).parent / test_file
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_path)],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout per test
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print(f"❌ Test {test_file} timed out after 2 minutes")
        return False
    except Exception as e:
        print(f"❌ Error running {test_file}: {e}")
        return False


async def main():
    """Run all Day 8 tests."""
    print("\n" + "="*60)
    print("DAY 8: Clarification & Enhanced Information Flow Tests")
    print("Part 1: Base Clarification Testing (8A)")
    print("="*60)
    
    results = {}
    
    # Run Day 8A tests
    print("\n### Test Group 8A: Single Clarification Patterns ###")
    for test_file in DAY_8A_TESTS:
        results[test_file] = await run_test(test_file)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_file, passed_test in results.items():
        status = "✅ PASSED" if passed_test else "❌ FAILED"
        print(f"{test_file}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All Day 8A tests passed\!")
    else:
        print(f"\n⚠️ {total - passed} tests failed")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
