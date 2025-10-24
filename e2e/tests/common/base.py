"""
Base test class for E2E tests.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple
from concurrent.futures import ThreadPoolExecutor

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402
from .formatter import TestOutputFormatter  # noqa: E402
from .timeout import TestTimeouts  # noqa: E402
from .formations import FormationManager, FormationPattern, TEST_PATTERNS  # noqa: E402
from .env import test_env  # noqa: E402
from .results import TestResultTracker  # noqa: E402
from .benchmark import PerformanceBenchmark  # noqa: E402


class BaseE2ETest:
    """
    Base class for all E2E tests.

    Provides:
    - Formation lifecycle management
    - Support for all three formation patterns
    - Standardized test execution
    - Event loop handling
    - Timeout management
    - Result collection and reporting
    """

    def __init__(self, test_name: str, test_description: str, test_area: str):
        """
        Initialize base test.

        Args:
            test_name: Name of the test (e.g., "1a1_basic_formation")
            test_description: Description of what the test validates
            test_area: Test area (e.g., "1_foundation", "2_memory")
        """
        self.test_name = test_name
        self.test_description = test_description
        self.test_area = test_area
        self.pattern = TEST_PATTERNS.get(test_area, FormationPattern.RUNTIME)

        # Initialize components
        self.formatter = TestOutputFormatter()
        self.timeouts = TestTimeouts()
        self.formation_manager = FormationManager()
        self.result_tracker = TestResultTracker()
        self.benchmark = PerformanceBenchmark()

        # Test state
        self.results: List[bool] = []
        self.transcript: List[Tuple[str, str]] = []
        self.formation: Optional[Formation] = None
        self.overlord = None
        self.start_time = None

    async def setup_formation(
        self,
        formation_path: Optional[Union[Path, str]] = None,
        yaml_name: Optional[str] = None,
        runtime_overrides: Optional[Dict[str, Any]] = None,
        template: str = "standard",
    ):
        """
        Initialize and start formation with pattern-specific handling.

        Args:
            formation_path: Optional explicit path (overrides pattern-based path)
            yaml_name: YAML filename for shared pattern (e.g., "formation-buffer-local.yaml")
            runtime_overrides: Optional runtime configuration overrides
            template: Template to use if creating new formation

        Returns:
            Formation object
        """
        try:
            self.formatter.print_setup("Initializing formation...")

            # Determine formation path based on pattern
            if formation_path:
                # Explicit path provided
                path = Path(formation_path)
            else:
                # Use pattern-based path
                if self.pattern == FormationPattern.SHARED and not yaml_name:
                    raise ValueError("Shared pattern requires yaml_name parameter")

                # Extract test name from full test name
                test_name = (
                    self.test_name.split("_", 2)[-1] if "_" in self.test_name else self.test_name
                )

                path = self.formation_manager.get_formation_path(
                    self.test_area, self.pattern, yaml_name, test_name
                )

            # Initialize formation
            self.formation = Formation()

            # Load formation (runtime overrides would need to be applied to the YAML directly)
            # TODO: Implement runtime override mechanism if needed
            await self.formation.load(str(path))

            # Start overlord
            self.overlord = await self.formation.start_overlord()

            self.formatter.print_setup(f"Formation ready (pattern: {self.pattern})")
            return self.formation

        except Exception as e:
            self.formatter.print_error(f"Formation setup failed: {e}")
            raise

    async def cleanup_formation(self):
        """Clean up formation resources."""
        if self.formation:
            try:
                self.formatter.print_teardown("Cleaning up formation...")
                
                # Stop API server if it's running
                if hasattr(self.formation, '_formation_server') and self.formation._formation_server:
                    if hasattr(self.formation._formation_server, 'is_running') and self.formation._formation_server.is_running:
                        self.formatter.print_teardown("Stopping API server...")
                        try:
                            await self.formation._formation_server.stop()
                            # Give server time to fully release port
                            await asyncio.sleep(1)
                        except Exception as e:
                            self.formatter.print_warning(f"Server stop error: {e}")
                
                # Stop overlord if it's running
                if self.overlord:
                    await self.formation.stop_overlord()
                
                self.formatter.print_teardown("Formation cleaned up")
            except Exception as e:
                self.formatter.print_warning(f"Cleanup error: {e}")

    async def run_test_case(self, test_case: Dict[str, Any]) -> bool:
        """
        Run a single test case.

        Args:
            test_case: Test case dictionary with:
                - name: Test case name
                - message: Message to send
                - expected: Expected response content (string or list)
                - timeout: Optional timeout override
                - user_id: Optional user ID
                - session_id: Optional session ID
                - use_async: Optional async flag
                - stream: Optional stream flag

        Returns:
            Boolean indicating test success
        """
        case_name = test_case.get("name", "Unnamed test")
        message = test_case.get("message", "")
        expected = test_case.get("expected", [])

        # Get timeout for this test type
        timeout = test_case.get("timeout")
        if not timeout:
            timeout = self.timeouts.get_test_timeout(
                self.test_name, message, test_env.get_test_config()["environment"]
            )

        self.formatter.print_test_case(case_name, message)

        try:
            # Send chat message with timeout
            response = await asyncio.wait_for(
                self.overlord.chat(
                    message=message,
                    user_id=test_case.get("user_id", "test_user"),
                    session_id=test_case.get("session_id", "test_session"),
                    use_async=test_case.get("use_async", False),
                    stream=test_case.get("stream", False),
                ),
                timeout=timeout,
            )

            # Extract content
            content = response.content if hasattr(response, "content") else str(response)

            # Store transcript
            self.transcript.append((message, content))

            # Check expectations
            if isinstance(expected, list):
                success = all(exp.lower() in content.lower() for exp in expected)
                check_msg = f"Expected all of: {expected}"
            else:
                success = expected.lower() in content.lower()
                check_msg = f"Expected: '{expected}'"

            if success:
                self.formatter.print_success(f"{case_name} passed")
            else:
                self.formatter.print_failure(f"{case_name} failed")
                self.formatter.print_debug(f"Got: {content[:200]}...")

            self.formatter.print_exchange(message, content, success, check_msg)

            return success

        except asyncio.TimeoutError:
            self.formatter.print_failure(f"{case_name} timed out after {timeout}s")
            return False
        except Exception as e:
            self.formatter.print_error(f"{case_name} error: {e}")
            return False

    async def run_test_cases(self, test_cases: List[Dict[str, Any]]) -> List[bool]:
        """
        Run multiple test cases sequentially.

        Args:
            test_cases: List of test case dictionaries

        Returns:
            List of boolean results for each test case
        """
        results = []
        total = len(test_cases)

        for i, test_case in enumerate(test_cases, 1):
            self.formatter.print_progress(i, total)
            result = await self.run_test_case(test_case)
            results.append(result)
            self.results.append(result)

        return results

    def print_summary(self, include_transcript: bool = True):
        """
        Print test summary.

        Args:
            include_transcript: Whether to include chat transcript
        """
        passed = sum(self.results)
        total = len(self.results)
        duration = time.time() - self.start_time if self.start_time else 0

        # Check for performance regression
        ok, perf_msg = self.benchmark.check_regression(self.test_name, duration)
        if not ok:
            self.formatter.print_warning(perf_msg)

        # Record result for tracking
        self.result_tracker.record_result(
            self.test_name,
            self.test_area,
            duration,
            all(self.results),
            error_message=None if all(self.results) else f"Failed {total - passed}/{total} tests",
        )

        # Print formatted summary
        self.formatter.print_summary(passed, total, self.test_name)

        if include_transcript and self.transcript:
            checks_passed = [f"Test case {i+1}" for i, r in enumerate(self.results) if r]
            self.formatter.print_test_result(
                self.test_name, all(self.results), checks_passed, self.transcript, duration
            )

    async def run(
        self,
        test_cases: List[Dict[str, Any]],
        formation_path: Optional[Union[Path, str]] = None,
        yaml_name: Optional[str] = None,
        runtime_overrides: Optional[Dict[str, Any]] = None,
        template: str = "standard",
    ) -> int:
        """
        Main test execution method.

        Args:
            test_cases: List of test cases to run
            formation_path: Optional explicit formation path
            yaml_name: YAML filename for shared pattern
            runtime_overrides: Optional runtime configuration
            template: Template to use if creating formation

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        # Print header
        self.formatter.print_test_header(self.test_name, self.test_description)
        self.start_time = time.time()

        try:
            # Setup formation
            if not await self.setup_formation(
                formation_path, yaml_name, runtime_overrides, template
            ):
                return 1

            # Run test cases
            await self.run_test_cases(test_cases)

            # Print summary
            self.print_summary()

            # Cleanup
            await self.cleanup_formation()

            # Return exit code
            return 0 if all(self.results) else 1

        except Exception as e:
            self.formatter.print_error(f"Test suite error: {e}")
            return 1

    @classmethod
    def run_in_event_loop(
        cls,
        test_name: str,
        test_description: str,
        test_area: str,
        test_cases: List[Dict[str, Any]],
        formation_path: Optional[Union[Path, str]] = None,
        yaml_name: Optional[str] = None,
        runtime_overrides: Optional[Dict[str, Any]] = None,
        template: str = "standard",
    ) -> int:
        """
        Helper method to run test with proper event loop handling.

        Args:
            test_name: Name of the test
            test_description: Test description
            test_area: Test area (e.g., "1_foundation")
            test_cases: List of test cases
            formation_path: Optional explicit formation path
            yaml_name: YAML filename for shared pattern
            runtime_overrides: Optional runtime configuration
            template: Formation template

        Returns:
            Exit code
        """
        # Handle event loop conflicts as per Lessons Learned
        try:
            # Try to get existing loop
            asyncio.get_running_loop()
            # If we're in a running loop, use ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    cls(test_name, test_description, test_area).run(
                        test_cases, formation_path, yaml_name, runtime_overrides, template
                    ),
                )
                return future.result()
        except RuntimeError:
            # No running loop, we can use asyncio.run directly
            test = cls(test_name, test_description, test_area)
            return asyncio.run(
                test.run(test_cases, formation_path, yaml_name, runtime_overrides, template)
            )
