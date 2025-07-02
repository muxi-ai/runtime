#!/usr/bin/env python3
"""Quick test status checker for Days 1-3."""

import subprocess
import time
from pathlib import Path

def count_tests(day):
    """
    Count the number of test files for a specified day, excluding helper files.
    
    Parameters:
        day (int): The day number whose test files should be counted.
    
    Returns:
        int: The number of test files matching 'test_*.py' in 'tests/day_<day>', excluding files with 'helper' in their names.
    """
    test_dir = Path(f"tests/day_{day}")
    test_files = list(test_dir.glob("test_*.py"))
    # Exclude helper files
    test_files = [f for f in test_files if "helper" not in f.name]
    return len(test_files)

def main():
    """
    Print a summary of test file counts and names for Days 1 to 3, comparing actual test files to the expected test plan.
    
    Displays the number and names of test files found in each day's test directory (excluding helper files), then prints the expected and actual test counts for each day.
    """
    print("MUXI Runtime Test Status Check")
    print("=" * 50)
    
    # Check each day
    for day in [1, 2, 3]:
        test_count = count_tests(day)
        print(f"\nDay {day}: Found {test_count} test files")
        
        # List test files
        test_dir = Path(f"tests/day_{day}")
        test_files = sorted([f.name for f in test_dir.glob("test_*.py") if "helper" not in f.name])
        for f in test_files:
            print(f"  - {f}")
    
    # Expected counts from test plan
    print("\n" + "=" * 50)
    print("Test Plan Expectations:")
    print("- Day 1: 8 foundation tests (2 groups: 1A, 1B)")
    print("- Day 2: 20+ memory tests (7 groups: 2A-2G)")  
    print("- Day 3: 36 multimodal tests (10 groups: 3A-3J)")
    
    print("\nActual Implementation:")
    print(f"- Day 1: {count_tests(1)} test files")
    print(f"- Day 2: {count_tests(2)} test files")
    print(f"- Day 3: {count_tests(3)} test files")

if __name__ == "__main__":
    main()