# Scheduler Audit Trail Guide

**Version**: 1.0.0
**Date**: June 2025
**Status**: ✅ Complete Implementation

## Overview

The MUXI Scheduler maintains a comprehensive audit trail of all job lifecycle events, providing complete visibility into job creation, modifications, status changes, and deletions. This guide covers how to use the audit trail for monitoring, troubleshooting, and compliance.

## What is Tracked

The audit trail records the following job lifecycle events:

| Action | Description | Tracked Information |
|--------|-------------|-------------------|
| `created` | Job was created | Title, prompt, schedule, job type |
| `updated` | Job was modified | Changed fields and new values |
| `paused` | Job was paused | User who paused, reason if provided |
| `resumed` | Job was resumed | User who resumed |
| `deleted` | Job was deleted | User who deleted, reason if provided |
| `replaced` | Job was replaced due to significant change | New job ID, reason for replacement |

> **Note**: Job executions are NOT tracked in the audit trail. Execution history is handled by the observability system.

## Audit Entry Structure

Each audit entry contains:

```python
{
    "id": 123,                          # Unique audit entry ID
    "job_id": "sched_abc123",          # Job being audited
    "user_id": "user123",              # User who performed action
    "action": "paused",                # Action type
    "timestamp": "2025-06-23T10:30:00Z",  # When it happened
    "changes": {                       # What changed (JSON)
        "status": "PAUSED",
        "previous_status": "ACTIVE"
    },
    "reason": "Maintenance window"     # Optional reason
}
```

## Using the Audit Trail API

### Get Job-Specific Audit Trail

```python
from muxi.runtime.formation import Formation

# Initialize formation
formation = Formation()
await formation.load("formation.afs")
overlord = await formation.start_overlord()

# Get audit trail for a specific job
job_id = "sched_abc123"
audit_trail = await formation.get_job_audit_trail(job_id)

# Display audit history
print(f"Audit Trail for Job {job_id}:")
print("-" * 50)

for event in audit_trail:
    print(f"{event['timestamp']}: {event['action'].upper()}")
    print(f"  User: {event['user_id']}")

    if event['changes']:
        changes = json.loads(event['changes'])
        print(f"  Changes: {changes}")

    if event['reason']:
        print(f"  Reason: {event['reason']}")

    print()
```

### Get User-Specific Audit Trail

```python
# Get all audit events for a specific user
user_id = "user123"
audit_trail = await formation.get_recent_audit_trail(
    user_id=user_id,
    limit=50
)

# Group events by action
events_by_action = {}
for event in audit_trail:
    action = event['action']
    if action not in events_by_action:
        events_by_action[action] = []
    events_by_action[action].append(event)

# Display summary
print(f"Audit Summary for User {user_id}:")
for action, events in events_by_action.items():
    print(f"  {action}: {len(events)} events")
```

### Get Recent System-Wide Events

```python
# Get recent events across all users
recent_events = await formation.get_recent_audit_trail(limit=100)

# Filter for specific actions
create_events = await formation.get_recent_audit_trail(
    action="created",
    limit=20
)

delete_events = await formation.get_recent_audit_trail(
    action="deleted",
    limit=20
)

# Monitor for issues
pause_events = await formation.get_recent_audit_trail(
    action="paused",
    limit=50
)

print(f"Recent Activity:")
print(f"  Jobs created: {len(create_events)}")
print(f"  Jobs deleted: {len(delete_events)}")
print(f"  Jobs paused: {len(pause_events)}")
```

## Practical Examples

### Example 1: Track Job Lifecycle

```python
async def track_job_lifecycle(formation: Formation, job_id: str):
    """Track the complete lifecycle of a job."""
    audit_trail = await formation.get_job_audit_trail(job_id)

    # Find key events
    creation = next((e for e in audit_trail if e['action'] == 'created'), None)
    pauses = [e for e in audit_trail if e['action'] == 'paused']
    resumes = [e for e in audit_trail if e['action'] == 'resumed']
    deletion = next((e for e in audit_trail if e['action'] == 'deleted'), None)
    replacement = next((e for e in audit_trail if e['action'] == 'replaced'), None)

    print(f"Job Lifecycle Report for {job_id}")
    print("=" * 50)

    if creation:
        print(f"Created: {creation['timestamp']} by {creation['user_id']}")
        if creation['changes']:
            changes = json.loads(creation['changes'])
            print(f"  Title: {changes.get('title')}")
            print(f"  Type: {changes.get('type')}")

    print(f"\nStatus Changes:")
    print(f"  Paused {len(pauses)} times")
    print(f"  Resumed {len(resumes)} times")

    if replacement:
        changes = json.loads(replacement['changes'])
        print(f"\nReplaced: {replacement['timestamp']}")
        print(f"  New Job ID: {changes['replaced_by']}")
        print(f"  Reason: {replacement['reason']}")

    if deletion:
        print(f"\nDeleted: {deletion['timestamp']} by {deletion['user_id']}")
        if deletion['reason']:
            print(f"  Reason: {deletion['reason']}")

    return {
        "created": creation is not None,
        "deleted": deletion is not None,
        "replaced": replacement is not None,
        "pause_count": len(pauses),
        "resume_count": len(resumes)
    }
```

### Example 2: Detect Suspicious Activity

```python
async def detect_suspicious_activity(formation: Formation, time_window_hours: int = 24):
    """Detect potentially suspicious scheduler activity."""
    from datetime import datetime, timedelta, timezone

    # Get recent events
    recent_events = await formation.get_recent_audit_trail(limit=1000)

    # Filter to time window
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
    window_events = [
        e for e in recent_events
        if datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00')) > cutoff_time
    ]

    # Analyze patterns
    suspicious_patterns = []

    # 1. Mass deletions by single user
    deletions_by_user = {}
    for event in window_events:
        if event['action'] == 'deleted':
            user = event['user_id']
            deletions_by_user[user] = deletions_by_user.get(user, 0) + 1

    for user, count in deletions_by_user.items():
        if count > 5:  # Threshold
            suspicious_patterns.append({
                "type": "mass_deletion",
                "user": user,
                "count": count,
                "severity": "high"
            })

    # 2. Rapid job creation
    creations_by_user = {}
    for event in window_events:
        if event['action'] == 'created':
            user = event['user_id']
            creations_by_user[user] = creations_by_user.get(user, 0) + 1

    for user, count in creations_by_user.items():
        if count > 20:  # Threshold
            suspicious_patterns.append({
                "type": "rapid_creation",
                "user": user,
                "count": count,
                "severity": "medium"
            })

    # 3. Frequent pause/resume cycles
    job_status_changes = {}
    for event in window_events:
        if event['action'] in ['paused', 'resumed']:
            job_id = event['job_id']
            if job_id not in job_status_changes:
                job_status_changes[job_id] = []
            job_status_changes[job_id].append(event)

    for job_id, changes in job_status_changes.items():
        if len(changes) > 10:  # Threshold
            suspicious_patterns.append({
                "type": "excessive_status_changes",
                "job_id": job_id,
                "count": len(changes),
                "severity": "low"
            })

    return suspicious_patterns
```

### Example 3: Generate Compliance Report

```python
async def generate_compliance_report(formation: Formation, start_date: str, end_date: str):
    """Generate a compliance report for audit purposes."""
    from datetime import datetime

    # Get all events in date range
    all_events = await formation.get_recent_audit_trail(limit=10000)

    # Filter by date range
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    filtered_events = []
    for event in all_events:
        event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        if start <= event_time <= end:
            filtered_events.append(event)

    # Generate report
    report = {
        "period": {
            "start": start_date,
            "end": end_date
        },
        "summary": {
            "total_events": len(filtered_events),
            "unique_users": len(set(e['user_id'] for e in filtered_events)),
            "unique_jobs": len(set(e['job_id'] for e in filtered_events))
        },
        "events_by_action": {},
        "events_by_user": {},
        "deletions_with_reasons": []
    }

    # Count events by action
    for event in filtered_events:
        action = event['action']
        report['events_by_action'][action] = report['events_by_action'].get(action, 0) + 1

    # Count events by user
    for event in filtered_events:
        user = event['user_id']
        if user not in report['events_by_user']:
            report['events_by_user'][user] = {
                'total': 0,
                'by_action': {}
            }
        report['events_by_user'][user]['total'] += 1
        action = event['action']
        report['events_by_user'][user]['by_action'][action] = \
            report['events_by_user'][user]['by_action'].get(action, 0) + 1

    # Track deletions with reasons
    for event in filtered_events:
        if event['action'] == 'deleted':
            report['deletions_with_reasons'].append({
                'job_id': event['job_id'],
                'user_id': event['user_id'],
                'timestamp': event['timestamp'],
                'reason': event['reason'] or 'No reason provided'
            })

    return report
```

## Monitoring Best Practices

### 1. Regular Health Checks

```python
async def scheduler_health_check(formation: Formation):
    """Perform regular health check on scheduler jobs."""
    # Get recent pause events
    recent_pauses = await formation.get_recent_audit_trail(
        action="paused",
        limit=50
    )

    # Check for jobs paused without reason
    no_reason_pauses = [e for e in recent_pauses if not e['reason']]
    if no_reason_pauses:
        print(f"⚠️ Warning: {len(no_reason_pauses)} jobs paused without reason")

    # Check for rapid replacements (might indicate issues)
    recent_replacements = await formation.get_recent_audit_trail(
        action="replaced",
        limit=20
    )

    if len(recent_replacements) > 5:
        print(f"⚠️ Warning: High replacement rate ({len(recent_replacements)} in recent history)")

    return {
        "pauses_without_reason": len(no_reason_pauses),
        "recent_replacements": len(recent_replacements)
    }
```

### 2. User Activity Monitoring

```python
async def monitor_user_activity(formation: Formation, user_id: str, days: int = 7):
    """Monitor a user's scheduler activity."""
    from datetime import datetime, timedelta, timezone

    # Get user's recent events
    user_events = await formation.get_recent_audit_trail(
        user_id=user_id,
        limit=500
    )

    # Filter to time window
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent_events = [
        e for e in user_events
        if datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00')) > cutoff
    ]

    # Analyze activity
    activity_summary = {
        "user_id": user_id,
        "period_days": days,
        "total_actions": len(recent_events),
        "actions_by_type": {},
        "affected_jobs": set()
    }

    for event in recent_events:
        action = event['action']
        activity_summary['actions_by_type'][action] = \
            activity_summary['actions_by_type'].get(action, 0) + 1
        activity_summary['affected_jobs'].add(event['job_id'])

    activity_summary['unique_jobs_affected'] = len(activity_summary['affected_jobs'])
    activity_summary['affected_jobs'] = list(activity_summary['affected_jobs'])

    return activity_summary
```

## Database Queries

For advanced use cases, you can query the audit table directly:

```sql
-- Get audit trail for a specific job
SELECT * FROM scheduled_job_audit
WHERE job_id = 'sched_abc123'
ORDER BY timestamp DESC;

-- Find all deletions in the last 24 hours
SELECT * FROM scheduled_job_audit
WHERE action = 'deleted'
AND timestamp > NOW() - INTERVAL '24 hours';

-- Count actions by user
SELECT user_id, action, COUNT(*) as count
FROM scheduled_job_audit
GROUP BY user_id, action
ORDER BY count DESC;

-- Find jobs that were replaced
SELECT job_id, user_id, timestamp, changes->>'replaced_by' as new_job_id, reason
FROM scheduled_job_audit
WHERE action = 'replaced'
ORDER BY timestamp DESC;
```

## Retention and Cleanup

The audit trail is retained indefinitely by default. To implement retention policies:

```python
async def cleanup_old_audit_trails(db_manager, retention_days: int = 90):
    """Clean up audit trails older than retention period."""
    from datetime import datetime, timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    try:
        with db_manager.get_session() as session:
            deleted = session.query(ScheduledJobAudit).filter(
                ScheduledJobAudit.timestamp < cutoff_date
            ).delete()

            # Commit only if no errors occurred
            session.commit()

        print(f"Successfully cleaned up {deleted} audit entries older than {retention_days} days")
        return deleted

    except Exception as e:
        # Log error and ensure transaction is rolled back
        print(f"Error during audit trail cleanup: {str(e)}", flush=True)
        # Note: session.rollback() is automatically called when exiting the context manager
        # on exception, but explicit rollback can be added if needed
        raise  # Re-raise to allow caller to handle the error
```

## Security Considerations

1. **Access Control**: Audit trails contain sensitive information about user actions
2. **Data Privacy**: Consider user privacy when exposing audit data
3. **Immutability**: Audit trails should never be modified after creation
4. **Retention**: Balance compliance needs with data minimization principles

## Summary

The scheduler audit trail provides:

- Complete visibility into job lifecycle events
- User activity tracking for security monitoring
- Compliance reporting capabilities
- Troubleshooting information for debugging issues
- Historical data for analysis and optimization

Use the Formation API methods to access audit data programmatically and build custom monitoring and reporting solutions.
