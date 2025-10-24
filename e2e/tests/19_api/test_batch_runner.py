#!/usr/bin/env python3
"""Batch test runner to quickly check test status."""

import subprocess
import sys
from pathlib import Path

TESTS = [
    "test_19g1_memory_sessions",
    "test_19h1_users",
    "test_19i1_memory_crud",
    "test_19j1_buffer_memory_ops",
    "test_19k1_jobs",
    "test_19l1_secrets",
    "test_19m1_admin_config",
    "test_19n1_mcp",
    "test_19o1_memory_admin",
    "test_19p1_scheduler_admin",
    "test_19q1_llm_settings",
    "test_19r1_a2a",
    "test_19s1_async_jobs",
    "test_19t1_logging",
    "test_19u1_triggers",
    "test_19v1_events_streaming",
]

def run_test(test_name):
    """Run a single test and return status."""
    test_path = Path(__file__).parent / f"{test_name}.py"
    
    try:
        result = subprocess.run(
            ["python3", str(test_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=Path(__file__).parent.parent.parent.parent,
        )
        
        # Check if test passed
        if result.returncode == 0:
            if "SUCCESS:" in result.stdout:
                return "✅ PASS"
            else:
                return "❓ UNCLEAR (exit 0 but no SUCCESS)"
        else:
            # Check for specific error types
            output = result.stdout + result.stderr
            if "AssertionError" in output:
                # Extract the assertion error
                lines = output.split('\n')
                for i, line in enumerate(lines):
                    if "AssertionError" in line:
                        # Get context
                        context = lines[max(0,i-2):i+3]
                        return f"❌ ASSERTION: {' '.join(context)}"
                return "❌ ASSERTION (details unclear)"
            elif "address already in use" in output:
                return "⚠️  PORT CONFLICT"
            elif "timeout" in output.lower():
                return "⏱️  TIMEOUT"
            else:
                return f"❌ FAIL (code {result.returncode})"
                
    except subprocess.TimeoutExpired:
        return "⏱️  TIMEOUT (60s)"
    except Exception as e:
        return f"❌ ERROR: {str(e)}"

if __name__ == "__main__":
    print("=" * 70)
    print("BATCH TEST RUNNER")
    print("=" * 70)
    print()
    
    results = {}
    for test_name in TESTS:
        print(f"Running {test_name}...", end=" ", flush=True)
        status = run_test(test_name)
        results[test_name] = status
        print(status)
        
        # Small delay between tests to avoid port conflicts
        import time
        time.sleep(3)
    
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for s in results.values() if s.startswith("✅"))
    failed = sum(1 for s in results.values() if s.startswith("❌"))
    other = len(results) - passed - failed
    
    print(f"Passed: {passed}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")
    print(f"Other:  {other}/{len(results)}")
    
    if failed > 0:
        print("\nFailed tests:")
        for test, status in results.items():
            if status.startswith("❌"):
                print(f"  - {test}: {status}")
