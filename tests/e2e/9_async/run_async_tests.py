#!/usr/bin/env python3
"""
Runner script for all async decision logic tests (9A group).
Executes tests sequentially with proper cleanup between tests.
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path


def run_test(test_file: str) -> tuple[bool, float]:
    """Run a single test file and return success status and duration."""
    print(f"\n{'='*70}")
    print(f"Running: {test_file}")
    print('='*70)
    
    start_time = time.time()
    result = subprocess.run(
        [sys.executable, test_file],
        capture_output=False,
        text=True
    )
    duration = time.time() - start_time
    
    success = result.returncode == 0
    return success, duration


async def main():
    """Run all async tests."""
    print("🚀 MUXI Runtime - Async Decision Logic Test Suite (9A)")
    print("="*70)
    print("Running all tests in sequence...")
    print("Note: Webhook server should be running on http://127.0.0.1:8765")
    print("="*70)
    
    test_dir = Path(__file__).parent
    tests = [
        "test_9a1_forced_async_mode.py",
        "test_9a2_forced_sync_mode.py", 
        "test_9a3a_simple_task_auto_sync.py",
        "test_9a3b_complex_task_auto_async.py"
    ]
    
    results = []
    total_duration = 0
    
    for test in tests:
        test_path = test_dir / test
        if test_path.exists():
            success, duration = run_test(str(test_path))
            results.append((test, success, duration))
            total_duration += duration
            
            # Brief pause between tests
            await asyncio.sleep(2)
        else:
            print(f"⚠️ Test file not found: {test}")
            results.append((test, False, 0))
    
    # Print summary
    print(f"\n{'='*70}")
    print("📊 TEST SUMMARY")
    print('='*70)
    
    passed = 0
    failed = 0
    
    for test, success, duration in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{test:<40} {status} ({duration:.2f}s)")
        if success:
            passed += 1
        else:
            failed += 1
    
    print(f"\n{'='*70}")
    print(f"Total: {passed}/{len(tests)} passed, {failed} failed")
    print(f"Total duration: {total_duration:.2f}s")
    
    if failed == 0:
        print("\n🎉 All async decision logic tests PASSED!")
        print("="*70)
        return True
    else:
        print(f"\n⚠️ {failed} test(s) failed. Check output above for details.")
        print("="*70)
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)