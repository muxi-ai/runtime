#!/usr/bin/env python3
"""
Master Test Runner - Runs all days of the MUXI Runtime Comprehensive Test Plan
"""

import subprocess
import sys
import os
from pathlib import Path

# Color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def run_day_tests(day_num, day_name):
    """Run tests for a specific day."""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}Running Day {day_num}: {day_name}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    day_dir = Path(__file__).parent / f"day_{day_num}"
    test_runner = day_dir / f"run_day{day_num}_tests.py"
    
    if not test_runner.exists():
        # Try running pytest on the directory
        print(f"{YELLOW}No dedicated runner found, checking for tests in {day_dir}{RESET}")
        if day_dir.exists():
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(day_dir), "-v"],
                capture_output=True,
                text=True
            )
        else:
            print(f"{RED}Day {day_num} directory not found{RESET}")
            return False
    else:
        # Run the dedicated test runner
        print(f"{GREEN}Running dedicated test runner: {test_runner.name}{RESET}")
        result = subprocess.run(
            [sys.executable, str(test_runner)],
            capture_output=False,  # Let it print directly
            text=True,
            cwd=str(day_dir)  # Run from the day directory
        )
    
    return result.returncode == 0

def main():
    """Run all test days in sequence."""
    print(f"{YELLOW}{'='*80}{RESET}")
    print(f"{YELLOW}MUXI Runtime Comprehensive Test Suite{RESET}")
    print(f"{YELLOW}Based on 9-Day Test Plan (June 25 - July 3, 2025){RESET}")
    print(f"{YELLOW}{'='*80}{RESET}")
    
    # Set Python path
    src_path = Path(__file__).parent.parent / "src"
    os.environ["PYTHONPATH"] = str(src_path) + ":" + os.environ.get("PYTHONPATH", "")
    
    test_days = [
        (1, "Foundation Layer"),
        (2, "Memory Systems"),
        # Future days will be added as implemented
        # (3, "Document Processing"),
        # (4, "Multi-Agent Coordination"),
        # (5, "MCP Integration & Tools"),
        # (6, "Clarification & Information Flow"),
        # (7, "Async Operations & Real-time Features"),
        # (8, "Performance & Integration Testing"),
        # (9, "Production Readiness & Scheduler"),
    ]
    
    results = []
    
    for day_num, day_name in test_days:
        success = run_day_tests(day_num, day_name)
        results.append((day_num, day_name, success))
    
    # Final summary
    print(f"\n{YELLOW}{'='*80}{RESET}")
    print(f"{YELLOW}Overall Test Summary{RESET}")
    print(f"{YELLOW}{'='*80}{RESET}\n")
    
    all_passed = True
    for day_num, day_name, success in results:
        status = f"{GREEN}✅ PASSED{RESET}" if success else f"{RED}❌ FAILED{RESET}"
        print(f"Day {day_num} ({day_name}): {status}")
        if not success:
            all_passed = False
    
    print(f"\n{YELLOW}Total Days Tested: {len(results)}{RESET}")
    print(f"{YELLOW}Target: 1,078 strategic test combinations across 17 feature dimensions{RESET}")
    
    if all_passed:
        print(f"\n{GREEN}🎉 All tests passed!{RESET}")
        return 0
    else:
        print(f"\n{RED}❌ Some tests failed. Please review the output above.{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())