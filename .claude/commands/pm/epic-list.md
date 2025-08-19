---
allowed-tools: Read, LS
---

# Epic List

List all existing epics in the project.

## Usage
```
/pm:epic-list
```

## Preflight Checklist

1. **Verify epic directory exists:**
   - Check if `.claude/epics/` directory exists
   - If not found, tell user: "📁 No epics directory found. Create your first epic with: /pm:prd-parse <feature-name>"
   - Exit gracefully if directory doesn't exist

## Instructions

You are listing all epics in the project.

### 1. Scan Epic Directories
- Read the `.claude/epics/` directory
- Look for subdirectories containing `epic.md` files
- Parse frontmatter from each epic file to extract metadata
- Count task files in each epic directory

### 2. Display Format
For each epic found, display using frontmatter data:
```
📚 {name} ({status}) - {progress}%
   Path: .claude/epics/{epic_name}/
   Created: {created}
   Progress: {progress}% ({completed_tasks}/{total_tasks} tasks)
   PRD: {prd_path}
   GitHub: {github_url or "Not synced"}
```

### 3. Status-Based Grouping
Group epics by status:
```
🔍 Backlog Epics:
   📚 user-authentication (backlog) - 0%
   📚 payment-system (backlog) - 0%

🔄 In-Progress Epics:
   📚 notification-service (in-progress) - 60%
   📚 user-profiles (in-progress) - 25%

✅ Implemented Epics:
   📚 basic-setup (implemented) - 100%
```

### 4. Task Breakdown Details
For each epic, show task summary:
```
📚 notification-service (in-progress) - 60%
   ├── 📋 Tasks: 5 total (3 completed, 2 remaining)
   ├── 🚀 Parallel tasks available: 1
   ├── ⏸️ Blocked tasks: 0
   └── 🔗 GitHub: https://github.com/org/repo/issues/123
```

### 5. Summary Statistics
```
📊 Epic Summary
   Total epics: {count}
   Backlog: {backlog_count}
   In-progress: {in_progress_count}
   Implemented: {implemented_count}
   
📈 Progress Overview
   Average completion: {avg_progress}%
   Most active: {most_active_epic} ({progress}%)
   
☁️ GitHub Sync Status
   Synced: {synced_count}
   Local only: {local_count}
```

### 6. Suggested Actions
Based on epic statuses and progress:
- For backlog epics: suggest decomposition with `/pm:epic-decompose {name}`
- For epics without GitHub sync: suggest `/pm:epic-sync {name}`
- For in-progress epics: suggest next task with `/pm:next`
- For high-progress epics: highlight completion opportunities

### 7. Epic Health Indicators
Use visual indicators:
- 🟢 Healthy progress (tasks moving regularly)
- 🟡 Needs attention (stuck/blocked tasks)
- 🔴 Stalled (no recent activity)
- ✅ Complete (100% progress)

### 8. Error Handling

Handle these cases gracefully:
- **Empty directory:** Show "📁 No epics found. Start by creating a PRD: /pm:prd-new <feature-name>"
- **Invalid epic structure:** For directories without epic.md, show: "⚠️ {dirname} - Invalid epic structure (missing epic.md)"
- **Corrupt frontmatter:** Show epic but mark as "⚠️ Invalid frontmatter"
- **Missing task count:** If can't count tasks, show "? tasks"

### 9. Performance Considerations

For large projects:
- Don't read full file contents, only frontmatter
- Cache task counts if possible
- Show progress indicator if scanning takes time

If no epics exist, suggest creating one with `/pm:prd-new` followed by `/pm:prd-parse`.

Parse frontmatter from all epic and task files to provide accurate status and progress information.
