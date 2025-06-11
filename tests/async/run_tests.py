#!/usr/bin/env python3
"""
Test runner for async orchestration test suite.

This script runs all async orchestration tests and provides summary results.
Can be used for development testing or CI/CD pipelines.
"""

import sys
import pytest
from pathlib import Path


def main():
    """Run the async orchestration test suite."""

    # Get the async tests directory
    async_tests_dir = Path(__file__).parent

    print("🧪 Running MUXI Async Orchestration Test Suite")
    print("=" * 60)
    print()

    # Configure pytest arguments
    pytest_args = [
        str(async_tests_dir),
        "-v",                    # Verbose output
        "--tb=short",            # Short traceback format
        "--asyncio-mode=auto",   # Auto async mode
        "-x",                    # Stop on first failure
        "--color=yes",           # Colored output
    ]

    # Add coverage if available
    try:
        import pytest_cov  # noqa: F401
        pytest_args.extend([
            "--cov=muxi.runtime.overlord.async_patterns",
            "--cov-report=term-missing",
            "--cov-report=html:coverage_html"
        ])
        print("📊 Coverage reporting enabled")
    except ImportError:
        print("ℹ️  Coverage reporting not available (install pytest-cov)")

    print()
    print("🚀 Starting tests...")
    print()

    # Run the tests
    exit_code = pytest.main(pytest_args)

    print()
    print("=" * 60)

    if exit_code == 0:
        print("✅ All tests passed!")
        print()
        print("📝 Test Coverage:")
        print("   - RequestTracker: State management, thread safety, cleanup")
        print("   - WebhookManager: Delivery, retries, error handling")
        print("   - TimeEstimator: Processing time estimation, threshold logic")
        print("   - Integration: Complete async workflow end-to-end")
        print()
        print("🎯 Async orchestration implementation is fully tested!")
    else:
        print("❌ Some tests failed!")
        print()
        print("💡 To run specific test files:")
        print(f"   pytest {async_tests_dir}/test_request_tracker.py -v")
        print(f"   pytest {async_tests_dir}/test_webhook_manager.py -v")
        print(f"   pytest {async_tests_dir}/test_time_estimator.py -v")
        print(f"   pytest {async_tests_dir}/test_async_integration.py -v")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
