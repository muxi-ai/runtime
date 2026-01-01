#!/usr/bin/env python3
"""
MUXI Scheduler One-Time Jobs Demo

This example demonstrates the new one-time job functionality that allows
users to schedule tasks for specific dates/times rather than recurring schedules.

Example usage:
- "Remind me to call mom tomorrow at 2pm"
- "Send project report next Friday"
- "Check server status on December 25th at noon"

The system intelligently detects whether a request is for a one-time or recurring job
and handles them appropriately.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
import pytz

# Add the runtime path so we can import muxi
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from muxi.runtime.formation import Formation
from muxi.runtime.services.scheduler.parser import ScheduleParser
from muxi.runtime.services.scheduler.manager import JobManager
from muxi.runtime.services.db import get_database_manager


async def demo_one_time_job_detection():
    """Demonstrate how the scheduler detects one-time vs recurring jobs."""
    print("🔍 Job Type Detection Demo")
    print("=" * 50)

    parser = ScheduleParser()

    test_requests = [
        # One-time jobs
        ("Remind me to call mom tomorrow at 2pm", "one_time"),
        ("Send report next Friday", "one_time"),
        ("Check server status on December 25th", "one_time"),
        ("Do maintenance next week", "one_time"),
        ("Review quarterly data in 3 days", "one_time"),

        # Recurring jobs
        ("Remind me to call mom every day at 2pm", "recurring"),
        ("Send report every Friday", "recurring"),
        ("Check server status daily", "recurring"),
        ("Do maintenance weekly", "recurring"),
        ("Review quarterly data every 3 months", "recurring"),
    ]

    for request, expected_type in test_requests:
        detected_type = await parser._detect_job_type(request)
        status = "✅" if detected_type == expected_type else "❌"
        print(f"{status} '{request}' → {detected_type}")

    print()


async def demo_datetime_parsing():
    """Demonstrate parsing of specific dates and times."""
    print("📅 Datetime Parsing Demo")
    print("=" * 50)

    parser = ScheduleParser()
    timezone = "America/New_York"

    test_phrases = [
        "tomorrow at 2pm",
        "next week",
        "next month",
        "in 3 days",
    ]

    for phrase in test_phrases:
        try:
            # Use fallback parsing for demo (doesn't require LLM)
            result = parser._fallback_parse_datetime(phrase, timezone)
            scheduled_time = result["scheduled_for"].astimezone(pytz.timezone(timezone))

            print(f"✅ '{phrase}' → {scheduled_time.strftime('%Y-%m-%d %H:%M %Z')}")
        except Exception as e:
            print(f"❌ '{phrase}' → Error: {e}")

    print()


async def demo_job_creation():
    """Demonstrate creating one-time vs recurring jobs."""
    print("📝 Job Creation Demo")
    print("=" * 50)

    # Create a test database manager (SQLite for demo)
    connection_string = "sqlite:///./demo_scheduler.db"
    db_manager = get_database_manager(connection_string)

    job_manager = JobManager(db_manager)
    await job_manager.initialize()

    # Create a one-time job
    tomorrow = datetime.now(pytz.UTC) + timedelta(days=1)
    tomorrow = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)

    onetime_job_id = await job_manager.create_job(
        user_id="demo_user",
        formation_id="demo_formation",
        title="One-time Reminder",
        original_prompt="remind me tomorrow at 2pm",
        execution_prompt="Send reminder: Don't forget your appointment!",
        cron_expression=None,
        scheduled_for=tomorrow,
        is_recurring=False,
    )
    print(f"✅ Created one-time job: {onetime_job_id}")

    # Create a recurring job (existing functionality)
    recurring_job_id = await job_manager.create_job(
        user_id="demo_user",
        formation_id="demo_formation",
        title="Daily Reminder",
        original_prompt="remind me every day at 9am",
        execution_prompt="Send daily reminder: Start your day!",
        cron_expression="0 9 * * *",
        is_recurring=True,
    )
    print(f"✅ Created recurring job: {recurring_job_id}")

    # Show job details
    onetime_job = await job_manager.get_job(onetime_job_id)
    recurring_job = await job_manager.get_job(recurring_job_id)

    print("\n📊 Job Details:")
    print(f"One-time job: {onetime_job['title']} (scheduled for: {onetime_job['scheduled_for']})")
    print(f"Recurring job: {recurring_job['title']} (cron: {recurring_job['cron_expression']})")

    print()


async def demo_natural_language_scheduling():
    """Demonstrate natural language scheduling examples."""
    print("🗣️  Natural Language Scheduling Examples")
    print("=" * 50)

    examples = [
        # One-time scheduling examples
        {
            "user_request": "I want you to remind me to call my dentist tomorrow at 3pm",
            "job_type": "one_time",
            "description": "Sets up a one-time reminder for tomorrow at 3pm"
        },
        {
            "user_request": "Send me a summary of this week's progress next Friday morning",
            "job_type": "one_time",
            "description": "Creates a one-time job for next Friday morning"
        },
        {
            "user_request": "Check if the servers are running properly on December 25th at midnight",
            "job_type": "one_time",
            "description": "Schedules a specific date/time system check"
        },

        # Recurring scheduling examples
        {
            "user_request": "Remind me to review my goals every Monday at 9am",
            "job_type": "recurring",
            "description": "Sets up a weekly recurring reminder"
        },
        {
            "user_request": "Send me daily weather updates every morning at 7am",
            "job_type": "recurring",
            "description": "Creates a daily recurring information task"
        },
    ]

    for example in examples:
        print(f"Request: \"{example['user_request']}\"")
        print(f"Type: {example['job_type']}")
        print(f"Result: {example['description']}")
        print()


async def demo_job_lifecycle():
    """Demonstrate the complete lifecycle of a one-time job."""
    print("🔄 One-Time Job Lifecycle Demo")
    print("=" * 50)

    # Create database manager
    connection_string = "sqlite:///./demo_scheduler.db"
    db_manager = get_database_manager(connection_string)
    job_manager = JobManager(db_manager)
    await job_manager.initialize()

    # 1. Create a one-time job
    scheduled_time = datetime.now(pytz.UTC) + timedelta(minutes=5)
    job_id = await job_manager.create_job(
        user_id="demo_user",
        formation_id="demo_formation",
        title="Demo One-time Job",
        original_prompt="remind me in 5 minutes",
        execution_prompt="Demo reminder: 5 minutes have passed!",
        scheduled_for=scheduled_time,
        is_recurring=False,
    )
    print(f"1. ✅ Created job: {job_id}")

    # 2. Check job status
    job = await job_manager.get_job(job_id)
    print(f"2. 📋 Job status: {job['status']}")
    print(f"   Scheduled for: {job['scheduled_for']}")
    print(f"   Is recurring: {job['is_recurring']}")

    # 3. Simulate job execution success
    await job_manager.mark_job_execution_success(job_id, "Demo execution completed")
    print(f"3. ⚡ Simulated job execution")

    # 4. Mark job as completed (this would happen automatically for one-time jobs)
    await job_manager.complete_onetime_job(job_id)
    print(f"4. ✅ Marked job as completed")

    # 5. Check final status
    job = await job_manager.get_job(job_id)
    print(f"5. 🏁 Final status: {job['status']}")

    print()


async def main():
    """Run all demo functions."""
    print("🚀 MUXI Scheduler One-Time Jobs Demo")
    print("=" * 50)
    print()

    try:
        await demo_one_time_job_detection()
        await demo_datetime_parsing()
        await demo_job_creation()
        await demo_natural_language_scheduling()
        await demo_job_lifecycle()

        print("🎉 Demo completed successfully!")
        print("\nKey Features Demonstrated:")
        print("✅ Intelligent job type detection (one-time vs recurring)")
        print("✅ Natural language datetime parsing")
        print("✅ Database support for both job types")
        print("✅ Complete job lifecycle management")
        print("✅ Automatic completion of one-time jobs")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
