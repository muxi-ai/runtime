# MUXI Scheduler Usage Guide

## Quick Start

The MUXI Scheduler enables your AI formation to execute tasks automatically at specified times or intervals. Here's how to get started:

### Enable Scheduler in Your Formation

```yaml
# formation.yaml
scheduler:
  enabled: true
  check_interval_minutes: 1
  timezone: "America/New_York"
```

### Basic Usage Examples

#### 1. Creating a Recurring Job

```python
# Via API
POST /scheduler/jobs
{
  "title": "Daily Standup Report",
  "prompt": "Generate a standup report summarizing yesterday's progress",
  "schedule": "every day at 9am"
}

# Response
{
  "job_id": "job_abc123def456",
  "status": "created",
  "cron_expression": "0 9 * * *",
  "next_run": "2025-01-20T09:00:00-05:00"
}
```

#### 2. Creating a One-Time Job

```python
# Via API
POST /scheduler/jobs
{
  "title": "Meeting Reminder",
  "prompt": "Remind me about the project review meeting",
  "schedule": "tomorrow at 2:30pm"
}

# Response
{
  "job_id": "job_xyz789uvw012",
  "status": "created",
  "scheduled_for": "2025-01-20T14:30:00-05:00",
  "is_recurring": false
}
```

## Natural Language Schedule Examples

The scheduler understands various natural language patterns:

### Time-Based Schedules

| Natural Language | Cron Expression | Description |
|-----------------|-----------------|-------------|
| "every hour" | `0 * * * *` | Start of every hour |
| "every 30 minutes" | `*/30 * * * *` | Every 30 minutes |
| "every day at 9am" | `0 9 * * *` | Daily at 9:00 AM |
| "every day at 3:30pm" | `30 15 * * *` | Daily at 3:30 PM |
| "at midnight" | `0 0 * * *` | Daily at midnight |
| "at noon" | `0 12 * * *` | Daily at noon |

### Day-Based Schedules

| Natural Language | Cron Expression | Description |
|-----------------|-----------------|-------------|
| "every Monday" | `0 0 * * 1` | Weekly on Monday |
| "every weekday at 8am" | `0 8 * * 1-5` | Mon-Fri at 8:00 AM |
| "every weekend at 10am" | `0 10 * * 0,6` | Sat-Sun at 10:00 AM |
| "every Friday at 5pm" | `0 17 * * 5` | Weekly Friday at 5:00 PM |

### Complex Schedules with Exclusions

```python
# Create job with exclusions
POST /scheduler/jobs
{
  "title": "Business Hours Check",
  "prompt": "Check system status",
  "schedule": "every hour",
  "exclusions": [
    "except weekends",
    "except between 6pm and 8am"
  ]
}
```

## Job Management

### List All Jobs

```python
GET /scheduler/jobs

# Response
{
  "jobs": [
    {
      "id": "job_abc123",
      "title": "Daily Standup",
      "status": "ACTIVE",
      "cron_expression": "0 9 * * *",
      "last_run_at": "2025-01-19T09:00:00Z",
      "next_run_at": "2025-01-20T09:00:00Z"
    }
  ]
}
```

### Get Job Details

```python
GET /scheduler/jobs/{job_id}

# Response includes full job details and execution history
```

### Pause a Job

```python
POST /scheduler/jobs/{job_id}/pause
{
  "reason": "Vacation - back next week"
}
```

### Resume a Job

```python
POST /scheduler/jobs/{job_id}/resume
```

### Delete a Job

```python
DELETE /scheduler/jobs/{job_id}
```

## Advanced Features

### Dynamic Prompt Variables

The scheduler automatically injects context into your prompts:

```python
# Original prompt
"Generate daily report"

# Executed prompt (automatically enhanced)
"Generate daily report for Monday, January 20, 2025 at 9:00 AM EST"
```

### Exclusion Rules

#### Simple Exclusions

```json
{
  "exclusions": [
    "except weekends",
    "except holidays",
    "skip last Friday of month"
  ]
}
```

#### Complex Exclusion Patterns

```json
{
  "exclusion_rules": [
    {
      "type": "cron",
      "pattern": "0 0 * * 0,6",
      "description": "Skip weekends"
    },
    {
      "type": "complex_date",
      "pattern": "last_friday_of_month",
      "description": "Skip month-end processing day"
    }
  ]
}
```

### Job Metadata

Store additional context with jobs:

```python
POST /scheduler/jobs
{
  "title": "Customer Report",
  "prompt": "Generate report for customer",
  "schedule": "every Monday at 9am",
  "metadata": {
    "customer_id": "cust_123",
    "report_type": "weekly_summary",
    "recipients": ["alice@example.com", "bob@example.com"]
  }
}
```

## Monitoring & Debugging

### View Job Execution History

```python
GET /scheduler/jobs/{job_id}/history

# Response
{
  "executions": [
    {
      "executed_at": "2025-01-19T09:00:00Z",
      "status": "success",
      "duration_ms": 3450,
      "response_length": 1234
    },
    {
      "executed_at": "2025-01-18T09:00:00Z",
      "status": "failed",
      "error": "LLM timeout",
      "duration_ms": 30000
    }
  ]
}
```

### Check Scheduler Status

```python
GET /scheduler/status

# Response
{
  "status": "running",
  "last_check": "2025-01-19T10:45:00Z",
  "active_jobs": 15,
  "paused_jobs": 3,
  "completed_jobs": 127,
  "current_executions": 2,
  "performance": {
    "cycles_completed": 1440,
    "average_cycle_time_ms": 145,
    "cache_hit_rate": 0.73
  }
}
```

### View Audit Trail

```python
GET /scheduler/audit?job_id={job_id}

# Response shows all lifecycle events
{
  "events": [
    {
      "timestamp": "2025-01-15T10:00:00Z",
      "action": "created",
      "user_id": "user_123"
    },
    {
      "timestamp": "2025-01-17T14:30:00Z",
      "action": "paused",
      "reason": "Manual pause for maintenance"
    }
  ]
}
```

## Best Practices

### 1. Use Descriptive Titles

```python
# Good
"Daily Sales Report Generation"
"Weekly Team Standup Summary"
"Monthly Customer Satisfaction Analysis"

# Bad
"Report"
"Task 1"
"Untitled Job"
```

### 2. Provide Context in Prompts

```python
# Good prompt
"Generate a weekly sales report including:
- Total revenue by product category
- Top 10 customers by volume
- Comparison with previous week
Focus on actionable insights for the sales team."

# Less effective
"Make sales report"
```

### 3. Set Appropriate Intervals

- Use longer intervals for resource-intensive tasks
- Consider time zones for global teams
- Avoid scheduling during maintenance windows

### 4. Handle Failures Gracefully

The scheduler automatically:
- Retries failed jobs (configurable)
- Pauses jobs after consecutive failures
- Sends notifications for critical failures

### 5. Use Exclusions Wisely

```python
# Example: Business hours only
{
  "schedule": "every hour",
  "exclusions": [
    "except between 6pm and 8am",
    "except weekends",
    "except holidays"
  ]
}
```

## Performance Tips

### Optimize Check Intervals

```yaml
scheduler:
  # For minute-precision schedules
  check_interval_minutes: 1

  # For less time-sensitive jobs
  check_interval_minutes: 5
```

### Batch Processing

The scheduler automatically batches job processing:

```yaml
scheduler:
  batch_size: 50  # Process jobs in batches
  max_concurrent_jobs: 10  # Limit parallel executions
```

### Caching

Repeated schedule parsing is cached:

```yaml
scheduler:
  cache_ttl: 300  # Cache for 5 minutes
  max_cache_size: 1000  # Maximum cached items
```

## Troubleshooting

### Job Not Executing

1. Check job status: `GET /scheduler/jobs/{job_id}`
2. Verify schedule: Look at `cron_expression` or `scheduled_for`
3. Check exclusion rules: Job might be excluded
4. Review audit trail: `GET /scheduler/audit?job_id={job_id}`
5. Check scheduler status: `GET /scheduler/status`

### Job Failing Repeatedly

1. Check error messages in history
2. Verify prompt is valid
3. Check if job was auto-paused
4. Review consecutive failure count
5. Check LLM availability

### Performance Issues

1. Reduce `check_interval_minutes` if jobs are delayed
2. Increase `max_concurrent_jobs` for more parallelism
3. Enable caching if not already enabled
4. Check database query performance
5. Review batch processing settings

## Examples

### Example 1: Daily Metrics Report

```python
POST /scheduler/jobs
{
  "title": "Daily Business Metrics",
  "prompt": "Generate a comprehensive business metrics report including:
    - User engagement statistics
    - Revenue metrics
    - System performance indicators
    - Notable events or anomalies
    Format as a concise executive summary.",
  "schedule": "every weekday at 8:30am",
  "metadata": {
    "report_type": "executive_daily",
    "distribution": "c-suite"
  }
}
```

### Example 2: Hourly System Check

```python
POST /scheduler/jobs
{
  "title": "System Health Monitor",
  "prompt": "Check system health and report any issues",
  "schedule": "every hour",
  "exclusions": ["except between 2am and 4am"],  # Maintenance window
  "metadata": {
    "alert_threshold": "critical",
    "notify_on_failure": true
  }
}
```

### Example 3: Weekly Team Summary

```python
POST /scheduler/jobs
{
  "title": "Weekly Team Performance Summary",
  "prompt": "Analyze team performance for the past week including:
    - Completed tasks and milestones
    - Blockers and challenges
    - Upcoming priorities
    - Team member highlights",
  "schedule": "every Friday at 4pm",
  "metadata": {
    "team": "engineering",
    "lookback_days": 7
  }
}
```

## API Reference Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/scheduler/jobs` | GET | List all jobs |
| `/scheduler/jobs` | POST | Create new job |
| `/scheduler/jobs/{id}` | GET | Get job details |
| `/scheduler/jobs/{id}` | PUT | Update job |
| `/scheduler/jobs/{id}` | DELETE | Delete job |
| `/scheduler/jobs/{id}/pause` | POST | Pause job |
| `/scheduler/jobs/{id}/resume` | POST | Resume job |
| `/scheduler/jobs/{id}/history` | GET | Get execution history |
| `/scheduler/status` | GET | Get scheduler status |
| `/scheduler/audit` | GET | View audit trail |

## Conclusion

The MUXI Scheduler transforms your AI formation from reactive to proactive, enabling automated workflows and scheduled intelligence. With natural language scheduling, flexible exclusion rules, and comprehensive monitoring, you can build sophisticated automated systems that work around the clock.