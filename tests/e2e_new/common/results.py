"""
Test result persistence and tracking.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
class TestResultTracker:
    """Track and persist test results for analysis and trending."""

    def __init__(self, db_path: str = "tests/results/test_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize results database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    test_area TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    duration REAL NOT NULL,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    metadata TEXT,
                    git_commit TEXT,
                    environment TEXT
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_test_name ON test_results (test_name)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp ON test_results (timestamp)
            """
            )

    def record_result(
        self,
        test_name: str,
        test_area: str,
        duration: float,
        success: bool,
        error_message: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """Record a test result."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO test_results
                (test_name, test_area, timestamp, duration, success, error_message, metadata, git_commit, environment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    test_name,
                    test_area,
                    datetime.utcnow().isoformat(),
                    duration,
                    success,
                    error_message,
                    json.dumps(metadata) if metadata else None,
                    self._get_git_commit(),
                    self._get_environment(),
                ),
            )

    def get_performance_trend(self, test_name: str, limit: int = 30) -> List[Dict]:
        """Get performance trend for a test."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, duration, success
                FROM test_results
                WHERE test_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (test_name, limit),
            )
            return [{"timestamp": row[0], "duration": row[1], "success": row[2]} for row in cursor]

    def get_test_stats(self, test_name: str) -> Dict[str, Any]:
        """Get statistics for a specific test."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                    AVG(duration) as avg_duration,
                    MIN(duration) as min_duration,
                    MAX(duration) as max_duration
                FROM test_results
                WHERE test_name = ?
            """,
                (test_name,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "total_runs": row[0],
                    "successes": row[1],
                    "success_rate": row[1] / row[0] if row[0] > 0 else 0,
                    "avg_duration": row[2],
                    "min_duration": row[3],
                    "max_duration": row[4],
                }
            return {}

    def detect_regression(
        self, test_name: str, current_duration: float, threshold: float = 1.2
    ) -> bool:
        """Detect if test has regressed (>20% slower by default)."""
        trend = self.get_performance_trend(test_name, limit=10)
        if len(trend) < 5:
            return False  # Not enough history

        # Calculate baseline from successful runs
        baseline = [t["duration"] for t in trend if t["success"]][:5]
        if not baseline:
            return False

        avg_baseline = sum(baseline) / len(baseline)
        return current_duration > avg_baseline * threshold

    def get_flaky_tests(self, min_runs: int = 10, failure_rate_threshold: float = 0.1) -> List[str]:
        """Identify flaky tests based on failure rate."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    test_name,
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failures
                FROM test_results
                GROUP BY test_name
                HAVING total_runs >= ?
            """,
                (min_runs,),
            )

            flaky_tests = []
            for row in cursor:
                test_name, total_runs, failures = row
                failure_rate = failures / total_runs
                if 0 < failure_rate < failure_rate_threshold:
                    flaky_tests.append(test_name)

            return flaky_tests

    @staticmethod
    def _get_git_commit() -> str:
        """Get current git commit hash."""
        try:
            import subprocess

            return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()[:8]
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"

    @staticmethod
    def _get_environment() -> str:
        """Detect test environment."""
        import os

        if os.getenv("CI"):
            return "ci"
        elif os.getenv("DOCKER_CONTAINER"):
            return "docker"
        else:
            return "local"
