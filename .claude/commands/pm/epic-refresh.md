---
allowed-tools: Read, Write, LS
---

# Epic Refresh

Update epic progress based on task states.

## Usage
```
/pm:epic-refresh <epic_name>
```

## Instructions

### 1. Count Task Status

Scan all task files in `.claude/epics/$ARGUMENTS/`:
- Count total tasks
- Count tasks with `status: closed`
- Count tasks with `status: open`
- Count tasks with work in progress

### 2. Calculate Progress

```
progress = (closed_tasks / total_tasks) * 100
```

Round to nearest integer.

### 3. Determine Epic Status

- If progress = 0% and no work started: `backlog`
- If progress > 0% and < 100%: `in-progress`
- If progress = 100%: `completed`

### 4. Update Epic

Get current datetime: `date -u +"%Y-%m-%dT%H:%M:%SZ"`

Update epic.md frontmatter:
```yaml
status: {calculated_status}
progress: {calculated_progress}%
updated: {current_datetime}
```

### 5. Output

```
🔄 Epic refreshed: $ARGUMENTS

Tasks:
  Closed: {closed_count}
  Open: {open_count}
  Total: {total_count}
  
Progress: {old_progress}% → {new_progress}%
Status: {old_status} → {new_status}

{If complete}: Run /pm:epic-close $ARGUMENTS to close epic
{If in progress}: Run /pm:next to see priority tasks
```

## Important Notes

This is useful after manual task edits or GitHub sync.
Don't modify task files, only epic status.
Preserve all other frontmatter fields.