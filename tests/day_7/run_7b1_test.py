#!/usr/bin/env python3
"""
Run Test 7B1: Internal A2A Communication
"""

import subprocess
import sys
import os


def run_test():
    """Run the 7B1 test with proper output."""
    print("\n" + "=" * 80)
    print("Running Day 7B Test 1: Internal A2A Communication")
    print("=" * 80)

    # Run the specific test
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/day_7/test_7b1_internal_a2a_communication.py",
        "-v",
        "-s",  # Show print statements
        "--tb=short",  # Shorter traceback
    ]

    # Execute from the runtime directory
    runtime_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    result = subprocess.run(cmd, cwd=runtime_dir)

    return result.returncode


if __name__ == "__main__":
    exit_code = run_test()
    sys.exit(exit_code)
