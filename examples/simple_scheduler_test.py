#!/usr/bin/env python3
"""
Simple Real-World Scheduler Test

Direct test of scheduler functionality without full formation setup.
Tests both recurring and one-time jobs.
"""

import asyncio
import sys
import os
import tempfile
from datetime import datetime

# Add the runtime path so we can import muxi
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from muxi.runtime.services.scheduler.manager import JobManager  # noqa: E402
from muxi.runtime.services.scheduler.parser import ScheduleParser  # noqa: E402
from muxi.runtime.services.db import get_database_manager  # noqa: E402


class SimpleSchedulerTest:
    """Simple real-world test for scheduler functionality."""

    def __init__(self):
        self.test_results = {}
        self.postgres_url = "postgresql://muxi@localhost/muxi_test"

    async def test_onetime_job_sqlite(self):
        """Test one-time job with SQLite."""
        print("⏰ Testing One-Time Job with SQLite")
        print("=" * 50)

        try:
            # Create SQLite database
            sqlite_path = tempfile.mktemp(suffix=".db")
            sqlite_url = f"sqlite:///{sqlite_path}"

            # Initialize database manager
            db_manager = get_database_manager(sqlite_url)
            job_manager = JobManager(db_manager)
            await job_manager.initialize()

            # Parse "in 1 minute" request
            parser = ScheduleParser()
            schedule_result = await parser.parse_schedule("in 1 minute", "UTC")

            print(f"Parsed schedule: {schedule_result}")

            if isinstance(schedule_result, dict) and schedule_result.get("job_type") == "one_time":
                # Create one-time job
                job_id = await job_manager.create_job(
                    user_id="test_user_sqlite",
                    formation_id="test_formation",
                    title="One-time Test Job",
                    original_prompt="remind me in 1 minute",
                    execution_prompt="Test reminder: One minute has passed!",
                    scheduled_for=schedule_result["scheduled_for"],
                    is_recurring=False,
                )

                print(f"✅ Created one-time job: {job_id}")
                print(f"Scheduled for: {schedule_result['scheduled_for']}")

                # Wait for job time
                print("⏳ Waiting for job execution time...")
                now = datetime.now(schedule_result["scheduled_for"].tzinfo)
                wait_seconds = (schedule_result["scheduled_for"] - now).total_seconds()

                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds + 10)  # Wait a bit extra

                # Check if job would have been due
                job = await job_manager.get_job(job_id)
                if job:
                    now = datetime.now(job["scheduled_for"].tzinfo)
                    if now >= job["scheduled_for"]:
                        print("🎉 One-time job test PASSED - job time has arrived!")
                        print(f"Job scheduled for: {job['scheduled_for']}")
                        print(f"Current time: {now}")
                        self.test_results["onetime_sqlite"] = True
                    else:
                        print("❌ One-time job test FAILED - job time hasn't arrived yet")
                        self.test_results["onetime_sqlite"] = False
                else:
                    print("❌ One-time job test FAILED - couldn't retrieve job")
                    self.test_results["onetime_sqlite"] = False

            else:
                print(f"❌ Failed to parse 'in 1 minute' as one-time job: {schedule_result}")
                self.test_results["onetime_sqlite"] = False

        except Exception as e:
            print(f"❌ One-time SQLite test failed: {e}")
            self.test_results["onetime_sqlite"] = False
            import traceback

            traceback.print_exc()

        print()

    async def test_recurring_job_sqlite(self):
        """Test recurring job with SQLite."""
        print("🔄 Testing Recurring Job with SQLite")
        print("=" * 50)

        try:
            # Create SQLite database
            sqlite_path = tempfile.mktemp(suffix=".db")
            sqlite_url = f"sqlite:///{sqlite_path}"

            # Initialize database manager
            db_manager = get_database_manager(sqlite_url)
            job_manager = JobManager(db_manager)
            await job_manager.initialize()

            # Parse "every minute" request
            parser = ScheduleParser()
            cron_expression = await parser.parse_schedule("every minute", "UTC")

            print(f"Parsed cron: {cron_expression}")

            if isinstance(cron_expression, str):
                # Create recurring job
                job_id = await job_manager.create_job(
                    user_id="test_user_sqlite_recurring",
                    formation_id="test_formation",
                    title="Recurring Test Job",
                    original_prompt="remind me every minute",
                    execution_prompt="Test reminder: Another minute has passed!",
                    cron_expression=cron_expression,
                    is_recurring=True,
                )

                print(f"✅ Created recurring job: {job_id}")
                print(f"Cron expression: {cron_expression}")

                # Verify job was created correctly
                job = await job_manager.get_job(job_id)
                if job and job["is_recurring"] and job["cron_expression"]:
                    print("🎉 Recurring job test PASSED - job created correctly!")
                    self.test_results["recurring_sqlite"] = True
                else:
                    print("❌ Recurring job test FAILED - job not created correctly")
                    self.test_results["recurring_sqlite"] = False

            else:
                print(f"❌ Failed to parse 'every minute' as cron expression: {cron_expression}")
                self.test_results["recurring_sqlite"] = False

        except Exception as e:
            print(f"❌ Recurring SQLite test failed: {e}")
            self.test_results["recurring_sqlite"] = False
            import traceback

            traceback.print_exc()

        print()

    async def test_postgres_multiuser(self):
        """Test PostgreSQL with multiple users."""
        print("👥 Testing PostgreSQL Multi-User")
        print("=" * 50)

        try:
            # Initialize database manager
            db_manager = get_database_manager(self.postgres_url)
            job_manager = JobManager(db_manager)
            await job_manager.initialize()

            # Create jobs for two different users
            parser = ScheduleParser()

            # User A: Recurring job
            cron_expr = await parser.parse_schedule("every minute", "UTC")
            job_a_id = await job_manager.create_job(
                user_id="user_a_postgres",
                formation_id="test_formation",
                title="User A Recurring Job",
                original_prompt="remind me every minute",
                execution_prompt="Hello from User A!",
                cron_expression=cron_expr,
                is_recurring=True,
            )

            # User B: One-time job
            onetime_result = await parser.parse_schedule("in 2 minutes", "UTC")
            if isinstance(onetime_result, dict):
                job_b_id = await job_manager.create_job(
                    user_id="user_b_postgres",
                    formation_id="test_formation",
                    title="User B One-time Job",
                    original_prompt="remind me in 2 minutes",
                    execution_prompt="Hello from User B!",
                    scheduled_for=onetime_result["scheduled_for"],
                    is_recurring=False,
                )

            print(f"✅ Created User A job: {job_a_id}")
            print(f"✅ Created User B job: {job_b_id}")

            # Verify user isolation
            user_a_jobs = await job_manager.get_user_jobs("user_a_postgres")
            user_b_jobs = await job_manager.get_user_jobs("user_b_postgres")

            print(f"User A has {len(user_a_jobs)} job(s)")
            print(f"User B has {len(user_b_jobs)} job(s)")

            if len(user_a_jobs) > 0 and len(user_b_jobs) > 0:
                user_a_recurring = user_a_jobs[0]["is_recurring"]
                user_b_onetime = not user_b_jobs[0]["is_recurring"]

                if user_a_recurring and user_b_onetime:
                    print("🎉 PostgreSQL multi-user test PASSED - proper isolation!")
                    self.test_results["postgres_multiuser"] = True
                else:
                    print("❌ PostgreSQL multi-user test FAILED - job types wrong")
                    self.test_results["postgres_multiuser"] = False
            else:
                print("❌ PostgreSQL multi-user test FAILED - jobs not created")
                self.test_results["postgres_multiuser"] = False

        except Exception as e:
            print(f"❌ PostgreSQL multi-user test failed: {e}")
            self.test_results["postgres_multiuser"] = False
            import traceback

            traceback.print_exc()

        print()

    async def test_job_type_detection(self):
        """Test intelligent job type detection."""
        print("🧠 Testing Job Type Detection")
        print("=" * 50)

        try:
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
                print("🎉 Job type detection test PASSED - all detections correct!")
                self.test_results["job_type_detection"] = True
            else:
                print("❌ Job type detection test FAILED - some detections wrong")
                self.test_results["job_type_detection"] = False

        except Exception as e:
            print(f"❌ Job type detection test failed: {e}")
            self.test_results["job_type_detection"] = False
            import traceback

            traceback.print_exc()

        print()

    async def run_all_tests(self):
        """Run all tests."""
        print("🚀 Simple Scheduler Real-World Tests")
        print("=" * 60)
        print()

        # Run tests
        await self.test_job_type_detection()
        await self.test_recurring_job_sqlite()
        await self.test_onetime_job_sqlite()
        await self.test_postgres_multiuser()

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
            print("🎉 All tests PASSED!")
            print("\n✅ Core scheduler functionality verified:")
            print("  - Job type detection works correctly")
            print("  - One-time job parsing and creation")
            print("  - Recurring job parsing and creation")
            print("  - SQLite database support")
            print("  - PostgreSQL database support")
            print("  - Multi-user job isolation")
        else:
            print("🚨 Some tests FAILED!")


async def main():
    """Main test runner."""
    test_runner = SimpleSchedulerTest()
    await test_runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
