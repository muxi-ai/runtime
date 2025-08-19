---
allowed-tools: Read, LS
---

# In Progress

List all work currently in progress.

## Usage
```
/pm:in-progress
```

## Instructions

### 1. Find Active Work

Scan for in-progress items:
- Epic directories with updates/ subdirectories
- Progress files with completion > 0% and < 100%
- Task files with status: "in-progress" in frontmatter
- Issues with started date in last 30 days

### 2. Calculate Time Metrics

For each in-progress item:
- Days since started (from progress.md frontmatter)
- Last activity (from updated field or file modification time)
- Current completion percentage

### 3. Display Active Work

```
🔄 Work In Progress

{epic_name}:
  Issue #{number}: {task_name}
  Progress: {completion}%
  Started: {days} days ago
  Last update: {date}
  Status: {Active|Stale if >3 days no update}

{epic_name}:
  Issue #{number}: {task_name}
  Progress: {completion}%
  Started: {days} days ago
  Last update: {date}
  Status: {Active|Stale}

Summary:
  Active tasks: {count}
  Stale tasks: {count} (no update >3 days)
  Average progress: {avg}%
  
Recommendations:
  {If stale tasks exist}: Consider updating or closing stale tasks
  {If too many in progress}: Focus on completing before starting new work
  {If average progress low}: Check for blockers with /pm:blocked
```

### 4. No Active Work

If nothing in progress:
```
📭 No work in progress

Run /pm:next to see recommended tasks to start.
```

## Important Notes

Mark work as stale if no updates in 3+ days.
Don't include completed work (100% or status: closed).
Order by last update time (most recent first).