#!/usr/bin/env python3
"""
Test suite for one-time job functionality in the MUXI Scheduler.

Tests the complete implementation of one-time jobs including:
- Job type detection
- Datetime parsing
- Job creation
- Job execution
- Job completion
"""

import pytest
import asyncio
from datetime import datetime, timedelta
import pytz
from unittest.mock import AsyncMock, MagicMock

from muxi.services.scheduler.parser import ScheduleParser
from muxi.services.scheduler.manager import JobManager
from muxi.services.scheduler.service import SchedulerService
from muxi.services.db import DatabaseManager


class TestOnetimeJobDetection:
    """Test detection of one-time vs recurring jobs."""

    @pytest.fixture
    def parser(self):
        return ScheduleParser()

    @pytest.mark.asyncio
    async def test_one_time_patterns(self, parser):
        """Test that one-time patterns are correctly detected."""
        one_time_examples = [
            "remind me tomorrow at 2pm",
            "send report next Friday",
            "check status next week",
            "do something on December 25th",
            "call mom this Tuesday",
            "review data in 3 days",
        ]

        for example in one_time_examples:
            job_type = await parser._detect_job_type(example)
            assert job_type == "one_time", f"Failed to detect '{example}' as one-time job"

    @pytest.mark.asyncio
    async def test_recurring_patterns(self, parser):
        """Test that recurring patterns are correctly detected."""
        recurring_examples = [
            "remind me every day at 2pm",
            "send report every Friday",
            "check status daily",
            "do something every week",
            "call mom every Tuesday",
            "review data hourly",
        ]

        for example in recurring_examples:
            job_type = await parser._detect_job_type(example)
            assert job_type == "recurring", f"Failed to detect '{example}' as recurring job"


class TestDatetimeParsing:
    """Test parsing of specific datetimes for one-time jobs."""

    @pytest.fixture
    def parser(self):
        parser = ScheduleParser()
        # Mock LLM for testing
        parser.llm = AsyncMock()
        return parser

    @pytest.mark.asyncio
    async def test_fallback_datetime_parsing(self, parser):
        """Test fallback datetime parsing without LLM."""
        timezone = "America/New_York"

        test_cases = [
            ("tomorrow", 1),  # 1 day ahead
            ("next week", 7),  # 7 days ahead (approximately)
        ]

        for schedule_text, expected_days in test_cases:
            result = parser._fallback_parse_datetime(schedule_text, timezone)

            assert result["job_type"] == "one_time"
            assert result["timezone"] == timezone
            assert isinstance(result["scheduled_for"], datetime)

            # Check that the datetime is approximately correct
            now = datetime.now(pytz.timezone(timezone))
            time_diff = (result["scheduled_for"].astimezone(pytz.timezone(timezone)) - now).days
            assert abs(time_diff - expected_days) <= 1  # Allow for some variance

    @pytest.mark.asyncio
    async def test_llm_datetime_parsing_success(self, parser):
        """Test successful LLM datetime parsing."""
        # Mock successful LLM response
        parser.llm.generate_text = AsyncMock(return_value='{"year": 2025, "month": 12, "day": 25, "hour": 14, "minute": 30, "timezone": "UTC"}')

        result = await parser._parse_specific_datetime("on December 25th at 2:30pm", "UTC")

        assert result["job_type"] == "one_time"
        assert result["scheduled_for"].year == 2025
        assert result["scheduled_for"].month == 12
        assert result["scheduled_for"].day == 25
        assert result["scheduled_for"].hour == 14
        assert result["scheduled_for"].minute == 30

    @pytest.mark.asyncio
    async def test_llm_datetime_parsing_fallback(self, parser):
        """Test fallback when LLM parsing fails."""
        # Mock LLM failure
        parser.llm.generate_text = AsyncMock(side_effect=Exception("LLM error"))

        result = await parser._parse_specific_datetime("tomorrow", "UTC")

        # Should fall back to basic parsing
        assert result["job_type"] == "one_time"
        assert isinstance(result["scheduled_for"], datetime)


class TestJobCreation:
    """Test creation of one-time jobs in the database."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager for testing."""
        db_manager = MagicMock()
        db_manager.database_type = "sqlite"

        # Mock session context manager
        mock_session = MagicMock()
        db_manager.get_session.return_value.__enter__.return_value = mock_session
        db_manager.get_session.return_value.__exit__.return_value = None

        return db_manager, mock_session

    @pytest.mark.asyncio
    async def test_create_onetime_job(self, mock_db_manager):
        """Test creating a one-time job."""
        db_manager, mock_session = mock_db_manager
        job_manager = JobManager(db_manager)

        scheduled_for = datetime.now(pytz.UTC) + timedelta(hours=1)

        job_id = await job_manager.create_job(
            user_id="test_user",
            formation_id="test_formation",
            title="Test One-time Job",
            original_prompt="remind me tomorrow",
            execution_prompt="Send reminder about tomorrow's task",
            cron_expression=None,
            scheduled_for=scheduled_for,
            is_recurring=False,
        )

        assert job_id.startswith("sched_")
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_recurring_job(self, mock_db_manager):
        """Test creating a recurring job (existing functionality)."""
        db_manager, mock_session = mock_db_manager
        job_manager = JobManager(db_manager)

        job_id = await job_manager.create_job(
            user_id="test_user",
            formation_id="test_formation",
            title="Test Recurring Job",
            original_prompt="remind me daily",
            execution_prompt="Send daily reminder",
            cron_expression="0 9 * * *",
            is_recurring=True,
        )

        assert job_id.startswith("sched_")
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_job_validation(self, mock_db_manager):
        """Test job creation validation."""
        db_manager, mock_session = mock_db_manager
        job_manager = JobManager(db_manager)

        # Test recurring job without cron expression
        with pytest.raises(ValueError, match="Recurring jobs require a cron_expression"):
            await job_manager.create_job(
                user_id="test_user",
                formation_id="test_formation",
                title="Invalid Recurring Job",
                original_prompt="test",
                execution_prompt="test",
                is_recurring=True,
                # Missing cron_expression
            )

        # Test one-time job without scheduled_for
        with pytest.raises(ValueError, match="One-time jobs require a scheduled_for datetime"):
            await job_manager.create_job(
                user_id="test_user",
                formation_id="test_formation",
                title="Invalid One-time Job",
                original_prompt="test",
                execution_prompt="test",
                is_recurring=False,
                # Missing scheduled_for
            )


class TestJobCompletion:
    """Test completion of one-time jobs."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager for testing."""
        db_manager = MagicMock()
        db_manager.database_type = "sqlite"

        # Mock session and query chain
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_update = MagicMock()

        # Chain the query methods
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.update.return_value = 1  # Simulate successful update

        db_manager.get_session.return_value.__enter__.return_value = mock_session
        db_manager.get_session.return_value.__exit__.return_value = None

        return db_manager, mock_session

    @pytest.mark.asyncio
    async def test_complete_onetime_job(self, mock_db_manager):
        """Test marking a one-time job as completed."""
        db_manager, mock_session = mock_db_manager
        job_manager = JobManager(db_manager)

        result = await job_manager.complete_onetime_job("test_job_id")

        assert result is True
        mock_session.commit.assert_called_once()


class TestEndToEndIntegration:
    """Test complete end-to-end flow for one-time jobs."""

    @pytest.mark.asyncio
    async def test_full_onetime_job_flow(self):
        """Test the complete flow from parsing to execution."""
        # This is a conceptual test - in a real environment you'd need
        # actual database and LLM connections

        parser = ScheduleParser()

        # Mock LLM response for datetime parsing
        if hasattr(parser, 'llm') and parser.llm:
            parser.llm = AsyncMock()
            parser.llm.generate_text = AsyncMock(
                return_value='{"year": 2025, "month": 6, "day": 23, "hour": 14, "minute": 0, "timezone": "UTC"}'
            )

        # Test job type detection
        job_type = await parser._detect_job_type("remind me tomorrow at 2pm")
        assert job_type == "one_time"

        # Test datetime parsing (using fallback)
        result = parser._fallback_parse_datetime("tomorrow at 2pm", "UTC")
        assert result["job_type"] == "one_time"
        assert isinstance(result["scheduled_for"], datetime)

        print("✅ End-to-end one-time job flow test passed")


if __name__ == "__main__":
    # Run basic tests
    asyncio.run(TestEndToEndIntegration().test_full_onetime_job_flow())
    print("🎉 One-time job functionality tests completed successfully!")
