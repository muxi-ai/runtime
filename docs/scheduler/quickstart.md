# MUXI Scheduler Quick Start Guide

**Get started with scheduling in 5 minutes**

## What is the MUXI Scheduler?

The MUXI Scheduler transforms your AI assistant from reactive (responds when asked) to proactive (acts on a schedule). Simply say "remind me every day at 9am to check my calendar" and MUXI will automatically execute that task daily.

## Prerequisites

- MUXI Runtime installed
- A database (PostgreSQL or SQLite)
- Python 3.10+

## Step 1: Enable Scheduler (2 minutes)

Add scheduler configuration to your `formation.afs`:

```yaml
# formation.afs (or .yaml)
scheduler:
  enabled: true
  check_interval_minutes: 1
  max_concurrent_jobs: 5
  max_failures_before_pause: 3
  timezone: "America/New_York"  # Your timezone

memory:
  persistent:
    connection_string: "${{ secrets.POSTGRES_URI }}"

agents:
  - id: assistant
    system_message: "You are a helpful assistant."
    llm_models:
      - text: "openai/gpt-4o-mini"
```

**For SQLite (simpler for testing):**
```yaml
memory:
  persistent:
    connection_string: "sqlite:///./scheduler.db"
```

## Step 2: Create Your First Scheduled Task (2 minutes)

### Using Python API

```python
import asyncio
from pathlib import Path
from muxi.formation.formation import Formation

async def schedule_daily_reminder():
    # Load formation
    formation = Formation()
    await formation.load("formation.afs")  # or Path to your formation directory
    overlord = await formation.start_overlord()

    # Schedule a task using natural language
    response = await overlord.chat(
        "Remind me every day at 9am to check my calendar",
        user_id="your_user_id",
        session_id="session_1",
        use_async=False,
        stream=False
    )

    print(response.content)

    # Cleanup
    await formation.kill_overlord()

# Run it
asyncio.run(schedule_daily_reminder())
```

**Expected output:**
```
✅ I've created a scheduled job for you. Your request 'check my calendar'
will be executed daily at 9:00 AM. Job ID: job_abc123xyz456
```

## Step 3: Verify Your Scheduled Job (1 minute)

```python
async def check_jobs():
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    # Get all jobs for your user
    jobs = await formation.get_user_jobs("your_user_id")

    for job in jobs:
        print(f"📅 {job['title']}")
        print(f"   Schedule: {job['cron_expression']}")
        print(f"   Status: {job['status']}")
        print(f"   Created: {job['created_at']}")

    await formation.kill_overlord()

asyncio.run(check_jobs())
```

**Expected output:**
```
📅 Scheduled: check my calendar
   Schedule: 0 9 * * *
   Status: ACTIVE
   Created: 2025-10-09T14:30:00Z
```

## Natural Language Examples

The scheduler understands various time patterns:

### Daily Tasks
```python
"Remind me every day at 9am to check emails"
"Send daily report at 5pm"
"Check system status every day at midnight"
```

### Weekly Tasks
```python
"Schedule team meeting every Monday at 10am"
"Send weekly summary every Friday at 4pm"
"Run backup every Sunday at 3am"
```

### Hourly/Interval Tasks
```python
"Check for new messages every 30 minutes"
"Monitor server every 2 hours"
"Update dashboard every 15 minutes during business hours"
```

### One-Time Tasks
```python
"Remind me tomorrow at 2pm about the meeting"
"Send report in 5 minutes"
"Schedule call next Monday at 3pm"
```

## Complete Working Example

Here's a complete example from our test suite that you can run:

```python
#!/usr/bin/env python3
"""Complete scheduler example."""

import asyncio
import sys
from pathlib import Path
from muxi.formation.formation import Formation


async def main():
    """Test basic scheduling functionality."""
    print("\n" + "="*60)
    print("Scheduler Example: Creating Multiple Scheduled Tasks")
    print("="*60)

    # Path to your formation
    formation_path = Path("./formation-scheduling")  # Update this path

    try:
        # Initialize formation
        print("\n[Setup] Initializing formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Test cases - various scheduling patterns
        test_cases = [
            {
                "name": "Daily Email Check",
                "message": "Remind me every day at 9am to check emails",
                "type": "recurring"
            },
            {
                "name": "Tomorrow's Meeting",
                "message": "Schedule a meeting reminder tomorrow at 3pm",
                "type": "one-off"
            },
            {
                "name": "Weekly Team Sync",
                "message": "Schedule team sync every Monday at 2pm",
                "type": "recurring"
            },
        ]

        results = []

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[Test {i}/{len(test_cases)}] {test_case['name']}")
            print(f"  Message: {test_case['message']}")
            print(f"  Type: {test_case['type']}")

            try:
                # Send the scheduling request
                response = await overlord.chat(
                    message=test_case['message'],
                    user_id=f"user_{i}",
                    session_id=f"session_{i}",
                    use_async=False,
                    stream=False
                )

                # Check the response
                content = response.content if hasattr(response, 'content') else str(response)

                if "scheduled" in content.lower():
                    print("  ✅ SUCCESS: Job created")
                    # Extract job ID if present
                    if "job id:" in content.lower():
                        job_id_start = content.lower().index("job id:") + 7
                        job_id_end = content.find(")", job_id_start) if ")" in content[job_id_start:] else len(content)
                        job_id = content[job_id_start:job_id_end].strip()
                        print(f"     Job ID: {job_id}")
                    results.append(True)
                else:
                    print(f"  ❌ FAILED: Unexpected response")
                    print(f"     Got: {content[:150]}...")
                    results.append(False)

            except Exception as e:
                print(f"  ❌ ERROR: {str(e)}")
                results.append(False)

        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)

        passed = sum(results)
        total = len(results)

        print(f"✅ Passed: {passed}/{total}")

        if passed == total:
            print("\n🎉 All scheduling tasks created successfully!")
        else:
            print(f"\n⚠️  {total - passed} tasks failed")

        # Show all scheduled jobs
        print("\n" + "="*60)
        print("YOUR SCHEDULED JOBS")
        print("="*60)

        for i in range(1, len(test_cases) + 1):
            jobs = await formation.get_user_jobs(f"user_{i}")
            for job in jobs:
                print(f"\n📅 {job['title']}")
                print(f"   User: user_{i}")
                print(f"   Schedule: {job['cron_expression'] or job['scheduled_for']}")
                print(f"   Status: {job['status']}")

        # Cleanup
        await formation.kill_overlord()

        return 0 if passed == total else 1

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print(f"\nExit code: {exit_code}")
    sys.exit(exit_code)
```

Save this as `example_scheduler.py` and run it:

```bash
python example_scheduler.py
```

## Next Steps

### 1. **Manage Your Jobs**

```python
# Get all active jobs
jobs = await formation.get_active_jobs()

# Get jobs for specific user
user_jobs = await formation.get_user_jobs("your_user_id")

# Get job audit trail (who created, modified, deleted)
audit = await formation.get_job_audit_trail(job_id)

# Get recent scheduler activity
recent = await formation.get_recent_audit_trail(limit=10)
```

### 2. **Pause/Resume Jobs**

```python
# Get scheduler service for write operations
scheduler = overlord.scheduler_service

# Pause a job
await scheduler.job_manager.pause_job(
    job_id,
    user_id,
    reason="Going on vacation"
)

# Resume a job
await scheduler.job_manager.resume_job(job_id, user_id)

# Delete a job
await scheduler.job_manager.delete_job(
    job_id,
    user_id,
    reason="No longer needed"
)
```

### 3. **Monitor Job Execution**

```python
# Check job statistics
jobs = await formation.get_user_jobs("your_user_id")
for job in jobs:
    print(f"{job['title']}:")
    print(f"  Total runs: {job['total_runs']}")
    print(f"  Failures: {job['total_failures']}")
    print(f"  Last run: {job['last_run_at']}")
    print(f"  Last status: {job['last_run_status']}")

    if job['total_runs'] > 0:
        success_rate = (job['total_runs'] - job['total_failures']) / job['total_runs']
        print(f"  Success rate: {success_rate:.1%}")
```

## Troubleshooting

### Scheduler Not Starting

**Check formation config:**
```yaml
scheduler:
  enabled: true  # ← Must be true
```

**Check logs for errors:**
```python
import logging
logging.getLogger('muxi.services.scheduler').setLevel(logging.DEBUG)
```

### Jobs Not Executing

**Verify job status:**
```python
jobs = await formation.get_user_jobs("your_user_id")
for job in jobs:
    if job['status'] != 'ACTIVE':
        print(f"⚠️  Job {job['title']} is {job['status']}")
```

**Check cron expression:**
```python
from croniter import croniter

job = jobs[0]
if croniter.is_valid(job['cron_expression']):
    print("✅ Cron expression is valid")
    # Show next 5 execution times
    from datetime import datetime
    cron = croniter(job['cron_expression'], datetime.now())
    print("Next 5 executions:")
    for i in range(5):
        print(f"  {cron.get_next(datetime)}")
else:
    print("❌ Invalid cron expression")
```

### Database Connection Issues

**Test database connection:**
```python
scheduler = overlord.scheduler_service
try:
    jobs = await scheduler.job_manager.get_active_jobs()
    print("✅ Database connection OK")
except Exception as e:
    print(f"❌ Database error: {e}")
    print("\nCheck your connection string in formation.afs:")
    print("  PostgreSQL: postgresql://user:pass@host:port/db")
    print("  SQLite: sqlite:///./scheduler.db")
```

## Key Concepts

### Cron Expressions

The scheduler converts natural language to cron expressions:

```
Format: minute hour day month weekday
        0-59   0-23 1-31 1-12  0-6 (0=Sunday)

Examples:
  0 9 * * *      Every day at 9am
  0 14 * * 1-5   Weekdays at 2pm
  */30 * * * *   Every 30 minutes
  0 0 1 * *      First day of month
  0 18 * * 5     Every Friday at 6pm
```

### Job Lifecycle

1. **ACTIVE** - Job is running on schedule
2. **PAUSED** - Manually paused or auto-paused due to failures
3. **COMPLETED** - One-time job that has executed
4. **DELETED** - Job removed (soft delete)

### User Isolation

- Each user's jobs are isolated
- Jobs execute with the original user's context
- One user cannot see or modify another user's jobs

## Real-World Examples

### Email Management
```python
await overlord.chat(
    "Check for urgent emails every 2 hours during business hours",
    user_id="user_123"
)
```

### Report Generation
```python
await overlord.chat(
    "Generate daily sales report at 8am on weekdays",
    user_id="user_123"
)
```

### System Monitoring
```python
await overlord.chat(
    "Check server health every 15 minutes and alert if issues found",
    user_id="user_123"
)
```

### Content Creation
```python
await overlord.chat(
    "Draft social media posts every Tuesday and Thursday at 10am",
    user_id="user_123"
)
```

## Learn More

- **[Full Documentation](README.md)** - Complete scheduler documentation
- **[Usage Guide](usage-guide.md)** - Comprehensive usage patterns
- **[Tutorial](tutorial.md)** - Step-by-step tutorial
- **[Architecture](architecture.md)** - Technical deep dive
- **[API Reference](formation-api.md)** - Complete API documentation

## Support

- **Test Suite**: See `e2e/tests/12_scheduling/` for working examples
- **Issues**: Check test results in test reports for common patterns
- **Debug**: Enable debug logging for detailed execution traces

---

**🎉 You're ready to schedule!** Start with simple daily tasks and gradually build more complex scheduling patterns as you become comfortable with the system.
