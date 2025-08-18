# Issue Start

Begin work on issue with specialized agent and progress tracking.

## Usage
```
/pm:issue-start <issue_number>
```

## Instructions

You are initiating work on a specific GitHub issue with proper setup and agent configuration for: **Issue #$ARGUMENTS**

### 1. Issue Validation
- Fetch issue details from GitHub using `gh issue view #$ARGUMENTS`
- Verify issue is open and assignable
- Check for any blocking dependencies

### 2. Find Local Task File
- Search for local task file with GitHub URL matching issue #$ARGUMENTS
- Look in all epic directories under `.claude/epics/`
- Extract task details and epic context

### 3. Update Task File Frontmatter
Update the local task file frontmatter to reflect work starting:
```yaml
---
name: [Task Title]
status: open
created: [existing date]
updated: [current date/time]
github: https://github.com/{org}/{repo}/issues/$ARGUMENTS
---
```

### 4. Local Workspace Setup
Create/verify local working environment:
```
.claude/epics/{epic_name}/
├── epic.md
├── {task_number}.md              # Task file for this issue
└── updates/
    └── $ARGUMENTS/               # Work-in-progress updates
        ├── progress.md           # Progress tracking
        ├── notes.md             # Development notes
        └── commits.md           # Commit history
```

### 5. Initialize Progress Tracking
Create initial progress file with frontmatter:
```markdown
---
issue: $ARGUMENTS
started: [current date/time]
last_sync: null
completion: 0%
---

# Progress: Issue #$ARGUMENTS

## Started
Date: {current_date}
Assignee: {github_username}

## Task Overview
{task_description}

## Acceptance Criteria
- [ ] {criterion_1}
- [ ] {criterion_2}
- [ ] {criterion_3}

## Work Log
### {current_date}
- Started work on issue
- Set up local development environment
- {initial_steps}

## Next Steps
- {planned_next_actions}

## Blockers
None currently

## Notes
{any_initial_observations}
```

### 6. Agent Configuration
Based on issue labels and content, configure specialized agent:

**Frontend Tasks** (labels: ui, frontend, component):
```markdown
# Agent: Frontend Developer

You are working on Issue #$ARGUMENTS: {title}

## Context
- Read the full task requirements from the local task file
- Review the epic context for architectural decisions
- Follow the project's UI/UX guidelines

## Development Approach
- Create components following the design system
- Implement responsive designs
- Add proper accessibility features
- Write component tests

## Progress Tracking
- Update progress.md with completed work
- Document any design decisions in notes.md
- Log commits and key changes
- Update task file frontmatter when status changes
```

**Backend Tasks** (labels: api, backend, service):
```markdown
# Agent: Backend Developer

You are working on Issue #$ARGUMENTS: {title}

## Context
- Read the full task requirements from the local task file
- Review API design patterns from the epic
- Follow security and performance guidelines

## Development Approach
- Implement API endpoints with proper validation
- Add comprehensive error handling
- Include monitoring and logging
- Write integration tests

## Progress Tracking
- Update progress.md with API completion status
- Document endpoint specifications
- Track performance metrics
- Update task file frontmatter when status changes
```

### 7. GitHub Assignment
- Assign issue to current user: `gh issue edit #$ARGUMENTS --add-assignee @me`
- Add "in-progress" label: `gh issue edit #$ARGUMENTS --add-label "in-progress"`

### 8. Development Environment
Check and prepare:
- Verify git branch strategy
- Check for required dependencies
- Set up any necessary environment variables
- Run initial tests to ensure clean starting state

### 9. Output Summary
```
🚀 Started work on Issue #$ARGUMENTS

📋 Task: {issue_title}
   Epic: {epic_name}
   Assignee: {username}
   
📁 Local workspace:
   Task file: .claude/epics/{epic_name}/{task_file}
   Updates: .claude/epics/{epic_name}/updates/$ARGUMENTS/
   
🤖 Agent configured: {agent_type}
   
✅ Ready to develop!
   
💡 Next steps:
   1. Review task requirements carefully
   2. Start implementation following the technical approach
   3. Update progress regularly in progress.md
   4. Sync updates with: /pm:issue-sync $ARGUMENTS
```

### 10. Error Handling
- Handle authentication issues with GitHub
- Check for conflicting assignments
- Verify write permissions to local directories
- Provide clear guidance for resolution

This command sets up everything needed for focused, tracked development work on Issue #$ARGUMENTS, ensuring frontmatter is properly maintained throughout the process.
