"""
Performance benchmarking for E2E tests.
"""

from typing import Dict, Tuple
import json
from pathlib import Path


class PerformanceBenchmark:
    """Track and enforce performance baselines for tests."""

    # Baseline performance expectations (in seconds)
    BASELINE_TIMES: Dict[str, float] = {
        # Quick tests
        "simple_chat": 5.0,
        "greeting": 3.0,
        "memory_recall": 8.0,
        "basic_formation": 5.0,
        # Medium tests
        "mcp_tool_use": 20.0,
        "file_generation": 25.0,
        "knowledge_query": 15.0,
        "scheduling": 20.0,
        "agent_selection": 15.0,
        # Long tests
        "workflow_decomposition": 30.0,
        "multi_agent": 45.0,
        "video_processing": 120.0,
        "complex_orchestration": 60.0,
        # Very long tests
        "recursive_clarification": 180.0,
        "batch_processing": 240.0,
    }

    REGRESSION_THRESHOLD = 1.2  # 20% slower is considered regression

    @classmethod
    def check_regression(cls, test_name: str, actual_time: float) -> Tuple[bool, str]:
        """
        Check if test has regressed from baseline.

        Args:
            test_name: Name of the test
            actual_time: Actual execution time in seconds

        Returns:
            Tuple of (is_ok, message)
        """
        # Extract test type from full test name
        test_type = cls._extract_test_type(test_name)

        if test_type not in cls.BASELINE_TIMES:
            return True, f"No baseline for {test_type}"

        baseline = cls.BASELINE_TIMES[test_type]
        threshold = baseline * cls.REGRESSION_THRESHOLD

        if actual_time > threshold:
            return (
                False,
                f"Performance regression: {actual_time:.1f}s > {threshold:.1f}s (baseline: {baseline:.1f}s)",
            )

        return True, f"Performance OK: {actual_time:.1f}s <= {threshold:.1f}s"

    @classmethod
    def update_baseline(cls, test_name: str, new_time: float, force: bool = False):
        """Update baseline if significantly improved or forced."""
        test_type = cls._extract_test_type(test_name)
        current = cls.BASELINE_TIMES.get(test_type)

        if force or not current or new_time < current * 0.8:  # 20% improvement
            cls.BASELINE_TIMES[test_type] = new_time
            cls._persist_baselines()

    @staticmethod
    def _extract_test_type(test_name: str) -> str:
        """Extract generic test type from specific test name."""
        # test_1a1_simple_chat -> simple_chat
        parts = test_name.split("_")
        if len(parts) > 2:
            return "_".join(parts[2:])
        return test_name

    @classmethod
    def _persist_baselines(cls):
        """Save baselines to file."""
        baseline_file = Path(__file__).parent / "baselines.json"
        baseline_file.write_text(json.dumps(cls.BASELINE_TIMES, indent=2))

    @classmethod
    def load_baselines(cls):
        """Load baselines from file if exists."""
        baseline_file = Path(__file__).parent / "baselines.json"
        if baseline_file.exists():
            cls.BASELINE_TIMES = json.loads(baseline_file.read_text())
