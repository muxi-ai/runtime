---
allowed-tools: Bash, Read, Write, LS
---

# Issue Close

Mark an issue as complete and close it on GitHub.

## Usage
```
/pm:issue-close <issue_number> [completion_notes]
```

## Instructions

### 1. Find Local Task File

Search for task file with `github:.*issues/$ARGUMENTS` in frontmatter.
If not found: "❌ No local task for issue #$ARGUMENTS"

### 2. Update Local Status

Get current datetime: `date -u +"%Y-%m-%dT%H:%M:%SZ"`

Update task file frontmatter:
```yaml
status: closed
updated: {current_datetime}
```

### 3. Update Progress File

If progress file exists at `.claude/epics/{epic}/updates/$ARGUMENTS/progress.md`:
- Set completion: 100%
- Add completion note with timestamp
- Update last_sync with current datetime

### 4. Close on GitHub

Add completion comment and close:
```bash
# Add final comment
echo "✅ Task completed

$ARGUMENTS

---
Closed at: {timestamp}" | gh issue comment $ARGUMENTS --body-file -

# Close the issue
gh issue close $ARGUMENTS
```

### 5. Update Epic Progress

- Count total tasks in epic
- Count closed tasks
- Calculate new progress percentage
- Update epic.md frontmatter progress field

### 6. Output

```
✅ Closed issue #$ARGUMENTS
  Epic progress: {new_progress}% ({closed}/{total} tasks complete)
  
Next: Run /pm:next for next priority task
```

## Important Notes

Follow `/rules/frontmatter-operations.md` for updates.
Follow `/rules/github-operations.md` for GitHub commands.
Always sync local state before GitHub.