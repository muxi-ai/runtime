#!/usr/bin/env python3
"""Common utilities for E2E test classes."""

import sys
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any


class TestOutputFormatter:
    """Standardized formatter for test outputs."""

    def print_test_header(self, test_name: str, description: str):
        """Print standardized test header.

        Args:
            test_name: Name of the test (e.g., "5_1")
            description: Description of what the test does
        """
        print(f"\n{'='*60}")
        print(f"🧪 TEST {test_name}: {description}")
        print(f"{'='*60}")

    def print_test_result(
        self,
        test_name: str,
        success: bool,
        checks: List[str],
        transcript: List[Tuple[str, str]],
        duration: float
    ):
        """Print standardized test result.

        Args:
            test_name: Name of the test
            success: Whether test passed
            checks: List of checks that passed
            transcript: Conversation transcript
            duration: Test duration in seconds
        """
        print(f"\n{'='*60}")
        print(f"📊 TEST {test_name} RESULTS")
        print(f"{'='*60}")

        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"Status: {status}")
        print(f"Duration: {duration:.2f}s")
        print(f"Checks passed: {len(checks)}")

        if checks:
            print("\n✓ Successful checks:")
            for check in checks:
                print(f"  • {check}")

        if transcript:
            print(f"\n{'='*40}")
            print("### Chat transcript:")
            for role, message in transcript:
                # Truncate long messages
                display_message = message[:200] + "..." if len(message) > 200 else message
                print(f"\n{role}: {display_message}")


class BaseE2ETest:
    """Base class for E2E tests."""

    def __init__(self):
        """Initialize base test."""
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None

    def print_test_header(self, test_name: str, description: str):
        """Print standardized test header."""
        self.formatter.print_test_header(test_name, description)

    def print_test_result(
        self,
        test_name: str,
        success: bool,
        checks: List[str],
        transcript: List[Tuple[str, str]],
        duration: float,
    ):
        """Print standardized test result."""
        self.formatter.print_test_result(test_name, success, checks, transcript, duration)

    async def cleanup(self):
        """Clean up formation and resources."""
        if self.formation:
            try:
                await self.formation.shutdown()
            except Exception:
                pass
        self.formation = None
        self.overlord = None