# Epic Sync

Push epic and all tasks to GitHub as issues.

## Usage
```
/pm:epic-sync <feature_name>
```

## Instructions

You are synchronizing local epic and tasks to GitHub Issues for: **$ARGUMENTS**

### 1. Verify Prerequisites
- Ensure `gh` CLI is installed and authenticated
- Check that you're in a git repository with GitHub remote
- Verify epic and task files exist locally for "$ARGUMENTS"

### 2. Create Epic Issue
- Read the epic from `.claude/epics/$ARGUMENTS/epic.md`
- Create GitHub issue with:
  - Title: `Epic: $ARGUMENTS`
  - Body: Full epic content (excluding frontmatter)
  - Labels: `epic`, `epic:$ARGUMENTS`

### 3. Create Task Issues
For each task file in `.claude/epics/$ARGUMENTS/`:
- Read task content
- Create GitHub issue with:
  - Title: `{Task Title}` (from frontmatter name field)
  - Body: Full task content (excluding frontmatter)
  - Labels: `task`, `epic:$ARGUMENTS`
  - Link to epic issue in description

### 4. GitHub CLI Commands
Use these commands for issue creation:

```bash
# Create epic issue
gh issue create \
  --title "Epic: $ARGUMENTS" \
  --body-file ".claude/epics/$ARGUMENTS/epic.md" \
  --label "epic,epic:$ARGUMENTS"

# Create task issue
gh issue create \
  --title "{Task Title}" \
  --body-file ".claude/epics/$ARGUMENTS/{task_file}" \
  --label "task,epic:$ARGUMENTS"
```

### 5. Update Local Files with GitHub URLs
After creating issues, update frontmatter in local files:

**Epic file** (`.claude/epics/$ARGUMENTS/epic.md`):
```yaml
---
name: $ARGUMENTS
status: in-progress
created: [existing date]
progress: 0%
prd: .claude/prds/$ARGUMENTS.md
github: https://github.com/{org}/{repo}/issues/{epic_number}
---
```

**Task files** (`.claude/epics/$ARGUMENTS/{task}.md`):
```yaml
---
name: [Task Title]
status: open
created: [existing date]
updated: [current date/time]
github: https://github.com/{org}/{repo}/issues/{task_number}
---
```

### 6. Create GitHub Mapping File
Create mapping file: `.claude/epics/$ARGUMENTS/github-mapping.md`
```markdown
# GitHub Issue Mapping for $ARGUMENTS

## Epic
- Epic Issue: #{epic_number} - https://github.com/{org}/{repo}/issues/{epic_number}

## Tasks
- Task #{task1_number}: {Task 1 Title} - https://github.com/{org}/{repo}/issues/{task1_number}
- Task #{task2_number}: {Task 2 Title} - https://github.com/{org}/{repo}/issues/{task2_number}
- etc.

## Labels Used
- epic:$ARGUMENTS
- epic
- task

Synced on: {current_date}
```

### 7. Output Summary
Display:
```
✅ Epic synced to GitHub
   Epic Issue: #{epic_number}
   
✅ Tasks synced to GitHub
   Task #{task1_number}: {Task 1 Title}
   Task #{task2_number}: {Task 2 Title}
   etc.

📋 Summary
   Epic: #{epic_number}
   Tasks: {task_count} issues created
   Labels: epic:$ARGUMENTS
   
📁 Files Updated
   Epic frontmatter updated with GitHub URL
   Task frontmatter updated with GitHub URLs
   GitHub mapping created
```

### 8. Error Handling
- Check for authentication issues
- Verify repository access
- Handle rate limiting
- Provide clear error messages and solutions

Synchronize all components of the "$ARGUMENTS" epic to GitHub for transparent project tracking, ensuring all local frontmatter is updated with GitHub URLs.
