---
allowed-tools: Bash, Read, LS
---

# Epic Status

Show real-time status of epic execution with parallel agents.

## Usage
```
/pm:epic-status <epic_name>
```

## Quick Check

```bash
test -f .claude/epics/$ARGUMENTS/epic.md || echo "❌ Epic not found: $ARGUMENTS"
```

## Instructions

### 1. Check Worktree Status

```bash
# Check if worktree exists
git worktree list | grep "epic-$ARGUMENTS"
```

If worktree exists:
```bash
# Get current status
cd ../epic-$ARGUMENTS
git status --short
git log --oneline -5
cd -
```

### 2. Read Execution Status

Read `.claude/epics/$ARGUMENTS/execution-status.md` if it exists.
Extract:
- Active agents and their streams
- Start times
- Queued issues
- Completed work

### 3. Check Stream Progress

For each active issue, read progress files:
```
.claude/epics/$ARGUMENTS/updates/{issue}/stream-*.md
```

Compile:
- Stream status (in_progress, completed, blocked)
- Completion percentage
- Current activity
- Any blockers

### 4. Analyze Git Activity

In the worktree:
```bash
# Recent commits by agents
cd ../epic-$ARGUMENTS
git log --oneline --since="1 day ago" | head -20

# Files being modified
git status --porcelain

# Uncommitted changes per area
git diff --stat

cd -
```

### 5. Check Issue Status

For each issue involved:
```bash
# Get GitHub status
gh issue view {issue_number} --json state,labels,assignees
```

Compare with local status to detect sync needs.

### 6. Identify Problems

Look for:
- Agents that haven't committed recently (>30 min)
- Streams marked as blocked
- Merge conflicts in worktree
- Failed tests or builds
- Divergence from main branch

### 7. Display Comprehensive Status

```
📊 Epic Status: $ARGUMENTS

📍 Worktree: ../epic-$ARGUMENTS
🌿 Branch: epic/$ARGUMENTS
⏱️ Running for: {duration}

Active Agents (3):
  Agent-1: Issue #1234 Stream A ✓ Running (45 min)
    Last commit: "Add user schema" (5 min ago)
    Progress: 60% - Creating migrations
    
  Agent-2: Issue #1234 Stream B ✓ Running (45 min) 
    Last commit: "Add service layer" (12 min ago)
    Progress: 40% - Implementing business logic
    
  Agent-3: Issue #1235 Stream A ⚠️ Blocked (20 min)
    Waiting for: Type definitions from #1234
    Will resume: Automatically when available

Completed Work:
  ✓ Issue #1233: Setup and configuration (2 hours ago)
  ✓ Issue #1234 Stream C: Documentation (1 hour ago)

Queued Issues (2):
  - #1236: Waiting for #1234 completion
  - #1237: Waiting for #1235 completion

Git Statistics:
  Commits today: 47
  Files changed: 23
  Insertions: +1,245
  Deletions: -89
  
Recent Commits:
  - 5a3f2d1 Issue #1234: Add user validation
  - 8b9c4e2 Issue #1234: Create user service
  - 2d7e9a3 Issue #1235: Setup API routes
  
Potential Issues:
  {⚠️ Agent-3 blocked for 20 minutes}
  {⚠️ No commits from Agent-2 in 12 minutes}

GitHub Sync:
  Last sync: {time} ago
  Issues needing sync: #1234, #1235
  Run: /pm:issue-sync {numbers}

Health: ⚠️ Good (1 agent blocked)

Next Actions:
  - Check blocked agent: /pm:agent-logs Agent-3
  - Sync progress: /pm:issue-sync 1234
  - View changes: cd ../epic-$ARGUMENTS && git diff
```

### 8. Provide Actionable Information

Based on status, suggest:
- If agents blocked: How to unblock
- If no recent commits: Check if agents need help
- If conflicts detected: How to resolve
- If work complete: Next steps for merging

## Quick Status Format

For a brief status (with --brief flag):
```
Epic: $ARGUMENTS
Agents: 3 active, 1 blocked
Progress: 45% (5/11 issues)
Health: ⚠️ (1 blocked)
```

## Error Conditions

Report clearly:
- "❌ No execution in progress for epic: $ARGUMENTS"
- "❌ Worktree missing. Run: /pm:epic-start $ARGUMENTS"
- "⚠️ Execution stalled - no activity for 1 hour"

## Important Notes

- Status is read-only - doesn't modify anything
- Should complete quickly (<5 seconds)
- Focus on actionable information
- Highlight problems that need attention