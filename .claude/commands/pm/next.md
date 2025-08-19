---
allowed-tools: Bash, Read, LS
---

# Next

Find the next priority task to work on.

## Usage
```
/pm:next
```

## Quick Check

```bash
# Check for epics
ls -d .claude/epics/*/ 2>/dev/null | head -1
```

If no epics: "❌ No epics found. Start with: /pm:prd-new {feature-name}"

## Instructions

### 1. Scan All Epics

For each epic directory in `.claude/epics/`:
- Read epic frontmatter for status and progress
- Count tasks with `status: open` in frontmatter
- Note any tasks marked `parallel: true`

### 2. Simple Priority Logic

Find the best next task using these rules:

1. **Incomplete epics near completion** (>70% done) - finish what's almost done
2. **First open task in active epics** - maintain momentum
3. **Any parallel task** - can start immediately
4. **First task in backlog epics** - start something new

### 3. Check GitHub Status (Optional)

If task has GitHub URL in frontmatter:
```bash
gh issue view {number} --json state
```
Skip if already closed on GitHub.

### 4. Display Recommendation

```
Next task: {task_name}

Epic: {epic_name} ({progress}% complete)
File: .claude/epics/{epic_name}/{task_file}
Type: {parallel|sequential}

Start with: /pm:issue-start {github_issue_number}
```

If multiple good options:
```
Other available tasks:
- {task_2}: {epic} (parallel)
- {task_3}: {epic} (sequential)
```

### 5. No Tasks Available

If no open tasks found:
```
No open tasks found.

Options:
- Create new epic: /pm:prd-new {feature}
- Check GitHub for updates: gh issue list --label task --state open
- Review completed work: /pm:epic-list
```

## Important Notes

- Keep priority logic simple
- Trust local frontmatter over GitHub state
- Focus on finishing epics before starting new ones
- Don't over-analyze - any forward progress is good