# One-Time Job Scheduling

**New Feature**: The MUXI Scheduler now supports one-time jobs alongside recurring jobs, enabling users to schedule tasks for specific dates and times.

## Overview

Users can now schedule tasks that execute once at a specific time, in addition to recurring tasks. The system intelligently detects whether a request is for a one-time or recurring job and handles them appropriately.

## Examples

### One-Time Jobs
```python
# Natural language examples that create one-time jobs:
"Remind me to call mom tomorrow at 2pm"
"Send project report next Friday"
"Check server status on December 25th at noon"
"Review quarterly data in 3 days"
"Do maintenance next week"
```

### Recurring Jobs (Existing Functionality)
```python
# Natural language examples that create recurring jobs:
"Remind me to call mom every day at 2pm"
"Send project report every Friday"
"Check server status daily"
"Review quarterly data every quarter"
"Do maintenance weekly"
```

## How It Works

### 1. Intelligent Job Type Detection

The scheduler uses pattern matching and LLM analysis to detect job types:

```python
from muxi.services.scheduler.parser import ScheduleParser

parser = ScheduleParser()

# Detect job type
job_type = await parser._detect_job_type("remind me tomorrow")
# Returns: "one_time"

job_type = await parser._detect_job_type("remind me daily")
# Returns: "recurring"
```

### 2. Natural Language Datetime Parsing

For one-time jobs, the system parses specific dates and times:

```python
# Parse specific datetime
result = await parser._parse_specific_datetime(
    "tomorrow at 2pm",
    timezone="America/New_York"
)

# Returns:
# {
#     "job_type": "one_time",
#     "scheduled_for": datetime(2025, 6, 23, 18, 0, 0, tzinfo=UTC),
#     "timezone": "America/New_York",
#     "original_text": "tomorrow at 2pm"
# }
```

### 3. Job Creation

Create jobs programmatically with the enhanced API:

```python
from muxi.services.scheduler.manager import JobManager
from datetime import datetime, timedelta
import pytz

# One-time job
scheduled_time = datetime.now(pytz.UTC) + timedelta(days=1)
job_id = await job_manager.create_job(
    user_id="user123",
    formation_id="formation456",
    title="One-time Reminder",
    original_prompt="remind me tomorrow",
    execution_prompt="Don't forget your appointment!",
    scheduled_for=scheduled_time,
    is_recurring=False,  # Key difference
)

# Recurring job (existing functionality)
job_id = await job_manager.create_job(
    user_id="user123",
    formation_id="formation456",
    title="Daily Reminder",
    original_prompt="remind me daily",
    execution_prompt="Daily reminder message",
    cron_expression="0 9 * * *",
    is_recurring=True,  # Default value
)
```

## Database Schema

The enhanced database schema supports both job types:

```sql
-- New fields added to scheduled_jobs table
ALTER TABLE scheduled_jobs ADD COLUMN is_recurring BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE scheduled_jobs ADD COLUMN scheduled_for TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE scheduled_jobs ALTER COLUMN cron_expression DROP NOT NULL;

-- Updated status constraint to include 'COMPLETED'
ALTER TABLE scheduled_jobs ADD CONSTRAINT scheduled_jobs_status_check
CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED'));
```

## Job Lifecycle

### One-Time Jobs
1. **Created** - Job is created with `status='ACTIVE'` and `is_recurring=False`
2. **Scheduled** - System waits until `scheduled_for` datetime
3. **Executed** - Job runs once at the specified time
4. **Completed** - Job status changes to `'COMPLETED'` automatically
5. **Finished** - Job no longer appears in active job queries

### Recurring Jobs
1. **Created** - Job is created with `status='ACTIVE'` and `is_recurring=True`
2. **Scheduled** - System evaluates cron expression continuously
3. **Executed** - Job runs according to cron schedule
4. **Continues** - Job remains `'ACTIVE'` and continues executing

## API Reference

### ScheduleParser

```python
class ScheduleParser:
    async def parse_schedule(self, schedule_text: str, timezone: str = "UTC") -> Union[str, Dict[str, Any]]:
        """
        Parse natural language schedule.

        Returns:
            For recurring jobs: Cron expression string
            For one-time jobs: Dict with job type and scheduled datetime
        """

    async def _detect_job_type(self, schedule_text: str) -> str:
        """
        Detect whether request is for one-time or recurring job.

        Returns:
            "one_time" or "recurring"
        """

    async def _parse_specific_datetime(self, schedule_text: str, timezone: str = "UTC") -> Optional[Dict[str, Any]]:
        """
        Parse specific datetime for one-time jobs.

        Returns:
            Dict with job type and scheduled datetime, or None if parsing fails
        """
```

### JobManager

```python
class JobManager:
    async def create_job(
        self,
        user_id: str,
        formation_id: str,
        title: str,
        original_prompt: str,
        execution_prompt: str,
        cron_expression: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        is_recurring: bool = True,
        exclusion_rules: List[Dict[str, Any]] = None,
    ) -> str:
        """Create a new scheduled job (recurring or one-time)."""

    async def complete_onetime_job(self, job_id: str) -> bool:
        """Mark a one-time job as completed."""
```

## Configuration

No additional configuration is required. The feature works with existing scheduler settings:

```yaml
# formation.yaml
scheduler:
  enabled: true
  check_interval_minutes: 1
  max_concurrent_jobs: 10
  timezone: "America/New_York"

memory:
  persistent:
    connection_string: "${POSTGRES_DATABASE_URL}"
```

## Migration

Run the database migration to add one-time job support:

```bash
# The migration script handles both PostgreSQL and SQLite
python migrations/20250622190000_add_onetime_job_support.py
```

Existing recurring jobs continue to work without changes. They are automatically marked as `is_recurring=True` during migration.

## Examples

### Basic Usage

```python
import asyncio
from muxi.formation import Formation

async def demo_onetime_jobs():
    # Load formation with scheduler enabled
    formation = Formation()
    await formation.load("formation.yaml")
    overlord = await formation.start_overlord()

    # Schedule one-time tasks using natural language
    response1 = await overlord.chat(
        "Remind me to call the dentist tomorrow at 3pm",
        user_id="user123"
    )

    response2 = await overlord.chat(
        "Send me a project update next Friday morning",
        user_id="user123"
    )

    # Schedule recurring tasks (existing functionality)
    response3 = await overlord.chat(
        "Send me daily weather updates every morning at 7am",
        user_id="user123"
    )

    print("All jobs scheduled successfully!")
    return [response1, response2, response3]

asyncio.run(demo_onetime_jobs())
```

### Programmatic Usage

```python
from muxi.services.scheduler.parser import ScheduleParser
from muxi.services.scheduler.manager import JobManager
from datetime import datetime, timedelta
import pytz

async def create_mixed_jobs():
    parser = ScheduleParser()
    job_manager = JobManager(db_manager)

    # Parse and create one-time job
    result = await parser.parse_schedule("tomorrow at 2pm", "UTC")
    if result["job_type"] == "one_time":
        job_id = await job_manager.create_job(
            user_id="user123",
            formation_id="formation456",
            title="One-time Task",
            original_prompt="tomorrow at 2pm",
            execution_prompt="Execute one-time task",
            scheduled_for=result["scheduled_for"],
            is_recurring=False,
        )

    # Create recurring job
    cron_expr = await parser.parse_schedule("every day at 9am", "UTC")
    job_id = await job_manager.create_job(
        user_id="user123",
        formation_id="formation456",
        title="Daily Task",
        original_prompt="every day at 9am",
        execution_prompt="Execute daily task",
        cron_expression=cron_expr,
        is_recurring=True,
    )
```

## Benefits

✅ **Natural Language**: Users can request one-time tasks naturally
✅ **Intelligent Detection**: System automatically determines job type
✅ **Complete Lifecycle**: One-time jobs automatically complete after execution
✅ **Backwards Compatible**: Existing recurring jobs continue to work
✅ **Unified API**: Same interface for both job types
✅ **Database Optimized**: Efficient queries with proper indexing

## Supported Patterns

### One-Time Indicators
- "tomorrow", "next week", "next month"
- "on [specific date]"
- "in X days/weeks/months"
- "this [day of week]"
- "next [day of week]"

### Recurring Indicators
- "every day/week/month"
- "daily", "weekly", "monthly"
- "every [day of week]"
- "every X hours/minutes"

The system uses both pattern matching and LLM analysis to ensure accurate detection even for complex or ambiguous requests.
