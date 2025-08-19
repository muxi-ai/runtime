---
allowed-tools: Read, LS, Grep
---

# Blocked

Show all blocked tasks and their blockers.

## Usage
```
/pm:blocked
```

## Instructions

### 1. Scan for Blocked Tasks

Search across all epic directories:
- Look in progress.md files for "blocked", "waiting", "dependency"
- Check task files for dependency fields that reference open tasks
- Find tasks with 0% progress despite being started >2 days ago

### 2. Identify Blocker Types

Categorize blockers:
- **Dependency**: Waiting on another task
- **External**: Waiting on external team/service
- **Information**: Missing requirements/specs
- **Technical**: Technical issue blocking progress
- **Review**: Waiting for review/approval

### 3. Display Blocked Tasks

```
🚫 Blocked Tasks

{epic_name}/{task_name}:
  Type: Dependency
  Blocked by: Task #{number} - {task_name}
  Since: {date_blocked}
  Notes: {any_notes_from_progress_file}

{epic_name}/{task_name}:
  Type: External
  Blocked by: {description}
  Since: {date_blocked}
  Action needed: {what_would_unblock}

Summary:
  Total blocked: {count}
  By type:
    - Dependencies: {count}
    - External: {count}
    - Other: {count}

Suggested actions:
  {For dependency blocks, show which tasks to complete first}
  {For external blocks, suggest follow-up actions}
```

### 4. No Blockers

If no blocked tasks found:
```
✅ No blocked tasks

All in-progress work can proceed.
Run /pm:next to see priority tasks.
```

## Important Notes

Focus on actionable blockers that can be resolved.
Don't list completed or abandoned blockers.
Provide clear next steps to unblock.