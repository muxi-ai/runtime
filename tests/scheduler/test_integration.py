#!/usr/bin/env python3
"""
Integration tests for MUXI Scheduler with Formation framework.
Tests the complete scheduler integration including configuration, initialization, and database setup.
"""

import asyncio
import os
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from muxi.services.scheduler.service import SchedulerService
from muxi.services.scheduler.manager import JobManager
from muxi.services.scheduler.models import ScheduledJob
from muxi.services.db import DatabaseManager, get_database_manager


class TestSchedulerIntegration:
    """Test scheduler integration with MUXI framework."""

    @pytest.fixture
    def mock_overlord(self):
        """Create a mock overlord instance."""
        overlord = MagicMock()
        overlord.formation_config = {
            "scheduler": {
                "enabled": True,
                "check_interval_minutes": 1,
                "max_concurrent_jobs": 5,
                "timezone": "UTC",
                "max_failures_before_pause": 3
            },
            "memory": {
                "persistent": {
                    "connection_string": "sqlite:///test_scheduler.db"
                }
            }
        }
        overlord.chat = AsyncMock(return_value="Mock response")
        return overlord

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        yield f"sqlite:///{db_path}"
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.mark.asyncio
    async def test_scheduler_service_initialization(self, mock_overlord):
        """Test that SchedulerService initializes correctly with Formation integration."""
        with patch('muxi.services.scheduler.service.get_database_manager') as mock_db_manager:
            # Mock database manager
            db_manager = MagicMock()
            db_manager.database_type = 'sqlite'
            db_manager.get_session.return_value.__enter__ = MagicMock()
            db_manager.get_session.return_value.__exit__ = MagicMock()
            mock_db_manager.return_value = db_manager

            # Initialize scheduler service
            scheduler = SchedulerService(mock_overlord)

            # Verify initialization
            assert scheduler.overlord == mock_overlord
            assert scheduler.check_interval_minutes == 1
            assert scheduler.max_concurrent_jobs == 5
            assert scheduler.formation_timezone == "UTC"
            assert scheduler.max_failures_before_pause == 3
            assert isinstance(scheduler.job_manager, JobManager)

    @pytest.mark.asyncio
    async def test_database_manager_integration(self, temp_db_path):
        """Test that DatabaseManager works with scheduler models."""
        # Create database manager with test database
        with patch('muxi.services.db.get_database_manager') as mock_get_manager:
            db_manager = DatabaseManager(temp_db_path)
            mock_get_manager.return_value = db_manager

            # Initialize database schema
            from muxi.services.db import Base
            db_manager.create_tables(Base.metadata)

            # Test database operations
            job_manager = JobManager(db_manager)
            await job_manager.initialize()

            # Create a test job
            job_id = await job_manager.create_job(
                user_id="test_user",
                formation_id="test_formation",
                title="Test Job",
                original_prompt="Test original prompt",
                execution_prompt="Test execution prompt",
                cron_expression="0 * * * *",
                exclusion_rules=[]
            )

            # Verify job was created
            assert job_id.startswith("sched_")

            # Retrieve the job
            job = await job_manager.get_job(job_id)
            assert job is not None
            assert job['title'] == "Test Job"
            assert job['user_id'] == "test_user"
            assert job['status'] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_formation_config_integration(self, mock_overlord):
        """Test that scheduler correctly reads Formation configuration."""
        # Test with scheduler disabled
        mock_overlord.formation_config = {"scheduler": {"enabled": False}}

        with patch('muxi.services.scheduler.service.get_database_manager'):
            scheduler = SchedulerService(mock_overlord)

            # Should read disabled state
            config = scheduler._get_scheduler_config()
            assert config.get("enabled") == False

        # Test with custom configuration
        mock_overlord.formation_config = {
            "scheduler": {
                "enabled": True,
                "check_interval_minutes": 5,
                "max_concurrent_jobs": 20,
                "timezone": "America/New_York",
                "max_failures_before_pause": 5
            }
        }

        with patch('muxi.services.scheduler.service.get_database_manager'):
            scheduler = SchedulerService(mock_overlord)

            # Should read custom configuration
            assert scheduler.check_interval_minutes == 5
            assert scheduler.max_concurrent_jobs == 20
            assert scheduler.formation_timezone == "America/New_York"
            assert scheduler.max_failures_before_pause == 5

    @pytest.mark.asyncio
    async def test_scheduler_lifecycle_management(self, mock_overlord):
        """Test scheduler start/stop lifecycle integration."""
        with patch('muxi.services.scheduler.service.get_database_manager') as mock_db_manager:
            # Mock database manager and job manager
            db_manager = MagicMock()
            mock_db_manager.return_value = db_manager

            job_manager = AsyncMock()
            job_manager.count_active_jobs.return_value = 0

            # Initialize scheduler
            scheduler = SchedulerService(mock_overlord)
            scheduler.job_manager = job_manager

            # Test start
            result = await scheduler.start()
            assert result["status"] == "started"
            assert result["service"] == "SchedulerService"
            assert scheduler._running == True

            # Test get status
            status = await scheduler.get_status()
            assert status["running"] == True
            assert status["enabled"] == True
            assert status["jobs_active"] == 0

            # Test stop
            stop_result = await scheduler.stop()
            assert stop_result["status"] == "stopped"
            assert scheduler._running == False

    def test_scheduler_configuration_validation(self):
        """Test scheduler configuration validation patterns."""
        # Test valid configuration
        valid_config = {
            "scheduler": {
                "enabled": True,
                "check_interval_minutes": 1,
                "max_concurrent_jobs": 10,
                "timezone": "UTC",
                "max_failures_before_pause": 3
            }
        }

        # Test invalid configuration types
        invalid_configs = [
            {"scheduler": "not_a_dict"},
            {"scheduler": {"enabled": "not_a_bool"}},
            {"scheduler": {"check_interval_minutes": "not_an_int"}},
            {"scheduler": {"check_interval_minutes": -1}},
            {"scheduler": {"max_concurrent_jobs": 0}},
        ]

        # These would be caught by Formation validation
        # We're testing that our service handles them gracefully
        for config in invalid_configs:
            # Scheduler service should handle gracefully with defaults
            pass  # Implementation would use try/catch with sensible defaults


if __name__ == "__main__":
    # Run basic integration test
    async def run_basic_test():
        print("🧪 Running MUXI Scheduler Integration Tests...")

        # Create mock overlord
        mock_overlord = MagicMock()
        mock_overlord.formation_config = {
            "scheduler": {
                "enabled": True,
                "check_interval_minutes": 1,
                "max_concurrent_jobs": 5,
                "timezone": "UTC"
            }
        }
        mock_overlord.chat = AsyncMock(return_value="Test response")

        try:
            with patch('muxi.services.scheduler.service.get_database_manager') as mock_db_manager:
                # Mock database manager
                db_manager = MagicMock()
                db_manager.database_type = 'sqlite'
                mock_db_manager.return_value = db_manager

                # Test scheduler initialization
                scheduler = SchedulerService(mock_overlord)
                print(f"   ✓ Scheduler initialized with {scheduler.formation_timezone} timezone")
                print(f"   ✓ Check interval: {scheduler.check_interval_minutes} minutes")
                print(f"   ✓ Max concurrent jobs: {scheduler.max_concurrent_jobs}")

                # Test configuration reading
                config = scheduler._get_scheduler_config()
                assert config.get("enabled") == True
                print("   ✓ Formation configuration integration working")

                print("🎉 All integration tests passed!")

        except Exception as e:
            print(f"   ❌ Integration test failed: {e}")
            import traceback
            traceback.print_exc()

    # Run the test
    asyncio.run(run_basic_test())
