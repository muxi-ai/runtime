---
allowed-tools: Bash, Read, LS
---

# Standup

Generate daily standup report.

## Usage
```
/pm:standup
```

## Instructions

### 1. Gather Yesterday's Activity

Check for recent updates:
- Look for progress files modified in last 24 hours
- Check git commits from yesterday: `git log --since="1 day ago" --oneline`
- Read recent entries from progress.md files in updates/ directories

### 2. Identify Today's Work

- Find tasks currently marked as in-progress
- Check `/pm:next` priority
- Look for tasks near completion

### 3. Find Blockers

Scan progress files for:
- Keywords like "blocked", "waiting", "dependency"
- Tasks with 0% progress after being started
- Issues mentioned in notes.md files

### 4. Generate Report

```
📅 Daily Standup - {current_date}

Yesterday:
  ✅ {task_name} - {what_was_accomplished}
  ✅ {task_name} - {progress_made}
  📝 {commits_made}

Today:
  🎯 {task_name} - {planned_work}
  🎯 {task_name} - {planned_work}
  
In Progress:
  • {epic}/{task} - {progress}%
  • {epic}/{task} - {progress}%

Blockers:
  ⚠️ {task} - {blocker_description}
  ⚠️ {None if no blockers}

Next Priority:
  {Output from /pm:next logic}
```

### 5. Optional GitHub Activity

```bash
# Issues updated yesterday
gh issue list --assignee @me --updated ">1 day ago" --json number,title
```

## Important Notes

Keep report concise and actionable.
Focus on actual progress, not just activity.
Reference `/rules/datetime.md` for date handling.