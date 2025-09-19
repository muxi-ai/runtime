"""
Common utilities and base classes for E2E tests.

This module provides standardized components for all E2E tests:
- BaseE2ETest: Base test class with formation management
- TestOutputFormatter: Standardized output formatting
- TestTimeouts: Dynamic timeout management
- FormationManager: Formation setup and configuration
- TestDataGenerator: Test data fixtures
- TestRetry: Error recovery and retry logic
"""

from .base import BaseE2ETest
from .formatter import TestOutputFormatter
from .timeout import TestTimeouts
from .formations import FormationManager, FormationPattern, TEST_PATTERNS
from .fixtures.data import TestDataGenerator
from .retry import TestRetry, RetryConfig, CircuitBreaker
from .env import test_env
from .validation import FormationValidator
from .results import TestResultTracker
from .benchmark import PerformanceBenchmark
from .markers import (
    covers,
    critical,
    extended,
    fast,
    parallel_safe,
    rate_limited,
    regression,
    requires_a2a,
    requires_faissx,
    requires_postgres,
    requires_webhook,
    serial,
    slow,
    smoke,
    very_slow,
)

__all__ = [
    # Core classes
    "BaseE2ETest",
    "TestOutputFormatter",
    "TestTimeouts",
    "FormationManager",
    "FormationPattern",
    "TEST_PATTERNS",
    # Test utilities
    "TestDataGenerator",
    "TestRetry",
    "RetryConfig",
    "CircuitBreaker",
    "test_env",
    "FormationValidator",
    "TestResultTracker",
    "PerformanceBenchmark",
    # Test markers
    "smoke",
    "regression",
    "critical",
    "extended",
    "fast",
    "slow",
    "very_slow",
    "requires_postgres",
    "requires_faissx",
    "requires_webhook",
    "requires_a2a",
    "serial",
    "parallel_safe",
    "rate_limited",
    "covers",
]
