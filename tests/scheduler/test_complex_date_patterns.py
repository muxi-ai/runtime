#!/usr/bin/env python3
"""
Test complex date pattern exclusions for MUXI Scheduler.
Tests the new complex date pattern functionality for exclusion rules.
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from muxi.services.scheduler.parser import ScheduleParser
from muxi.services.scheduler.service import SchedulerService


class TestComplexDatePatterns:
    """Test complex date pattern functionality."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return ScheduleParser()

    @pytest.fixture
    def mock_scheduler(self):
        """Create a mock scheduler service."""
        mock_overlord = MagicMock()
        mock_overlord.formation_config = {
            "scheduler": {
                "enabled": True,
                "timezone": "America/New_York"
            }
        }

        with patch('muxi.services.scheduler.service.get_database_manager'):
            scheduler = SchedulerService(mock_overlord)
            return scheduler

    @pytest.mark.asyncio
    async def test_llm_complex_date_parsing(self, parser):
        """Test LLM parsing of complex date patterns."""
        # Mock LLM responses
        mock_llm = AsyncMock()

        test_cases = [
            (
                "except the last Friday of each month",
                '{"type": "complex_date", "pattern": "last_friday_of_month", "description": "Exclude the last Friday of each month"}'
            ),
            (
                "except the first Monday of the month",
                '{"type": "complex_date", "pattern": "first_monday_of_month", "description": "Exclude the first Monday of each month"}'
            ),
            (
                "except every 3rd Tuesday",
                '{"type": "complex_date", "pattern": "nth_weekday:3:tuesday", "description": "Exclude every 3rd Tuesday of the month"}'
            ),
            (
                "außer am letzten Freitag des Monats",  # German
                '{"type": "complex_date", "pattern": "last_friday_of_month", "description": "Exclude the last Friday of each month"}'
            ),
            (
                "sauf le premier lundi du mois",  # French
                '{"type": "complex_date", "pattern": "first_monday_of_month", "description": "Exclude the first Monday of each month"}'
            ),
        ]

        for description, expected_response in test_cases:
            mock_llm.generate_text.return_value = expected_response

            with patch.object(parser, '_get_llm', return_value=mock_llm):
                rules = await parser.generate_exclusion_rules([description])

                assert len(rules) == 1
                rule = rules[0]
                assert rule['type'] == 'complex_date'
                assert 'pattern' in rule
                assert 'description' in rule

    @pytest.mark.asyncio
    async def test_complex_date_pattern_validation(self, parser):
        """Test validation of complex date patterns."""
        valid_patterns = [
            "first_monday_of_month",
            "last_friday_of_month",
            "nth_weekday:3:tuesday",
            "nth_day:15",
            "last_day_minus:2",
        ]

        invalid_patterns = [
            "random_pattern",
            "nth_weekday:6:monday",  # 6th occurrence invalid
            "nth_weekday:3:invalidday",
            "last_invalidday_of_month",
            "nth_day:abc",
        ]

        for pattern in valid_patterns:
            assert parser._validate_complex_date_pattern(pattern), f"Should be valid: {pattern}"

        for pattern in invalid_patterns:
            assert not parser._validate_complex_date_pattern(pattern), f"Should be invalid: {pattern}"

    def test_nth_weekday_calculation(self, mock_scheduler):
        """Test nth weekday of month calculation."""
        # Test cases: (date, n, weekday, expected_result)
        test_cases = [
            # First Monday of January 2024 is Jan 1
            (datetime(2024, 1, 1), 1, "monday", True),
            (datetime(2024, 1, 8), 1, "monday", False),  # Second Monday

            # Third Tuesday of January 2024 is Jan 16
            (datetime(2024, 1, 16), 3, "tuesday", True),
            (datetime(2024, 1, 9), 3, "tuesday", False),  # Second Tuesday

            # Fourth Friday of January 2024 is Jan 26
            (datetime(2024, 1, 26), 4, "friday", True),
            (datetime(2024, 1, 19), 4, "friday", False),  # Third Friday
        ]

        for dt, n, weekday, expected in test_cases:
            result = mock_scheduler._is_nth_weekday_of_month(dt, n, weekday)
            assert result == expected, f"Failed for {dt.date()}, {n}th {weekday}: got {result}, expected {expected}"

    def test_last_weekday_calculation(self, mock_scheduler):
        """Test last weekday of month calculation."""
        test_cases = [
            # Last Friday of January 2024 is Jan 26
            (datetime(2024, 1, 26), "friday", True),
            (datetime(2024, 1, 19), "friday", False),  # Not last

            # Last Monday of January 2024 is Jan 29
            (datetime(2024, 1, 29), "monday", True),
            (datetime(2024, 1, 22), "monday", False),  # Not last

            # Last Sunday of February 2024 is Feb 25
            (datetime(2024, 2, 25), "sunday", True),
            (datetime(2024, 2, 18), "sunday", False),  # Not last
        ]

        for dt, weekday, expected in test_cases:
            result = mock_scheduler._is_last_weekday_of_month(dt, weekday)
            assert result == expected, f"Failed for {dt.date()}, last {weekday}: got {result}, expected {expected}"

    def test_days_before_month_end(self, mock_scheduler):
        """Test N days before month end calculation."""
        test_cases = [
            # 2 days before end of January 2024 (31st) is Jan 29
            (datetime(2024, 1, 29), 2, True),
            (datetime(2024, 1, 30), 2, False),

            # 1 day before end of February 2024 (29th - leap year) is Feb 28
            (datetime(2024, 2, 28), 1, True),
            (datetime(2024, 2, 27), 1, False),

            # 0 days before end (last day)
            (datetime(2024, 1, 31), 0, True),
            (datetime(2024, 2, 29), 0, True),  # Leap year
        ]

        for dt, days_before, expected in test_cases:
            result = mock_scheduler._is_n_days_before_month_end(dt, days_before)
            assert result == expected, f"Failed for {dt.date()}, {days_before} days before end: got {result}, expected {expected}"

    @pytest.mark.asyncio
    async def test_complex_date_exclusion_integration(self, mock_scheduler):
        """Test full integration of complex date exclusions."""
        # Create a job with complex date exclusion
        job = {
            "id": "test_job",
            "exclusion_rules": [
                {
                    "type": "complex_date",
                    "pattern": "last_friday_of_month",
                    "description": "Skip last Friday"
                }
            ]
        }

        # Test on last Friday of January 2024
        last_friday = datetime(2024, 1, 26, 10, 0, 0)
        result = await mock_scheduler._check_exclusion_rules(job, last_friday)
        assert result == True, "Should be excluded on last Friday"

        # Test on other Friday
        other_friday = datetime(2024, 1, 19, 10, 0, 0)
        result = await mock_scheduler._check_exclusion_rules(job, other_friday)
        assert result == False, "Should not be excluded on other Friday"

        # Test on non-Friday
        non_friday = datetime(2024, 1, 25, 10, 0, 0)  # Thursday
        result = await mock_scheduler._check_exclusion_rules(job, non_friday)
        assert result == False, "Should not be excluded on non-Friday"

    @pytest.mark.asyncio
    async def test_mixed_exclusion_rules(self, mock_scheduler):
        """Test job with both cron and complex date exclusions."""
        job = {
            "id": "test_job",
            "exclusion_rules": [
                {
                    "type": "cron",
                    "pattern": "0 0 * * 0",  # Sundays
                    "description": "Skip Sundays"
                },
                {
                    "type": "complex_date",
                    "pattern": "first_monday_of_month",
                    "description": "Skip first Monday"
                }
            ]
        }

        # Test on Sunday
        sunday = datetime(2024, 1, 7, 10, 0, 0)  # Sunday
        result = await mock_scheduler._check_exclusion_rules(job, sunday)
        assert result == True, "Should be excluded on Sunday"

        # Test on first Monday
        first_monday = datetime(2024, 1, 1, 10, 0, 0)  # First Monday of Jan 2024
        result = await mock_scheduler._check_exclusion_rules(job, first_monday)
        assert result == True, "Should be excluded on first Monday"

        # Test on regular Tuesday
        tuesday = datetime(2024, 1, 9, 10, 0, 0)  # Tuesday
        result = await mock_scheduler._check_exclusion_rules(job, tuesday)
        assert result == False, "Should not be excluded on regular Tuesday"


if __name__ == "__main__":
    # Run basic tests
    async def run_basic_tests():
        print("🧪 Running Complex Date Pattern Tests...")

        try:
            # Test parser validation
            parser = ScheduleParser()

            # Test pattern validation
            valid = parser._validate_complex_date_pattern("last_friday_of_month")
            assert valid == True
            print("   ✓ Pattern validation working")

            # Test scheduler date calculations
            mock_overlord = MagicMock()
            mock_overlord.formation_config = {"scheduler": {"timezone": "UTC"}}

            with patch('muxi.services.scheduler.service.get_database_manager'):
                scheduler = SchedulerService(mock_overlord)

                # Test last Friday calculation
                last_friday = datetime(2024, 1, 26)  # Last Friday of Jan 2024
                result = scheduler._is_last_weekday_of_month(last_friday, "friday")
                assert result == True
                print("   ✓ Last weekday calculation working")

                # Test nth weekday calculation
                third_tuesday = datetime(2024, 1, 16)  # Third Tuesday of Jan 2024
                result = scheduler._is_nth_weekday_of_month(third_tuesday, 3, "tuesday")
                assert result == True
                print("   ✓ Nth weekday calculation working")

            print("🎉 All complex date pattern tests passed!")

        except Exception as e:
            print(f"   ❌ Complex date pattern test failed: {e}")
            import traceback
            traceback.print_exc()

    # Run the test
    asyncio.run(run_basic_tests())
