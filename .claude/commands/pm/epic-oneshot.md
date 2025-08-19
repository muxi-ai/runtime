---
allowed-tools: Bash, Read, Write, LS
---

# Epic Oneshot

Decompose epic into tasks and sync to GitHub in one operation.

## Usage
```
/pm:epic-oneshot <feature_name>
```

## Preflight Checklist

Before proceeding, complete ALL validation steps:

1. **Epic Validation:**
   - Check if `.claude/epics/$ARGUMENTS/epic.md` exists
   - If not found, tell user: "❌ Epic not found. First run: /pm:prd-parse $ARGUMENTS"
   - Verify epic frontmatter is valid

2. **Check for Existing Work:**
   - Check if tasks already exist in `.claude/epics/$ARGUMENTS/`
   - Check if epic frontmatter has a GitHub URL (already synced)
   - If either exists, warn: "⚠️ This epic already has tasks/GitHub issues. Running oneshot will create duplicates."
   - Ask: "Continue anyway? (yes/no)"

3. **GitHub Prerequisites:**
   - Run: `gh auth status`
   - Run: `gh repo view --json name`
   - Check rate limit: `gh api rate_limit`
   - If any fail, provide specific fix instructions

## Instructions

You are performing a complete epic decomposition and GitHub sync in a single operation for: **$ARGUMENTS**

### 1. Atomic Operation Warning
Inform user: "🔄 Starting atomic operation: decompose + sync. This will create multiple GitHub issues."

### 2. Execute Decomposition
First, run the epic decomposition process:
- Read and analyze the epic for "$ARGUMENTS"
- Create all task files with proper structure
- Follow the same process as `/pm:epic-decompose $ARGUMENTS`

### 3. Execute Sync
Then, immediately sync to GitHub:
- Create epic issue on GitHub
- Create all task issues on GitHub
- Follow the same process as `/pm:epic-sync $ARGUMENTS`

### 4. Validation
After completion:
- Verify all issues were created successfully
- Check that labels are applied correctly
- Confirm task-epic relationships are established

### 5. Output Summary
Provide comprehensive summary:
```
🚀 Epic Oneshot Complete: $ARGUMENTS

📝 Decomposition Results:
   Tasks created: {task_count}
   Parallel tasks: {parallel_count}
   Sequential tasks: {sequential_count}

☁️ GitHub Sync Results:
   Epic Issue: #{epic_number}
   Task Issues: #{task1}, #{task2}, #{task3}...
   
🏷️ Labels Applied:
   epic:$ARGUMENTS
   
✅ Ready for development!
   Use /pm:issue-start #{task_number} to begin work
```

### 6. Error Recovery

**Failure Points and Recovery:**

1. **Decomposition Failed:**
   - If decomposition fails, stop immediately
   - No GitHub issues should be created
   - Tell user: "Fix the issue and retry: /pm:epic-oneshot $ARGUMENTS"

2. **Sync Failed After Decomposition:**
   - Tasks exist locally but not on GitHub
   - Tell user: "Decomposition succeeded, sync failed"
   - Provide recovery: "Run: /pm:epic-sync $ARGUMENTS to retry sync"

3. **Partial Sync:**
   - Some issues created, others failed
   - List what succeeded and what failed
   - Offer rollback: "Delete created issues and retry? (yes/no)"
   - If no, provide: "Continue with: /pm:epic-sync $ARGUMENTS --resume"

### 7. Success Validation

After completion, verify:
- [ ] All task files created with valid frontmatter
- [ ] Epic issue exists on GitHub
- [ ] All task issues exist on GitHub
- [ ] All frontmatter updated with GitHub URLs
- [ ] Mapping file created

### 8. Post-Operation

On success:
1. Show comprehensive summary (as above)
2. Suggest: "View on GitHub: {epic_url}"
3. Recommend: "Start with highest priority task: /pm:next"

This command is ideal for confident workflows where the "$ARGUMENTS" epic is well-defined and ready for immediate decomposition and sync. Use with caution as it creates multiple GitHub issues in one operation.
