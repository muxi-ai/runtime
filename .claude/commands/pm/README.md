# Project Management Commands

A comprehensive command system for GitHub Issues-driven project management with Claude Code.

## Command Categories

### PRD (Product Requirements) Commands
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

## Workflow Overview

1. **Product Planning**: `/pm:prd-new feature-name`
2. **Technical Planning**: `/pm:prd-parse feature-name`
3. **Task Creation**: `/pm:epic-decompose feature-name`
4. **GitHub Sync**: `/pm:epic-sync feature-name` (or use `/pm:epic-oneshot`)
5. **Find Next Work**: `/pm:next`
6. **Development**: `/pm:issue-start 1234`
7. **Progress Updates**: `/pm:issue-sync 1234`
8. **Repeat**: `/pm:next` → work → sync

## Smart Work Prioritization

The `/pm:next` command provides intelligent recommendations by:
- **Prioritizing blocking tasks** that unlock other work
- **Suggesting parallel tasks** when sequential work is blocked
- **Showing epic context** and progress within larger initiatives
- **Checking dependencies** to ensure work is ready to start
- **Providing alternatives** when multiple good options exist

Example output:
```
🎯 Next Recommended Issue

📋 Issue #1234: Implement user authentication API
   Epic: user-management  
   Progress: 3/8 tasks complete (37.5%)
   Estimate: M (16 hours)
   
🚀 Quick Start: /pm:issue-start 1234
```

## Directory Structure

```
.claude/
├── prds/              # Product requirement documents
├── epics/             # Local epic workspace (add to .gitignore)
│   ├── [epic-name]/   # Epic and related tasks
│   │   ├── epic.md    # Implementation plan
│   │   ├── [#].md     # Individual task files  
│   │   └── updates/   # Work-in-progress updates
└── commands/pm/       # These command files
```

## Prerequisites

- `gh` CLI installed and authenticated
- Git repository with GitHub remote
- Claude Code environment

## Key Features

- **Context Preservation**: Persistent context across sessions
- **Parallel Development**: Multiple agents on independent tasks  
- **Full Traceability**: Every decision traces to specifications
- **GitHub Native**: Leverages existing issue infrastructure
- **Incremental Sync**: Work locally, sync when ready
- **Smart Prioritization**: Always know what to work on next

## Setup

1. Copy these command files to `.claude/commands/pm/`
2. Create `.claude/prds/` and `.claude/context/` directories
3. Add `.claude/epics/` to `.gitignore`
4. Ensure GitHub CLI is authenticated: `gh auth status`

## Quick Start

```bash
# Start your first project
/pm:prd-new user-authentication

# Create implementation plan  
/pm:prd-parse user-authentication

# Break into tasks and sync to GitHub
/pm:epic-oneshot user-authentication

# Find the next priority task
/pm:next

# Start working on the recommended issue
/pm:issue-start 1234

# Sync your progress
/pm:issue-sync 1234

# Find the next task when ready
/pm:next
```

The system maintains momentum by always providing clear next steps and preserving context across development sessions!
