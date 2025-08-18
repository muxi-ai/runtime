# Claude Code: Project Management System

A context-preserving, GitHub Issues-driven workflow for managing complex software projects with Claude Code. This system enables parallel development, maintains context across sessions, and provides a structured approach to spec-driven development.

## Philosophy

This system follows a strict spec-driven development approach:
1. **Brainstorm** thoroughly before coding
2. **Document** product requirements comprehensively
3. **Plan** implementation details
4. **Execute** to the letter
5. **Track** progress transparently

No "vibe coding" - every line of code traces back to a specification.

## System Architecture

```
.claude/
├── CLAUDE.md          # Always-on instructions & repo metadata
├── context/           # Project-wide context files
├── prds/              # Product requirement documents
├── epics/             # ← PM's local workspace (place in .gitignore)
│   ├── [epic-name]/   # Epic and related tasks
│   │   ├── epic.md    # Implementation plan
│   │   ├── [#].md     # Individual task files
│   │   └── updates/   # Work-in-progress updates
├── agents/            # Specialized agent configurations
└── commands/          # Command definitions
    └── pm/            # ← Project management commands (this system)
```

## Workflow

### 1. Product Planning Phase

```bash
/pm:prd-new feature-name
```
Launches a comprehensive brainstorming session to create a Product Requirements Document (PRD). The PRD captures the complete vision, user stories, success criteria, and constraints.

Output: `.claude/prds/feature-name.md`

### 2. Implementation Planning Phase

```bash
/pm:prd-parse feature-name
```
Transforms the PRD into a technical implementation plan (epic). This includes architectural decisions, technical approach, task breakdown, and dependency mapping.

Output: `.claude/epics/feature-name/epic.md`

### 3. Task Decomposition Phase

```bash
/pm:epic-decompose feature-name
```
Breaks down the epic into concrete, actionable tasks. Each task includes acceptance criteria, estimated effort, and parallelization flags.

Output: `.claude/epics/feature-name/[task].md` files

### 4. GitHub Synchronization

```bash
/pm:epic-sync feature-name
```
Pushes the epic and all tasks to GitHub as issues with appropriate labels and relationships.

For confident workflows:

```bash
/pm:epic-oneshot feature-name
```
Decomposes and syncs in a single operation.

### 5. Execution Phase

```bash
/pm:issue-start 1234
```
Fetches issue details from GitHub (if needed), creates a local working copy, and launches a specialized agent to implement the task. The agent maintains progress updates throughout development.

```bash
/pm:issue-sync 1234
```
Pushes local updates as GitHub issue comments, creating a transparent audit trail of development progress.

## Command Reference

### PRD Commands
- **`/pm:prd-new`** - Launch brainstorming for new product requirement
- **`/pm:prd-parse`** - Convert PRD to implementation epic
- **`/pm:prd-list`** - List all PRDs

### Epic Commands
- **`/pm:epic-decompose`** - Break epic into task files
- **`/pm:epic-sync`** - Push epic and tasks to GitHub
- **`/pm:epic-oneshot`** - Decompose and sync in one command
- **`/pm:epic-list`** - List all epics
- **`/pm:epic-show`** - Display epic and its tasks

### Issue Commands
- **`/pm:issue-show`** - Display issue and sub-issues
- **`/pm:issue-status`** - Check issue status (open/closed)
- **`/pm:issue-start`** - Begin work on issue with specialized agent
- **`/pm:issue-sync`** - Push updates to GitHub

### Workflow Commands
- **`/pm:next`** - Show next priority issue to work on with epic context

## Key Features

### Context Preservation
- Each epic maintains its own context in `.claude/epics/[epic-name]/`
- Agents can read full project context from `.claude/context/`
- Updates are tracked locally before GitHub sync

### Parallel Execution
- Tasks marked with `parallel: true` can run simultaneously
- Multiple agents can work on different tasks without conflicts
- Each agent maintains its own update log

### GitHub Integration
- Issues are the source of truth for the task state
- Comments provide development history
- No dependency on GitHub Projects - works with plain issues
- Projects can be added as an optional visualization layer

### Agent Specialization
- Different agents for different domains (UI, API, database)
- Agents read task requirements from local files
- Progress updates posted to GitHub automatically

## Local vs Remote

| Operation | Local | GitHub |
|-----------|-------|--------|
| PRD Creation | ✓ | |
| Implementation Planning | ✓ | |
| Task Breakdown | ✓ | |
| Execution | ✓ | |
| Status Updates | ✓ | ✓ (sync) |
| Final Deliverables | | ✓ |

## Example Flow

```bash
# Start a new feature
/pm:prd-new memory-system

# Review and refine the PRD...

# Create implementation plan
/pm:prd-parse memory-system

# Review the epic...

# Break into tasks and push to GitHub
/pm:epic-oneshot memory-system
# Creates issues: #1234 (epic), #1235, #1236 (tasks)

# Start development on a task
/pm:issue-start 1235
# Agent begins work, maintains local progress

# Sync progress to GitHub
/pm:issue-sync 1235
# Updates posted as issue comments

# Check overall status
/pm:epic-show memory-system
```

## Benefits

- **No Context Loss**: Persistent context across sessions
- **Parallel Development**: Multiple agents on independent tasks
- **Full Traceability**: Every decision traces to specifications
- **GitHub Native**: Leverages existing issue infrastructure
- **Tool Agnostic**: Other developers can use standard GitHub tools
- **Incremental Sync**: Work locally, sync when ready

## Setup

1. Create `.claude/` directory structure in your repository
2. Add `.claude/epics/` to `.gitignore`
3. Ensure `gh` CLI is installed and authenticated
4. Copy command definitions to `.claude/commands/pm/`
5. Create `.claude/CLAUDE.md` with repository information

## Notes

- The system intentionally avoids GitHub Projects API complexity
- Issues use labels for organization (e.g., `epic:memory-system`, `task:memory-system`)
- GitHub Projects can be configured separately for visualization
- All commands operate on local files first for speed
- Synchronization with GitHub is explicit and controlled

---

*This system prioritizes developer productivity through structured planning, context preservation, and seamless GitHub integration while maintaining simplicity and flexibility.*
