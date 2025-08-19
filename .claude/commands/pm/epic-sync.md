---
allowed-tools: Bash, Read, Write, LS
---

# Epic Sync

Push epic and tasks to GitHub as issues.

## Usage
```
/pm:epic-sync <feature_name>
```

## Quick Check

```bash
# Verify epic exists
test -f .claude/epics/$ARGUMENTS/epic.md || echo "❌ Epic not found. Run: /pm:prd-parse $ARGUMENTS"

# Count task files
ls .claude/epics/$ARGUMENTS/*.md 2>/dev/null | grep -v epic.md | wc -l
```

If no tasks found: "❌ No tasks to sync. Run: /pm:epic-decompose $ARGUMENTS"

## Instructions

### 1. Create Epic Issue

Read epic content and create GitHub issue:
```bash
gh issue create \
  --title "Epic: $ARGUMENTS" \
  --body-file .claude/epics/$ARGUMENTS/epic.md \
  --label "epic,epic:$ARGUMENTS"
```

Store the returned issue number for epic frontmatter update.

### 2. Create Task Issues

For each numbered task file (001.md, 002.md, etc.):
```bash
gh issue create \
  --title "{task_name_from_frontmatter}" \
  --body-file .claude/epics/$ARGUMENTS/{task_file} \
  --label "task,epic:$ARGUMENTS"
```

Store each returned issue number.

### 3. Update Local Files

Follow `/rules/frontmatter-operations.md` to update:
- Epic file: Add `github: {issue_url}` to frontmatter
- Each task file: Add `github: {issue_url}` to frontmatter
- Update `updated` field with current datetime (see `/rules/datetime.md`)

### 4. Create Mapping File

Create `.claude/epics/$ARGUMENTS/github-mapping.md`:
```markdown
# GitHub Issue Mapping

Epic: #{number} - {url}

Tasks:
- #{number}: {title} - {url}
- #{number}: {title} - {url}

Synced: {current_datetime}
```

### 5. Create Worktree

Follow `/rules/worktree-operations.md` to create development worktree:

```bash
# Ensure main is current
git checkout main
git pull origin main

# Create worktree for epic
git worktree add ../epic-$ARGUMENTS -b epic/$ARGUMENTS

echo "✅ Created worktree: ../epic-$ARGUMENTS"
```

### 6. Output

```
✅ Synced to GitHub
  - Epic: #{number}
  - Tasks: {count} issues created
  - Labels: epic:$ARGUMENTS
  - Worktree: ../epic-$ARGUMENTS

Next steps:
  - Start parallel execution: /pm:epic-start $ARGUMENTS
  - Or work on single issue: /pm:issue-start {task_number}
```

## Error Handling

Follow `/rules/github-operations.md` for GitHub CLI errors.

If any issue creation fails:
- Report what succeeded
- Note what failed
- Don't attempt rollback (partial sync is fine)

## Important Notes

- Trust GitHub CLI authentication
- Don't pre-check for duplicates
- Update frontmatter only after successful creation
- Keep operations simple and atomic