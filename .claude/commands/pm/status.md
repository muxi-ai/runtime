---
allowed-tools: Bash, Read, LS
---

# Status

Display overall project status dashboard.

## Usage
```
/pm:status
```

## Instructions

### 1. Gather Project Metrics

Scan all directories:
- Count PRDs in `.claude/prds/` by status
- Count epics in `.claude/epics/` by status
- Count open vs closed tasks across all epics
- Check for work in progress (updates/ directories)

### 2. Display Dashboard

```
📊 Project Status

PRDs:
  Backlog: {count}
  In Progress: {count}
  Complete: {count}

Epics:
  Active: {count} ({avg_progress}% avg progress)
  Backlog: {count}
  Completed: {count}

Tasks:
  Open: {count}
  In Progress: {count}
  Closed: {count}

Current Work:
  {epic_name}: Issue #{num} - {task_name} ({progress}%)
  {epic_name}: Issue #{num} - {task_name} ({progress}%)

Near Completion:
  {epic_name}: {progress}% complete ({tasks_remaining} tasks left)

Blocked:
  {Check for tasks with blockers in progress files}

Next Priority:
  Run /pm:next for recommended next task
```

### 3. GitHub Sync Status (Optional)

If connected to GitHub:
```bash
gh issue list --label "epic" --json state | jq 'length'
gh issue list --label "task" --json state | jq 'length'
```

Show sync indicators:
- ✅ Synced (has GitHub URL in frontmatter)
- ⚠️ Local only (no GitHub URL)
- 🔄 May need sync (updated > last_sync)

## Important Notes

Follow `/rules/standard-patterns.md` for output format.
Keep metrics focused on actionable insights.