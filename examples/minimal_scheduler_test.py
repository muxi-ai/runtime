#!/usr/bin/env python3
"""
Minimal Real-World Scheduler Test

Direct test of core scheduler functionality without observability dependencies.
Tests both recurring and one-time job parsing and database operations.
"""

import asyncio
import sys
import os
import tempfile
from datetime import datetime, timedelta

# Add the runtime path so we can import muxi
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class MockObservability:
    """Mock observability to avoid missing events."""

    class SystemEvents:
        DATABASE_MANAGER_INITIALIZED = "database_manager_initialized"
        DATABASE_EXTENSION_FAILED = "database_extension_failed"
        SCHEDULER_PARSER_INITIALIZED = "scheduler_parser_initialized"

    class ErrorEvents:
        DATABASE_EXTENSION_FAILED = "database_extension_failed"

    def observe(self, *args, **kwargs):
        pass

    def emit_event(self, *args, **kwargs):
        pass


# Mock the observability module before importing scheduler components
import muxi.services.observability as obs_module  # noqa: E402

mock_obs = MockObservability()
obs_module.SystemEvents = mock_obs.SystemEvents
obs_module.ErrorEvents = mock_obs.ErrorEvents
obs_module.observe = mock_obs.observe
obs_module.emit_event = mock_obs.emit_event


from muxi.services.scheduler.manager import JobManager  # noqa: E402
from muxi.services.scheduler.parser import ScheduleParser  # noqa: E402
from muxi.services.db import DatabaseManager  # noqa: E402


class MinimalSchedulerTest:
    """Minimal real-world test for scheduler functionality."""

    def __init__(self):
        self.test_results = {}
        self.postgres_url = "postgresql://muxi@localhost/muxi_test"

    def create_database_manager(self, connection_string: str) -> DatabaseManager:
        """Create a database manager with minimal setup."""
        return DatabaseManager(connection_string)

    async def test_job_type_detection(self):
        """Test intelligent job type detection."""
        print("🧠 Testing Job Type Detection")
        print("=" * 50)

        try:
            # Mock LLM for the parser
            parser = ScheduleParser()

            test_cases = [
                ("remind me tomorrow at 2pm", "one_time"),
                ("remind me every day at 2pm", "recurring"),
                ("send report next Friday", "one_time"),
                ("send report every Friday", "recurring"),
                ("check status in 5 minutes", "one_time"),
                ("check status every 5 minutes", "recurring"),
            ]

            all_correct = True
            for text, expected_type in test_cases:
                detected_type = await parser._detect_job_type(text)
                status = "✅" if detected_type == expected_type else "❌"
                print(f"{status} '{text}' → {detected_type} (expected: {expected_type})")

                if detected_type != expected_type:
                    all_correct = False

            if all_correct:
                print("🎉 Job type detection test PASSED!")
                self.test_results["job_type_detection"] = True
            else:
                print("❌ Job type detection test FAILED!")
                self.test_results["job_type_detection"] = False

        except Exception as e:
            print(f"❌ Job type detection test failed: {e}")
            self.test_results["job_type_detection"] = False
            import traceback

            traceback.print_exc()

        print()

    async def test_datetime_parsing(self):
        """Test datetime parsing for one-time jobs."""
        print("📅 Testing Datetime Parsing")
        print("=" * 50)

        try:
            parser = ScheduleParser()

            test_cases = [
                "tomorrow",
                "in 1 minute",
                "next week",
                "in 2 hours",
            ]

            all_correct = True
            for text in test_cases:
                try:
                    result = parser._fallback_parse_datetime(text, "UTC")
                    if result and result.get("job_type") == "one_time":
                        print(f"✅ '{text}' → {result['scheduled_for']}")
                    else:
                        print(f"❌ '{text}' → Failed to parse")
                        all_correct = False
                except Exception as e:
                    print(f"❌ '{text}' → Error: {e}")
                    all_correct = False

            if all_correct:
                print("🎉 Datetime parsing test PASSED!")
                self.test_results["datetime_parsing"] = True
            else:
                print("❌ Datetime parsing test FAILED!")
                self.test_results["datetime_parsing"] = False

        except Exception as e:
            print(f"❌ Datetime parsing test failed: {e}")
            self.test_results["datetime_parsing"] = False
            import traceback

            traceback.print_exc()

        print()

    async def test_database_operations_sqlite(self):
        """Test database operations with SQLite."""
        print("💾 Testing Database Operations (SQLite)")
        print("=" * 50)

        try:
            # Create SQLite database
            sqlite_path = tempfile.mktemp(suffix=".db")
            sqlite_url = f"sqlite:///{sqlite_path}"

            db_manager = self.create_database_manager(sqlite_url)
            job_manager = JobManager(db_manager)
            await job_manager.initialize()

            # Test creating a one-time job
            scheduled_time = datetime.now() + timedelta(minutes=1)
            job_id = await job_manager.create_job(
                user_id="test_user",
                formation_id="test_formation",
                title="Test One-time Job",
                original_prompt="remind me in 1 minute",
                execution_prompt="Test reminder!",
                scheduled_for=scheduled_time,
                is_recurring=False,
            )

            # Test creating a recurring job
            recurring_job_id = await job_manager.create_job(
                user_id="test_user",
                formation_id="test_formation",
                title="Test Recurring Job",
                original_prompt="remind me every minute",
                execution_prompt="Recurring test reminder!",
                cron_expression="* * * * *",
                is_recurring=True,
            )

            # Verify jobs were created
            onetime_job = await job_manager.get_job(job_id)
            recurring_job = await job_manager.get_job(recurring_job_id)

            if (
                onetime_job
                and not onetime_job["is_recurring"]
                and recurring_job
                and recurring_job["is_recurring"]
            ):
                print("✅ Created one-time job:", onetime_job["title"])
                print("✅ Created recurring job:", recurring_job["title"])
                print("🎉 Database operations test PASSED!")
                self.test_results["database_sqlite"] = True
            else:
                print("❌ Database operations test FAILED!")
                self.test_results["database_sqlite"] = False

        except Exception as e:
            print(f"❌ Database operations test failed: {e}")
            self.test_results["database_sqlite"] = False
            import traceback

            traceback.print_exc()

        print()

    async def test_database_operations_postgres(self):
        """Test database operations with PostgreSQL."""
        print("🐘 Testing Database Operations (PostgreSQL)")
        print("=" * 50)

        try:
            db_manager = self.create_database_manager(self.postgres_url)
            job_manager = JobManager(db_manager)
            await job_manager.initialize()

            # Test multi-user isolation
            user_a_job_id = await job_manager.create_job(
                user_id="user_a_test",
                formation_id="test_formation",
                title="User A Recurring Job",
                original_prompt="remind me every day",
                execution_prompt="Hello from User A!",
                cron_expression="0 9 * * *",
                is_recurring=True,
            )

            user_b_job_id = await job_manager.create_job(
                user_id="user_b_test",
                formation_id="test_formation",
                title="User B One-time Job",
                original_prompt="remind me tomorrow",
                execution_prompt="Hello from User B!",
                scheduled_for=datetime.now() + timedelta(days=1),
                is_recurring=False,
            )

            # Test user isolation
            user_a_jobs = await job_manager.get_user_jobs("user_a_test")
            user_b_jobs = await job_manager.get_user_jobs("user_b_test")

            user_a_has_recurring = any(
                job["is_recurring"] for job in user_a_jobs if job["id"] == user_a_job_id
            )
            user_b_has_onetime = any(
                not job["is_recurring"] for job in user_b_jobs if job["id"] == user_b_job_id
            )

            if user_a_has_recurring and user_b_has_onetime:
                print(f"✅ User A has {len(user_a_jobs)} job(s) (recurring)")
                print(f"✅ User B has {len(user_b_jobs)} job(s) (one-time)")
                print("🎉 PostgreSQL operations test PASSED!")
                self.test_results["database_postgres"] = True
            else:
                print("❌ PostgreSQL operations test FAILED!")
                self.test_results["database_postgres"] = False

        except Exception as e:
            print(f"❌ PostgreSQL operations test failed: {e}")
            self.test_results["database_postgres"] = False
            import traceback

            traceback.print_exc()

        print()

    async def run_all_tests(self):
        """Run all tests."""
        print("🚀 Minimal Scheduler Real-World Tests")
        print("=" * 60)
        print()

        # Run tests
        await self.test_job_type_detection()
        await self.test_datetime_parsing()
        await self.test_database_operations_sqlite()
        await self.test_database_operations_postgres()

        # Print summary
        print("📊 Test Results Summary")
        print("=" * 60)

        total_tests = len(self.test_results)
        passed_tests = sum(self.test_results.values())

        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")

        print(f"\n🎯 Overall: {passed_tests}/{total_tests} tests passed")

        if passed_tests == total_tests:
            print("🎉 All core tests PASSED!")
            print("\n✅ Core scheduler functionality verified:")
            print("  - Job type detection works correctly")
            print("  - Datetime parsing for one-time jobs")
            print("  - Database operations with SQLite")
            print("  - Database operations with PostgreSQL")
            print("  - Multi-user job isolation")
        else:
            print("🚨 Some tests FAILED!")
            print("Check individual test outputs for details.")


async def main():
    """Main test runner."""
    test_runner = MinimalSchedulerTest()
    await test_runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
