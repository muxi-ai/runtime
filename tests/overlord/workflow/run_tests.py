#!/usr/bin/env python3
"""
Test runner for Enhanced Overlord Workflow Testing.

This script runs the comprehensive test suite for the workflow orchestration
system, including unit tests, integration tests, and manual test scenarios.

Usage:
    python run_tests.py --unit                 # Run unit tests only
    python run_tests.py --integration          # Run integration tests only
    python run_tests.py --manual               # Run manual test scenarios
    python run_tests.py --all                  # Run all tests
    python run_tests.py --coverage             # Run with coverage report
"""

import subprocess
import sys
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
import json


class TestRunner:
    """Comprehensive test runner for workflow orchestration system."""

    def __init__(self):
        """Initialize test runner."""
        self.test_dir = Path(__file__).parent
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "unit_tests": None,
            "integration_tests": None,
            "manual_tests": None,
            "coverage": None,
        }

    def print_header(self, title: str):
        """Print formatted header."""
        print("\n" + "=" * 80)
        print(f"🧪 {title}")
        print("=" * 80)

    def print_step(self, step: str):
        """Print test step."""
        print(f"\n📋 {step}")

    def print_result(self, result: str, success: bool = True):
        """Print test result."""
        icon = "✅" if success else "❌"
        print(f"   {icon} {result}")

    def run_pytest(self, test_files: list, coverage: bool = False) -> dict:
        """Run pytest on specified test files."""
        cmd = ["python", "-m", "pytest", "-v"]

        if coverage:
            cmd.extend(
                ["--cov=muxi.overlord.workflow", "--cov-report=html", "--cov-report=term"]
            )

        cmd.extend(test_files)

        print(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.test_dir.parent.parent.parent,  # Navigate to runtime root
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Test execution timed out (5 minutes)",
                "return_code": -1,
            }
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "return_code": -1}

    def run_unit_tests(self, coverage: bool = False):
        """Run unit tests for workflow components."""
        self.print_header("Unit Tests - Core Workflow Components")

        test_files = [
            "tests/overlord/workflow/test_analyzer.py",
            "tests/overlord/workflow/test_decomposer.py",
            "tests/overlord/workflow/test_executor.py",
            "tests/overlord/workflow/test_types.py",
        ]

        # Check which test files exist
        existing_files = []
        for test_file in test_files:
            file_path = self.test_dir.parent.parent.parent / test_file
            if file_path.exists():
                existing_files.append(test_file)
                self.print_result(f"Found: {test_file}")
            else:
                self.print_result(f"Missing: {test_file}", success=False)

        if not existing_files:
            self.print_result("No unit test files found", success=False)
            self.results["unit_tests"] = {"success": False, "reason": "No test files found"}
            return

        # Run unit tests
        self.print_step("Running unit tests")
        result = self.run_pytest(existing_files, coverage=coverage)

        if result["success"]:
            self.print_result("Unit tests passed")
        else:
            self.print_result("Unit tests failed", success=False)
            print(f"STDOUT:\n{result['stdout']}")
            print(f"STDERR:\n{result['stderr']}")

        self.results["unit_tests"] = result

    def run_integration_tests(self):
        """Run integration tests for end-to-end workflow."""
        self.print_header("Integration Tests - End-to-End Workflow")

        test_file = "tests/overlord/workflow/test_integration.py"
        file_path = self.test_dir.parent.parent.parent / test_file

        if not file_path.exists():
            self.print_result(f"Integration test file not found: {test_file}", success=False)
            self.results["integration_tests"] = {"success": False, "reason": "Test file not found"}
            return

        # Run integration tests
        self.print_step("Running integration tests")
        result = self.run_pytest([test_file])

        if result["success"]:
            self.print_result("Integration tests passed")
        else:
            self.print_result("Integration tests failed", success=False)
            print(f"STDOUT:\n{result['stdout']}")
            print(f"STDERR:\n{result['stderr']}")

        self.results["integration_tests"] = result

    async def run_manual_tests(self, scenario: str = "all"):
        """Run manual test scenarios."""
        self.print_header("Manual Test Scenarios")

        # Import and run manual tests
        try:
            sys.path.append(str(self.test_dir))
            from manual_test_scenarios import ManualTestOrchestrator

            orchestrator = ManualTestOrchestrator()
            await orchestrator.setup_system(use_real_llm=False)

            self.print_step("Running manual test scenarios")

            if scenario == "all":
                await orchestrator.test_simple_request_workflow()
                await orchestrator.test_complex_request_with_approval()
                await orchestrator.test_workflow_modification()
                await orchestrator.test_parallel_execution()
                await orchestrator.test_error_handling()
            elif scenario == "simple":
                await orchestrator.test_simple_request_workflow()
            elif scenario == "complex":
                await orchestrator.test_complex_request_with_approval()
            elif scenario == "parallel":
                await orchestrator.test_parallel_execution()
            elif scenario == "error":
                await orchestrator.test_error_handling()

            orchestrator.generate_test_report()

            # Extract results
            passed = len([r for r in orchestrator.test_results.values() if r["status"] == "PASSED"])
            total = len(orchestrator.test_results)

            if passed == total and total > 0:
                self.print_result(f"Manual tests passed ({passed}/{total})")
                self.results["manual_tests"] = {"success": True, "passed": passed, "total": total}
            else:
                self.print_result(f"Manual tests failed ({passed}/{total})", success=False)
                self.results["manual_tests"] = {"success": False, "passed": passed, "total": total}

        except ImportError as e:
            self.print_result(f"Could not import manual test module: {e}", success=False)
            self.results["manual_tests"] = {"success": False, "reason": str(e)}
        except Exception as e:
            self.print_result(f"Manual tests failed: {e}", success=False)
            self.results["manual_tests"] = {"success": False, "reason": str(e)}

    def check_test_environment(self):
        """Check if test environment is properly configured."""
        self.print_header("Test Environment Check")

        checks = [
            ("Python version", sys.version_info >= (3, 8)),
            ("pytest available", self._check_package("pytest")),
            ("asyncio available", self._check_package("asyncio")),
            ("Test directory", self.test_dir.exists()),
        ]

        all_good = True
        for check_name, result in checks:
            self.print_result(f"{check_name}: {'✓' if result else '✗'}", success=result)
            if not result:
                all_good = False

        if not all_good:
            self.print_result("Environment check failed - some tests may not run", success=False)
            return False

        self.print_result("Environment check passed")
        return True

    def _check_package(self, package_name: str) -> bool:
        """Check if a package is available."""
        try:
            __import__(package_name)
            return True
        except ImportError:
            return False

    def generate_comprehensive_report(self):
        """Generate comprehensive test report."""
        self.print_header("Comprehensive Test Report")

        # Overall summary
        total_success = all(
            [
                self.results.get("unit_tests", {}).get("success", False),
                self.results.get("integration_tests", {}).get("success", False),
                self.results.get("manual_tests", {}).get("success", False),
            ]
        )

        print(f"📊 Overall Test Status: {'PASSED' if total_success else 'FAILED'}")

        # Detailed results
        for test_type, result in self.results.items():
            if result is None:
                continue

            if test_type == "timestamp":
                continue

            print(f"\n{test_type.replace('_', ' ').title()}:")
            if isinstance(result, dict):
                if result.get("success"):
                    print("   ✅ PASSED")
                    if "passed" in result and "total" in result:
                        print(f"      {result['passed']}/{result['total']} scenarios passed")
                else:
                    print("   ❌ FAILED")
                    if "reason" in result:
                        print(f"      Reason: {result['reason']}")

        # Save detailed report
        report_file = f"comprehensive_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w") as f:
            json.dump(self.results, f, indent=2)

        print(f"\n📄 Detailed report saved to: {report_file}")

        return total_success


async def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Enhanced Overlord Workflow Test Runner")
    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    parser.add_argument("--integration", action="store_true", help="Run integration tests")
    parser.add_argument("--manual", action="store_true", help="Run manual test scenarios")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--coverage", action="store_true", help="Include coverage report")
    parser.add_argument("--scenario", default="all", help="Specific manual test scenario")

    args = parser.parse_args()

    runner = TestRunner()

    # Environment check
    if not runner.check_test_environment():
        print("❌ Environment check failed. Please fix issues before running tests.")
        return 1

    # Run requested tests
    if args.all or (not args.unit and not args.integration and not args.manual):
        runner.run_unit_tests(coverage=args.coverage)
        runner.run_integration_tests()
        await runner.run_manual_tests(scenario=args.scenario)
    else:
        if args.unit:
            runner.run_unit_tests(coverage=args.coverage)
        if args.integration:
            runner.run_integration_tests()
        if args.manual:
            await runner.run_manual_tests(scenario=args.scenario)

    # Generate report
    success = runner.generate_comprehensive_report()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
