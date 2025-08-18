# Next

Show the next issue to work on with its relation to the epic.

## Usage
```
/pm:next
```

## Instructions

You are identifying the next priority issue to work on and showing its context within the epic structure.

### 1. Scan All Local Epics
- Read the `.claude/epics/` directory
- Find all epic directories with `epic.md` files
- Parse epic frontmatter for status and progress
- Look for associated task files and their statuses

### 2. Analyze Task Status from Frontmatter
For each epic, examine task frontmatter to determine:
- Tasks with `status: open` (available to start)
- Tasks with `status: closed` (completed)
- Tasks currently assigned or in progress
- Dependencies between tasks

### 3. Check GitHub Issue Status
For tasks with GitHub URLs in frontmatter:
- Use `gh issue list --label "epic:{epic_name}" --state open` to get current status
- Cross-reference with local frontmatter
- Identify any sync discrepancies

### 4. Priority Logic Using Frontmatter
Find the next issue using this priority based on frontmatter analysis:
1. **Blocking sequential tasks** - Open tasks that unlock others
2. **Ready parallel tasks** - Tasks marked `parallel: true` with no dependencies  
3. **Next sequential task** - Follow logical order in epics
4. **Consider epic progress** - Prioritize epics with higher completion rates

### 5. Display Next Issue with Context
Show the recommended next issue using frontmatter data:
```
🎯 Next Recommended Issue

📋 Issue #{github_issue}: {task_name}
   Epic: {epic_name} ({epic_status}) - {epic_progress}%
   Task Status: {task_status}
   Created: {task_created}
   Updated: {task_updated}
   
📚 Epic Context:
   Progress: {completed_tasks}/{total_tasks} tasks complete ({epic_progress}%)
   This task: #{position} in sequence
   PRD: {prd_path}
   
🔗 Dependencies:
   ✅ {completed_dependency}
   ⏸️ {pending_dependency}
   
📊 Task Details:
   File: .claude/epics/{epic_name}/{task_file}
   Parallel execution: {parallel_flag}
   GitHub: {github_url}
   
🚀 Quick Start:
   /pm:issue-start {github_issue}
```

### 6. Alternative Options from Frontmatter
If multiple good options exist, show alternatives using frontmatter:
```
🔄 Other Available Tasks:
   Issue #{alt1}: {name} ({epic_name}, parallel, {estimate})
   Issue #{alt2}: {name} ({epic_name}, sequential, {estimate})
   Issue #{alt3}: {name} ({epic_name}, parallel, {estimate})
```

### 7. Epic Health Check from Frontmatter
Show overall project status using frontmatter analysis:
```
📊 Epic Status Overview:
   Active epics: {active_count}
   
🔍 Backlog Epics: {backlog_count}
   {epic1_name} (0% complete)
   {epic2_name} (0% complete)
   
🔄 In-Progress Epics: {in_progress_count}
   {epic3_name} ({progress}% complete)
   {epic4_name} ({progress}% complete)
   
✅ Completed Epics: {completed_count}
   
🏃‍♂️ Velocity Analysis:
   Average epic progress: {avg_progress}%
   Ready tasks across all epics: {ready_count}
   Blocked tasks: {blocked_count}
```

### 8. No Work Available
If no issues are ready based on frontmatter analysis:
```
⏸️ No Ready Issues Found

Possible reasons:
- All current tasks have status: closed
- Tasks waiting for dependencies
- No epics with open tasks

🚀 Suggested Actions:
- Check /pm:epic-list for epics needing decomposition
- Review blocked tasks for dependency resolution
- Create new epic with /pm:prd-new {feature}
- Sync status with GitHub: /pm:epic-sync {epic_name}
```

### 9. Smart Recommendations from Metadata
Consider these factors from frontmatter:
- **Epic progress** - Prioritize epics closer to completion
- **Task creation dates** - Consider age and priority
- **GitHub sync status** - Prefer synced tasks for transparency
- **Parallel vs sequential** - Balance workload distribution

### 10. Status Synchronization Check
Compare frontmatter with GitHub and suggest sync if needed:
```
⚠️ Sync Recommendations:
   Epic {epic_name}: Local progress differs from GitHub
   → Run: /pm:issue-sync {issue_number}
   
   Epic {epic_name}: Not synced to GitHub
   → Run: /pm:epic-sync {epic_name}
```

Provide a clear, actionable recommendation that helps developers maintain momentum and make progress on the most important work, using frontmatter as the authoritative source for all status and progress information.
