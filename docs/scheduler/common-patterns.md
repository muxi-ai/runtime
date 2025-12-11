# Scheduler Common Patterns

**Real-world scheduling patterns from production test suite**

This guide shows proven scheduling patterns extracted from the MUXI test suite (`e2e/tests/12_scheduling/`). Each pattern has been tested and validated.

## Daily Tasks

### Morning Reminders

```python
await overlord.chat(
    "Remind me every day at 9am to check emails",
    user_id="user_id",
    session_id="session_id",
    use_async=False,
    stream=False
)
```

**Cron expression**: `0 9 * * *`
**Use cases**:
- Morning briefings
- Daily standup reminders
- Calendar reviews

### End of Day Tasks

```python
await overlord.chat(
    "Every day at 5pm, summarize today's accomplishments",
    user_id="user_id"
)
```

**Cron expression**: `0 17 * * *`
**Use cases**:
- Daily reports
- Task completion summaries
- Email digests

### Multiple Daily Checkpoints

```python
# Morning check
await overlord.chat("Check system status every day at 9am", user_id="user_id")

# Afternoon check
await overlord.chat("Review progress every day at 2pm", user_id="user_id")

# Evening wrap-up
await overlord.chat("Generate daily report every day at 6pm", user_id="user_id")
```

## Weekly Tasks

### Monday Morning Planning

```python
await overlord.chat(
    "Schedule team sync every Monday at 2pm",
    user_id="user_id"
)
```

**Cron expression**: `0 14 * * 1`
**Use cases**:
- Weekly team meetings
- Week planning sessions
- Status updates

### Friday Wrap-ups

```python
await overlord.chat(
    "Every Friday at 4pm, generate weekly summary report",
    user_id="user_id"
)
```

**Cron expression**: `0 16 * * 5`
**Use cases**:
- Weekly reports
- Project summaries
- Team updates

### Weekday vs Weekend

```python
# Weekdays only
await overlord.chat(
    "Check work email every weekday at 8am",
    user_id="user_id"
)
# Cron: 0 8 * * 1-5

# Weekends only
await overlord.chat(
    "Send personal weekly digest every Saturday at 10am",
    user_id="user_id"
)
# Cron: 0 10 * * 6
```

## Interval-Based Tasks

### Hourly Monitoring

```python
await overlord.chat(
    "Check server status every hour",
    user_id="user_id"
)
```

**Cron expression**: `0 * * * *`
**Use cases**:
- System health checks
- Monitoring dashboards
- Alert systems

### Every N Minutes

```python
# Every 30 minutes
await overlord.chat(
    "Check for new messages every 30 minutes",
    user_id="user_id"
)
# Cron: */30 * * * *

# Every 15 minutes
await overlord.chat(
    "Update dashboard every 15 minutes",
    user_id="user_id"
)
# Cron: */15 * * * *
```

### Business Hours Only

```python
await overlord.chat(
    "Monitor system every hour during business hours (9am-5pm)",
    user_id="user_id"
)
```

**Cron expression**: `0 9-17 * * *`
**Use cases**:
- Office hour monitoring
- Work-time only alerts
- Business day operations

## One-Time Tasks

### Tomorrow

```python
await overlord.chat(
    "Schedule a meeting tomorrow at 3pm",
    user_id="user_id"
)
```

**Type**: One-time execution
**Use cases**:
- Specific meeting reminders
- One-off deadlines
- Future notifications

### Relative Time

```python
# In 5 minutes
await overlord.chat(
    "In 5 minutes, generate a status report",
    user_id="user_id"
)

# Next week
await overlord.chat(
    "Remind me next Monday at 10am about the project review",
    user_id="user_id"
)
```

## Natural Language Patterns

### Time Expressions

These patterns are automatically parsed by the scheduler:

```python
# Absolute times
"every day at 9am"
"every day at 3:30pm"
"at midnight"
"at noon"

# Relative times
"every hour"
"every 30 minutes"
"every 2 hours"

# Day patterns
"every Monday"
"every weekday"
"every weekend"
"every Friday"

# Complex patterns
"every Monday at 10am"
"every weekday at 2pm"
"twice daily at 9am and 6pm"
```

### Exclusion Patterns

```python
# Exclude weekends
await overlord.chat(
    "Check emails every day except weekends at 9am",
    user_id="user_id"
)

# Exclude holidays
await overlord.chat(
    "Generate report every weekday except holidays at 8am",
    user_id="user_id"
)

# Exclude specific times
await overlord.chat(
    "Monitor system every hour except between 2am and 4am",
    user_id="user_id"
)
```

## Project Management

### Daily Standups

```python
async def setup_standup_reminders():
    """Set up daily standup notifications."""

    # Morning prep
    await overlord.chat(
        "Every weekday at 8:45am, remind me to prepare for standup",
        user_id="team_lead"
    )

    # Standup time
    await overlord.chat(
        "Every weekday at 9am, send standup meeting reminder to team",
        user_id="team_lead"
    )

    # Follow-up
    await overlord.chat(
        "Every weekday at 9:30am, summarize action items from standup",
        user_id="team_lead"
    )
```

### Sprint Management

```python
async def setup_sprint_schedule():
    """Set up bi-weekly sprint cadence."""

    # Sprint planning (every 2 weeks)
    await overlord.chat(
        "Every other Monday at 10am, prepare sprint planning agenda",
        user_id="scrum_master"
    )

    # Sprint review (Friday before sprint end)
    await overlord.chat(
        "Every other Friday at 2pm, send sprint review invitation",
        user_id="scrum_master"
    )

    # Sprint retrospective
    await overlord.chat(
        "Every other Friday at 4pm, collect retrospective feedback",
        user_id="scrum_master"
    )
```

### Task Tracking

```python
async def setup_task_tracking():
    """Set up automated task monitoring."""

    # Daily progress check
    await overlord.chat(
        "Every weekday at 5pm, review today's completed tasks",
        user_id="project_manager"
    )

    # Overdue task alerts
    await overlord.chat(
        "Every morning at 8am, list overdue tasks",
        user_id="project_manager"
    )

    # Weekly status report
    await overlord.chat(
        "Every Friday at 3pm, generate weekly progress report",
        user_id="project_manager"
    )
```

## Email Management

### Inbox Monitoring

```python
async def setup_email_monitoring():
    """Set up automated email management."""

    # Urgent email check
    await overlord.chat(
        "Check for urgent emails every 2 hours during business hours",
        user_id="user_id"
    )

    # Morning digest
    await overlord.chat(
        "Every day at 8am, send summary of yesterday's important emails",
        user_id="user_id"
    )

    # End of day cleanup
    await overlord.chat(
        "Every day at 6pm, archive processed emails",
        user_id="user_id"
    )
```

### VIP Email Alerts

```python
await overlord.chat(
    "Check for emails from VIP contacts every 30 minutes and alert me",
    user_id="user_id"
)
```

## Content Creation

### Social Media Scheduling

```python
async def setup_social_media():
    """Schedule social media content workflow."""

    # Content brainstorming
    await overlord.chat(
        "Every Tuesday at 10am, generate 5 social media post ideas",
        user_id="content_manager"
    )

    # Post drafting
    await overlord.chat(
        "Every Wednesday at 2pm, draft posts for next week",
        user_id="content_manager"
    )

    # Content review
    await overlord.chat(
        "Every Friday at 11am, prepare social media content calendar",
        user_id="content_manager"
    )
```

### Blog Post Pipeline

```python
async def setup_blog_pipeline():
    """Set up blog content creation schedule."""

    # Topic research
    await overlord.chat(
        "Every Monday at 9am, research trending topics in our industry",
        user_id="blog_writer"
    )

    # Outline creation
    await overlord.chat(
        "Every Tuesday at 10am, create blog post outline",
        user_id="blog_writer"
    )

    # Draft reminder
    await overlord.chat(
        "Every Thursday at 2pm, remind me to complete blog draft",
        user_id="blog_writer"
    )
```

## System Monitoring

### Health Checks

```python
async def setup_health_monitoring():
    """Set up comprehensive system monitoring."""

    # Frequent checks
    await overlord.chat(
        "Check system health every 15 minutes",
        user_id="devops"
    )

    # Resource monitoring
    await overlord.chat(
        "Monitor CPU and memory usage every hour",
        user_id="devops"
    )

    # Daily reports
    await overlord.chat(
        "Generate daily system health report at 8am",
        user_id="devops"
    )
```

### Backup Management

```python
async def setup_backup_schedule():
    """Configure automated backup checks."""

    # Hourly incremental
    await overlord.chat(
        "Verify hourly backup completed successfully",
        user_id="admin"
    )

    # Daily full backup
    await overlord.chat(
        "Run full system backup every day at 2am",
        user_id="admin"
    )

    # Weekly backup verification
    await overlord.chat(
        "Test backup restoration every Sunday at 3am",
        user_id="admin"
    )
```

## Reporting

### Daily Metrics

```python
async def setup_daily_reporting():
    """Configure daily metrics and KPI reporting."""

    # Morning metrics
    await overlord.chat(
        "Every weekday at 8am, generate yesterday's key metrics",
        user_id="analyst"
    )

    # Business hours updates
    await overlord.chat(
        "Update real-time dashboard every hour from 9am to 5pm",
        user_id="analyst"
    )

    # End of day summary
    await overlord.chat(
        "Every day at 6pm, compile daily performance summary",
        user_id="analyst"
    )
```

### Weekly and Monthly Reports

```python
async def setup_periodic_reporting():
    """Set up weekly and monthly reporting schedules."""

    # Weekly reports
    await overlord.chat(
        "Every Friday at 4pm, generate weekly performance report",
        user_id="manager"
    )

    # Monthly reports (first of month)
    await overlord.chat(
        "First day of every month at 9am, create monthly summary",
        user_id="manager"
    )

    # Quarterly reviews (every 3 months)
    await overlord.chat(
        "First Monday of January, April, July, October at 10am, prepare quarterly review",
        user_id="executive"
    )
```

## Testing and Validation

### Development Workflow

```python
async def setup_ci_cd_monitoring():
    """Monitor CI/CD pipeline automatically."""

    # Build monitoring
    await overlord.chat(
        "Check build status every 30 minutes during work hours",
        user_id="developer"
    )

    # Test results
    await overlord.chat(
        "Review test results every hour",
        user_id="qa_engineer"
    )

    # Deployment tracking
    await overlord.chat(
        "Monitor production deployments every 15 minutes",
        user_id="devops"
    )
```

## Best Practices from Tests

### 1. Use Specific User IDs

```python
# Good - unique user IDs for isolation
await overlord.chat(message, user_id="user_123")

# Avoid - generic IDs can cause conflicts
await overlord.chat(message, user_id="test")
```

### 2. Always Use Session IDs

```python
# Good - maintains conversation context
await overlord.chat(
    message,
    user_id="user_123",
    session_id="session_456"
)

# Works but less ideal
await overlord.chat(message, user_id="user_123")
```

### 3. Disable Async for Immediate Response

```python
# For immediate confirmation
response = await overlord.chat(
    message,
    user_id="user_id",
    use_async=False,  # Get immediate response
    stream=False      # No streaming
)
```

### 4. Verify Job Creation

```python
# Always verify job was created
response = await overlord.chat(scheduling_message, user_id="user_id")

# Check response
if "scheduled" in response.content.lower():
    print("✅ Job created successfully")

    # Get job details
    jobs = await formation.get_user_jobs("user_id")
    latest_job = jobs[-1]
    print(f"Job ID: {latest_job['id']}")
else:
    print("❌ Job creation failed")
```

### 5. Handle Errors Gracefully

```python
try:
    response = await overlord.chat(message, user_id="user_id")

    if "scheduled" in response.content.lower():
        # Extract job ID
        if "job id:" in response.content.lower():
            # Parse job ID from response
            pass
    else:
        print(f"Unexpected response: {response.content}")

except Exception as e:
    print(f"Error creating job: {e}")
    # Log error, notify admin, etc.
```

## Complete Working Example

Here's a production-ready example that combines multiple patterns:

```python
#!/usr/bin/env python3
"""
Production scheduler setup for a development team.
"""

import asyncio
from pathlib import Path
from muxi.formation.formation import Formation


async def setup_team_scheduler():
    """Configure complete team scheduling automation."""

    # Initialize formation
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    # Daily standup reminders
    await overlord.chat(
        "Every weekday at 8:45am, remind team about standup in 15 minutes",
        user_id="team_lead"
    )

    # Code review reminders
    await overlord.chat(
        "Every weekday at 10am and 3pm, remind team to review pending PRs",
        user_id="tech_lead"
    )

    # Daily deployment status
    await overlord.chat(
        "Every weekday at 5pm, summarize today's deployments and issues",
        user_id="devops"
    )

    # Weekly planning
    await overlord.chat(
        "Every Monday at 9am, prepare sprint planning agenda",
        user_id="scrum_master"
    )

    # Weekly retrospective
    await overlord.chat(
        "Every Friday at 4pm, collect team feedback for retrospective",
        user_id="scrum_master"
    )

    # System health monitoring
    await overlord.chat(
        "Check system health every 15 minutes and alert on issues",
        user_id="sre"
    )

    # Backup verification
    await overlord.chat(
        "Verify backup completed successfully every day at 3am",
        user_id="admin"
    )

    # Monthly reporting
    await overlord.chat(
        "First day of each month at 9am, generate monthly team metrics",
        user_id="manager"
    )

    # Verify all jobs created
    all_jobs = await formation.get_active_jobs()
    print(f"\n✅ Created {len(all_jobs)} scheduled jobs")

    # Show summary
    for job in all_jobs:
        print(f"  - {job['title']} ({job['cron_expression']})")

    await formation.kill_overlord()


if __name__ == "__main__":
    asyncio.run(setup_team_scheduler())
```

## See Also

- **[Quick Start Guide](quickstart.md)** - Get started in 5 minutes
- **[Tutorial](tutorial.md)** - Step-by-step learning
- **[Test Suite](../../e2e/tests/12_scheduling/)** - 12 comprehensive test examples
- **[API Reference](formation-api.md)** - Complete API documentation

## Contributing Patterns

Found a useful pattern? Consider:
1. Testing it with the test suite
2. Documenting it here
3. Sharing with the community

These patterns are extracted from `e2e/tests/12_scheduling/` and have been validated in production use.
