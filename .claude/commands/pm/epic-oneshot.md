# Epic Oneshot

Decompose epic into tasks and sync to GitHub in one operation.

## Usage
```
/pm:epic-oneshot <feature_name>
```

## Instructions

You are performing a complete epic decomposition and GitHub sync in a single operation for: **$ARGUMENTS**

### 1. Prerequisites Check
- Verify epic exists at `.claude/epics/$ARGUMENTS/epic.md`
- Ensure `gh` CLI is available and authenticated
- Confirm git repository with GitHub remote

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
If any step fails:
- Report exactly what succeeded and what failed
- Provide commands to continue manually
- Don't leave the system in an inconsistent state

This command is ideal for confident workflows where the "$ARGUMENTS" epic is well-defined and ready for immediate decomposition and sync.
