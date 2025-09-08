#!/usr/bin/env python3
"""
Day 1 Test Runner - Foundation Layer
Based on MUXI Runtime Comprehensive Test Plan

Note: Day 1 tests are a mix of pytest tests and standalone scripts.
This runner handles both types.
"""

import subprocess
import sys
import os
from pathlib import Path

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def run_pytest_file(test_file, description):
    """Run a pytest test file."""
    print(f"\n{BLUE}Running pytest: {description}{RESET}")
    print(f"{BLUE}File: {test_file}{RESET}\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-v"], capture_output=True, text=True
    )

    # Count passed/failed from pytest output
    passed = result.stdout.count("PASSED")
    failed = result.stdout.count("FAILED")

    if result.returncode == 0:
        print(f"{GREEN}✅ All tests passed ({passed} tests){RESET}")
    else:
        print(f"{RED}❌ Some tests failed ({failed} failed, {passed} passed){RESET}")
        if failed > 0:
            print(f"{RED}Error output:{RESET}")
            print(result.stdout[-1000:])  # Last 1000 chars

    return passed, failed


def run_script_file(test_file, description):
    """Run a standalone test script."""
    print(f"\n{BLUE}Running script: {description}{RESET}")
    print(f"{BLUE}File: {test_file}{RESET}\n")

    try:
        result = subprocess.run(
            [sys.executable, str(test_file)], capture_output=True, text=True, timeout=60
        )

        if result.returncode == 0:
            print(f"{GREEN}✅ Script completed successfully{RESET}")
            return 1, 0
        else:
            print(f"{RED}❌ Script failed{RESET}")
            print(f"{RED}Error:{RESET}")
            print(result.stderr[-1000:])
            return 0, 1

    except subprocess.TimeoutExpired:
        print(f"{RED}❌ Script timeout{RESET}")
        return 0, 1
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")
        return 0, 1


def main():
    """Run all Day 1 tests."""
    print(f"{YELLOW}{'='*80}{RESET}")
    print(f"{YELLOW}MUXI Runtime Day 1 Tests - Foundation Layer{RESET}")
    print(f"{YELLOW}{'='*80}{RESET}")

    # Set up Python path
    src_path = Path(__file__).parent.parent.parent / "src"
    os.environ["PYTHONPATH"] = str(src_path) + ":" + os.environ.get("PYTHONPATH", "")

    # Change to runtime directory so formation paths work
    runtime_dir = Path(__file__).parent.parent.parent
    os.chdir(runtime_dir)
    print(f"Working directory: {os.getcwd()}")

    total_passed = 0
    total_failed = 0

    # Test Group 1A: Formation Loading (5 tests from plan)
    print(f"\n{YELLOW}Test Group 1A: Formation Loading{RESET}")

    # Run the comprehensive test file that contains all 1A tests
    test_dir = Path(__file__).parent
    passed, failed = run_pytest_file(
        test_dir / "test_1a1_basic_yaml_formation.py",
        "Test Group 1A: Comprehensive Formation Loading Tests (5 methods)",
    )
    total_passed += passed
    total_failed += failed

    # Also run the secondary test file
    passed, failed = run_pytest_file(
        test_dir / "test_1a4_flattened_formation_loading.py",
        "Test Group 1A: Simple Formation Loading Tests (5 methods)",
    )
    total_passed += passed
    total_failed += failed

    # The other test files are standalone scripts
    for script, desc in [
        ("test_1a2_directory_structure_formation.py", "1A2: Directory Structure"),
        ("test_1a3_formation_validation_failures.py", "1A3: Validation Failures"),
    ]:
        script_path = test_dir / script
        if script_path.exists():
            p, f = run_script_file(script_path, desc)
            total_passed += p
            total_failed += f

    # Test Group 1B: Basic Agent Communication (4 tests from plan)
    print(f"\n{YELLOW}Test Group 1B: Basic Agent Communication{RESET}")

    for script, desc in [
        ("test_1b1_single_agent_response.py", "1B1: Single Agent Response"),
        ("test_1b2_agent_routing_validation.py", "1B2: Agent Routing Validation"),
    ]:
        script_path = test_dir / script
        if script_path.exists():
            p, f = run_script_file(script_path, desc)
            total_passed += p
            total_failed += f

    # Additional Tests (if we find them)
    # According to the plan, there should be 8 additional tests
    # These might be in the configuration directory
    print(f"\n{YELLOW}Additional Tests{RESET}")
    config_tests = Path(__file__).parent.parent / "configuration"
    if config_tests.exists():
        integration_file = config_tests / "test_formation_integration.py"
        if integration_file.exists():
            passed, failed = run_pytest_file(
                integration_file, "Formation Integration Tests (contains multiple tests)"
            )
            total_passed += passed
            total_failed += failed

    # Summary
    print(f"\n{YELLOW}{'='*80}{RESET}")
    print(f"{YELLOW}Day 1 Test Summary{RESET}")
    print(f"{YELLOW}{'='*80}{RESET}")
    print(f"Total tests run: {total_passed + total_failed}")
    print(f"{GREEN}Passed: {total_passed}{RESET}")
    print(f"{RED}Failed: {total_failed}{RESET}")

    # Expected from test plan
    print(f"\n{YELLOW}Day 1 Expected Results (from test plan):{RESET}")
    print("- Test Group 1A: Formation Loading (5 tests)")
    print("- Test Group 1B: Basic Agent Communication (4 tests)")
    print("- Additional Tests: (8 tests)")
    print("- Total Expected: 17 tests")

    if total_passed >= 17:
        print(f"\n{GREEN}✅ Day 1 Success Criteria Met!{RESET}")
    else:
        print(f"\n{YELLOW}⚠️  Some tests may be in other locations{RESET}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
