---
allowed-tools: Bash, Read, LS
---

# Epic Show

Display epic and its tasks with current status.

## Usage
```
/pm:epic-show <feature_name>
```

## Instructions

You are displaying comprehensive information about an epic and its tasks for: **$ARGUMENTS**

### 1. Load Epic Data
- Read epic from `.claude/epics/$ARGUMENTS/epic.md`
- Parse epic frontmatter for metadata
- Scan for all task files in the same directory
- Parse frontmatter from each task file
- Check for GitHub mapping if it exists

### 2. Epic Overview
Display epic header using frontmatter data:

```
📚 Epic: $ARGUMENTS ({status}) - {progress}%
   Created: {created}
   PRD: {prd_path}
   GitHub: {github_url or "Not synced"}
   
📝 Description:
{epic_overview_section}
```

### 3. Task Breakdown by Status
List all tasks grouped by their frontmatter status:
```
🎯 Tasks ({task_count} total) - {progress}% complete

✅ Completed Tasks ({completed_count}):
  ✅ 001.md - {Task 1 Title} (#{github_issue})
  ✅ 003.md - {Task 3 Title} (#{github_issue})

🔄 In Progress Tasks ({in_progress_count}):
  🔄 002.md - {Task 2 Title} (#{github_issue})

📋 Open Tasks ({open_count}):
  □ 004.md - {Task 4 Title} (#{github_issue}) [parallel]
  □ 005.md - {Task 5 Title} (#{github_issue}) [sequential]
```

### 4. Progress Calculation
Calculate progress from task frontmatter:
- Count tasks with `status: closed` as completed
- Count tasks with `status: open` as pending
- Calculate percentage: (completed / total) * 100
- Update epic frontmatter if progress has changed

### 5. Task Details with Frontmatter
For each task, show metadata from frontmatter:
```
📋 001.md - Setup Database Schema
   Status: closed
   Created: 2024-01-15T10:30:00Z
   Updated: 2024-01-16T14:20:00Z
   GitHub: https://github.com/org/repo/issues/125
   Parallel: false
```

### 6. Dependencies Analysis
Analyze task dependencies and show blocking relationships:
```
🔗 Dependencies & Blockers:
   Ready to start: 2 tasks
   Blocked by dependencies: 1 task
   Critical path: 3 tasks
```

### 7. Next Actions
Based on frontmatter analysis:
```
🚀 Next Recommended Actions:
   Start task: /pm:issue-start {next_ready_issue}
   Sync progress: /pm:issue-sync {in_progress_issue}
   Review completion: Check task #{completed_issue}
```

### 8. Progress Synchronization
If epic progress calculated from tasks differs from frontmatter:
- Update epic frontmatter with correct progress
- Note the synchronization in output
- Suggest syncing changes to GitHub if needed

### 9. GitHub Sync Status
Compare local frontmatter with GitHub status:
```
☁️ Sync Status:
   Epic synced: ✅ (Issue #{epic_number})
   Tasks synced: {synced_count}/{total_count}
   Last sync: {last_sync_date or "Never"}
```

### 10. Summary Dashboard
```
📊 Epic Health Dashboard
   Overall progress: {progress}%
   Tasks completed: {completed}/{total}
   Average task duration: {avg_duration}
   Estimated completion: {estimated_date}
   
🎯 Velocity Tracking
   Recent completions: {recent_count}
   Completion rate: {tasks_per_week} tasks/week
   Time to completion: {estimated_weeks} weeks
```

Provide a comprehensive view that helps developers understand the current state and next actions for the "$ARGUMENTS" epic, using frontmatter as the source of truth for all status and progress information.
