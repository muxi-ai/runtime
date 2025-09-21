"""
Standardized output formatting for E2E tests.
"""

from typing import List, Tuple, Any


class TestOutputFormatter:
    """Standardized test output format for all e2e tests."""

    @staticmethod
    def print_test_header(test_name: str, description: str):
        """Print standardized test header."""
        print(f"\n{'='*60}")
        print(f"TEST: {test_name}")
        print(f"Description: {description}")
        print(f"{'='*60}\n")

    @staticmethod
    def print_test_case(case_name: str, message: str):
        """Print individual test case header."""
        print(f"\n[Test Case] {case_name}")
        print(f"  Message: {message}")

    @staticmethod
    def print_exchange(user: str, assistant: str, passed: bool, check: str = ""):
        """Print standardized chat exchange."""
        print(f"User: {user}")
        print(f"Assistant: {assistant[:200]}...")
        if passed:
            print(f"✅ PASS: {check}")
        else:
            print(f"❌ FAIL: {check}")
        print()

    @staticmethod
    def print_test_result(
        test_name: str,
        success: bool,
        checks: List[str],
        transcript: List[Tuple[str, str]],
        duration: float,
    ):
        """Print standardized test result summary."""
        print(f"\n{'='*40}")
        print("\n### Test Result:")
        if success:
            print(f"  🎉 SUCCESS: {test_name}")
            for check in checks:
                print(f"  ✓ {check}")
        else:
            print(f"  ❌ FAILED: {test_name}")
            for check in checks:
                print(f"  ✗ {check}")

        print(f"\n  Duration: {duration:.2f}s")
        print(f"\n{'='*40}")

        print("\n### Chat transcript:")
        for user_msg, system_msg in transcript:
            print(f"User: {user_msg}")
            print(f"System: {system_msg[:500]}...")
            print()

    @staticmethod
    def print_setup(message: str):
        """Print setup/initialization message."""
        print(f"[Setup] {message}")

    @staticmethod
    def print_teardown(message: str):
        """Print teardown/cleanup message."""
        print(f"[Teardown] {message}")

    @staticmethod
    def print_progress(current: int, total: int):
        """Print test progress."""
        print(f"\n[Progress] Test {current}/{total}")

    @staticmethod
    def print_success(message: str):
        """Print success message."""
        print(f"  ✅ {message}")

    @staticmethod
    def print_failure(message: str):
        """Print failure message."""
        print(f"  ❌ {message}")

    @staticmethod
    def print_warning(message: str):
        """Print warning message."""
        print(f"  ⚠️  {message}")

    @staticmethod
    def print_error(message: str):
        """Print error message."""
        print(f"  ❌ ERROR: {message}")

    @staticmethod
    def print_debug(message: str):
        """Print debug message."""
        print(f"  🔍 Debug: {message}")

    @staticmethod
    def print_summary(passed: int, total: int, test_name: str):
        """Print test summary."""
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Test: {test_name}")
        print(f"Passed: {passed}/{total}")

        if passed == total:
            print("🎉 ALL TESTS PASSED!")
        else:
            print(f"⚠️  {total - passed} test(s) failed")

    @staticmethod
    def print_transcript(overlord: Any):
        """Print chat transcript from overlord."""
        # This would extract and print the conversation history
        # Implementation depends on overlord's interface
        pass

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        else:
            minutes = int(seconds / 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
