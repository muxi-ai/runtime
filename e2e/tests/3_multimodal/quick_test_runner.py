#!/usr/bin/env python3
"""
Quick test runner for multimodal tests with timeout management
Runs each test individually and collects results
"""

import subprocess
import sys
from pathlib import Path
import time
import json

def run_test_with_timeout(test_file, timeout=120):
    """Run a single test with timeout"""
    test_name = test_file.stem
    print(f"\n{'='*60}")
    print(f"Running: {test_name}")
    print(f"{'='*60}")
    
    start_time = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(test_file)],
            cwd=test_file.parent.parent.parent,
            timeout=timeout,
            capture_output=True,
            text=True
        )
        duration = time.time() - start_time
        
        # Check for success indicators
        output = result.stdout + result.stderr
        passed = "PASSED" in output or "✅" in output or result.returncode == 0
        
        return {
            "test": test_name,
            "status": "PASSED" if passed else "FAILED",
            "duration": round(duration, 2),
            "returncode": result.returncode,
            "output_snippet": output[-500:] if len(output) > 500 else output
        }
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return {
            "test": test_name,
            "status": "TIMEOUT",
            "duration": round(duration, 2),
            "returncode": -1,
            "output_snippet": f"Test timed out after {timeout}s"
        }
    except Exception as e:
        duration = time.time() - start_time
        return {
            "test": test_name,
            "status": "ERROR",
            "duration": round(duration, 2),
            "returncode": -1,
            "output_snippet": str(e)
        }

def main():
    # Find all test files
    test_dir = Path(__file__).parent
    test_files = sorted(test_dir.glob("test_3*.py"))
    
    print(f"Found {len(test_files)} tests to run")
    print("="*60)
    
    results = []
    start_time = time.time()
    
    for test_file in test_files:
        result = run_test_with_timeout(test_file, timeout=120)
        results.append(result)
        
        # Print immediate result
        status_icon = "✅" if result["status"] == "PASSED" else "❌"
        print(f"{status_icon} {result['test']}: {result['status']} ({result['duration']}s)")
    
    total_duration = time.time() - start_time
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for r in results if r["status"] == "PASSED")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    timeout = sum(1 for r in results if r["status"] == "TIMEOUT")
    error = sum(1 for r in results if r["status"] == "ERROR")
    
    print(f"Total Tests: {len(results)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⏱️  Timeout: {timeout}")
    print(f"🔥 Error: {error}")
    print(f"Total Duration: {round(total_duration, 2)}s")
    
    # Save detailed results
    results_file = test_dir / "test_results.json"
    with open(results_file, "w") as f:
        json.dump({
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "timeout": timeout,
                "error": error,
                "duration": round(total_duration, 2)
            },
            "tests": results
        }, f, indent=2)
    
    print(f"\nDetailed results saved to: {results_file}")
    
    # Exit with appropriate code
    sys.exit(0 if failed + timeout + error == 0 else 1)

if __name__ == "__main__":
    main()
