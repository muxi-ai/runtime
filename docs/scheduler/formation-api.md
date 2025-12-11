# Scheduler Formation API Reference

**Version**: 1.1.0
**Date**: June 2025
**Status**: ✅ Complete Implementation

## Overview

The MUXI Scheduler provides a comprehensive API through the Formation class, enabling developers to programmatically manage scheduled jobs, retrieve job information, and access audit trails. This document covers all scheduler-related methods available through the Formation API.

## Formation API Methods

### Job Retrieval Methods

All scheduler retrieval methods are available through the Formation instance after the overlord has been started.

```python
from muxi.formation import Formation

# Initialize and start formation
formation = Formation()
await formation.load("formation.afs")
overlord = await formation.start_overlord()

# Now scheduler methods are available
active_jobs = await formation.get_active_jobs()
```

### get_active_jobs()

Get all currently active scheduled jobs.

```python
async def get_active_jobs(self) -> List[Dict[str, Any]]
```

**Returns:**
- List of active scheduled jobs with their complete details

**Example:**
```python
active_jobs = await formation.get_active_jobs()
for job in active_jobs:
    print(f"Job: {job['title']} (ID: {job['id']})")
    print(f"Schedule: {job['cron_expression'] or job['scheduled_for']}")
    print(f"Last run: {job['last_run_at']}")
```

**Raises:**
- `OverlordStateError`: If overlord is not running

### get_all_jobs()

Get all scheduled jobs with optional filtering.

```python
async def get_all_jobs(
    self,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    is_recurring: Optional[bool] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None
) -> List[Dict[str, Any]]
```

**Parameters:**
- `status` (Optional[str]): Filter by job status ('active', 'paused', 'completed', 'failed')
- `user_id` (Optional[str]): Filter by user ID
- `is_recurring` (Optional[bool]): Filter by job type (True for recurring, False for one-time)
- `limit` (Optional[int]): Maximum number of jobs to return
- `offset` (Optional[int]): Number of jobs to skip for pagination

**Returns:**
- List of scheduled jobs matching the criteria

**Example:**
```python
# Get all paused jobs for a specific user
paused_jobs = await formation.get_all_jobs(
    status="paused",
    user_id="user123"
)

# Get the first 10 one-time jobs
onetime_jobs = await formation.get_all_jobs(
    is_recurring=False,
    limit=10
)

# Paginate through all jobs
page_size = 50
offset = 0
while True:
    jobs = await formation.get_all_jobs(limit=page_size, offset=offset)
    if not jobs:
        break
    # Process jobs
    offset += page_size
```

### get_user_jobs()

Get all scheduled jobs for a specific user.

```python
async def get_user_jobs(self, user_id: str) -> List[Dict[str, Any]]
```

**Parameters:**
- `user_id` (str): The user ID to get jobs for

**Returns:**
- List of all scheduled jobs for the specified user

**Example:**
```python
user_jobs = await formation.get_user_jobs("user123")
print(f"User has {len(user_jobs)} scheduled jobs")

# Group by status
by_status = {}
for job in user_jobs:
    status = job['status']
    if status not in by_status:
        by_status[status] = []
    by_status[status].append(job)

print(f"Active: {len(by_status.get('ACTIVE', []))}")
print(f"Paused: {len(by_status.get('PAUSED', []))}")
print(f"Completed: {len(by_status.get('COMPLETED', []))}")
```

### get_job_audit_trail()

Get the audit trail for a specific job.

```python
async def get_job_audit_trail(self, job_id: str) -> List[Dict[str, Any]]
```

**Parameters:**
- `job_id` (str): The job ID to get audit trail for

**Returns:**
- List of audit events for the job, ordered by timestamp (newest first)

**Example:**
```python
audit_trail = await formation.get_job_audit_trail("sched_abc123")

for event in audit_trail:
    print(f"{event['timestamp']}: {event['action']}")
    if event['changes']:
        print(f"  Changes: {event['changes']}")
    if event['reason']:
        print(f"  Reason: {event['reason']}")
```

**Audit Event Structure:**
```python
{
    "id": 123,
    "job_id": "sched_abc123",
    "user_id": "user123",
    "action": "paused",  # created, updated, paused, resumed, deleted, replaced
    "timestamp": "2025-06-23T10:30:00Z",
    "changes": {"status": "PAUSED"},  # JSON of what changed
    "reason": "User requested pause"   # Optional reason
}
```

### get_recent_audit_trail()

Get recent audit trail events with optional filtering.

```python
async def get_recent_audit_trail(
    self,
    limit: int = 100,
    user_id: Optional[str] = None,
    action: Optional[str] = None
) -> List[Dict[str, Any]]
```

**Parameters:**
- `limit` (int): Maximum number of events to return (default: 100)
- `user_id` (Optional[str]): Filter by user ID
- `action` (Optional[str]): Filter by action type ('created', 'updated', 'paused', 'resumed', 'deleted', 'replaced')

**Returns:**
- List of recent audit events, ordered by timestamp (newest first)

**Example:**
```python
# Get last 50 audit events
recent_events = await formation.get_recent_audit_trail(limit=50)

# Get all pause events for a user
pause_events = await formation.get_recent_audit_trail(
    user_id="user123",
    action="paused"
)

# Monitor recent job creations
create_events = await formation.get_recent_audit_trail(
    action="created",
    limit=20
)
for event in create_events:
    print(f"New job created: {event['job_id']} by {event['user_id']}")
```

## Job Data Structure

All job retrieval methods return job dictionaries with the following structure:

```python
{
    # Identification
    "id": "sched_abc123def456",
    "user_id": "user123",
    "formation_id": "formation456",

    # Job details
    "title": "Daily Email Check",
    "original_prompt": "Check my email every day at 9am",
    "execution_prompt": "Check user's email and summarize important messages",

    # Scheduling
    "is_recurring": True,
    "cron_expression": "0 9 * * *",  # For recurring jobs
    "scheduled_for": None,           # For one-time jobs
    "exclusion_rules": [],

    # Status
    "status": "ACTIVE",  # ACTIVE, PAUSED, COMPLETED

    # Execution tracking
    "last_run_at": "2025-06-23T09:00:00Z",
    "last_run_status": "success",
    "last_run_failure_message": None,
    "total_runs": 15,
    "total_failures": 0,
    "consecutive_failures": 0,

    # Timestamps
    "created_at": "2025-06-01T10:30:00Z",
    "updated_at": "2025-06-23T09:00:15Z",

    # Metadata
    "metadata": {}
}
```

## Common Use Cases

### Monitor Job Health

```python
async def check_job_health(formation: Formation, user_id: str):
    """Check health of user's scheduled jobs."""
    jobs = await formation.get_user_jobs(user_id)

    unhealthy_jobs = []
    for job in jobs:
        # Check for jobs with high failure rates
        if job['total_runs'] > 0:
            failure_rate = job['total_failures'] / job['total_runs']
            if failure_rate > 0.2:  # More than 20% failures
                unhealthy_jobs.append(job)

        # Check for jobs that haven't run recently
        if job['status'] == 'ACTIVE' and job['last_run_at']:
            last_run = datetime.fromisoformat(job['last_run_at'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) - last_run > timedelta(days=7):
                unhealthy_jobs.append(job)

    return unhealthy_jobs
```

### Generate Job Report

```python
async def generate_job_report(formation: Formation, user_id: str):
    """Generate a summary report of user's scheduled jobs."""
    jobs = await formation.get_user_jobs(user_id)
    audit_events = await formation.get_recent_audit_trail(
        user_id=user_id,
        limit=100
    )

    report = {
        "total_jobs": len(jobs),
        "active_jobs": len([j for j in jobs if j['status'] == 'ACTIVE']),
        "paused_jobs": len([j for j in jobs if j['status'] == 'PAUSED']),
        "completed_jobs": len([j for j in jobs if j['status'] == 'COMPLETED']),
        "recurring_jobs": len([j for j in jobs if j['is_recurring']]),
        "onetime_jobs": len([j for j in jobs if not j['is_recurring']]),
        "recent_activity": {
            "created": len([e for e in audit_events if e['action'] == 'created']),
            "paused": len([e for e in audit_events if e['action'] == 'paused']),
            "resumed": len([e for e in audit_events if e['action'] == 'resumed']),
            "deleted": len([e for e in audit_events if e['action'] == 'deleted']),
        }
    }

    return report
```

### Audit Trail Analysis

```python
async def analyze_job_changes(formation: Formation, job_id: str):
    """Analyze the change history of a job."""
    audit_trail = await formation.get_job_audit_trail(job_id)

    # Find creation event
    creation_event = next(
        (e for e in audit_trail if e['action'] == 'created'),
        None
    )

    # Count status changes
    status_changes = [
        e for e in audit_trail
        if e['action'] in ['paused', 'resumed']
    ]

    # Check if job was replaced
    replacement = next(
        (e for e in audit_trail if e['action'] == 'replaced'),
        None
    )

    analysis = {
        "created_at": creation_event['timestamp'] if creation_event else None,
        "created_by": creation_event['user_id'] if creation_event else None,
        "status_change_count": len(status_changes),
        "was_replaced": replacement is not None,
        "replaced_by": replacement['changes']['replaced_by'] if replacement else None,
        "total_events": len(audit_trail)
    }

    return analysis
```

## Error Handling

All Formation scheduler methods can raise the following exceptions:

### OverlordStateError

Raised when trying to access scheduler methods before the overlord is started.

```python
from muxi.datatypes.exceptions import OverlordStateError

try:
    jobs = await formation.get_active_jobs()
except OverlordStateError as e:
    print(f"Overlord not running: {e}")
    # Start the overlord first
    overlord = await formation.start_overlord()
    jobs = await formation.get_active_jobs()
```

### Database Errors

Database operations may raise SQLAlchemy exceptions.

```python
from sqlalchemy.exc import SQLAlchemyError

try:
    audit_trail = await formation.get_job_audit_trail("invalid_id")
except SQLAlchemyError as e:
    print(f"Database error: {e}")
```

## Performance Considerations

### Efficient Pagination

When dealing with many jobs, use pagination to avoid loading all data at once:

```python
async def process_all_jobs(formation: Formation):
    """Process jobs in batches."""
    batch_size = 100
    offset = 0

    while True:
        batch = await formation.get_all_jobs(
            limit=batch_size,
            offset=offset
        )

        if not batch:
            break

        # Process batch
        for job in batch:
            await process_job(job)

        offset += batch_size
```

### Caching Considerations

The Formation API methods query the database directly and do not cache results. For frequently accessed data:

```python
from functools import lru_cache
from datetime import datetime, timedelta

class CachedSchedulerAPI:
    def __init__(self, formation: Formation, cache_ttl: int = 60):
        self.formation = formation
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._cache_times = {}

    async def get_user_jobs_cached(self, user_id: str):
        """Get user jobs with caching."""
        cache_key = f"user_jobs_{user_id}"

        # Check cache
        if cache_key in self._cache:
            if datetime.now() - self._cache_times[cache_key] < timedelta(seconds=self.cache_ttl):
                return self._cache[cache_key]

        # Fetch fresh data
        jobs = await self.formation.get_user_jobs(user_id)
        self._cache[cache_key] = jobs
        self._cache_times[cache_key] = datetime.now()

        return jobs
```

## Integration with Scheduler Service

While the Formation API provides read access to scheduler data, job management operations should still go through the scheduler service or natural language interface:

```python
# Read operations - use Formation API
active_jobs = await formation.get_active_jobs()
audit_trail = await formation.get_job_audit_trail(job_id)

# Write operations - use scheduler service or chat
# Create a job via natural language
response = await overlord.chat(
    "Schedule daily email check at 9am",
    user_id="user123"
)

# Or use scheduler service directly
scheduler = await overlord.get_scheduler_service()
job_id = await scheduler.manager.create_job(...)
```

## Best Practices

1. **Always check overlord state** before calling scheduler methods
2. **Use pagination** for large result sets
3. **Handle exceptions** gracefully, especially database errors
4. **Monitor job health** regularly using audit trails
5. **Cache results** appropriately for read-heavy operations
6. **Use specific filters** to reduce database load

## Summary

The Formation API provides comprehensive read access to scheduler data:

- **Job Retrieval**: Get active, all, or user-specific jobs
- **Audit Trails**: Track job lifecycle events and changes
- **Filtering**: Query jobs by status, type, and user
- **Pagination**: Handle large datasets efficiently

These methods enable developers to build powerful monitoring, reporting, and management tools on top of the MUXI Scheduler.
