---
allowed-tools: Read
---

# PM Help

Display a quick reference of all PM commands.

## Usage
```
/pm:help
```

## Instructions

Display the following command reference:

```
📚 PM Command Reference

PLANNING
  /pm:prd-new <name>      Create PRD through brainstorming
  /pm:prd-parse <name>    Convert PRD to technical epic
  /pm:prd-list            List all PRDs
  /pm:prd-edit <name>     Edit existing PRD
  /pm:prd-status          Show PRD implementation status

EPIC MANAGEMENT
  /pm:epic-decompose <name>  Break epic into tasks
  /pm:epic-sync <name>       Push to GitHub & create worktree
  /pm:epic-oneshot <name>    Decompose + sync in one step
  /pm:epic-list              List all epics
  /pm:epic-show <name>       Display epic details
  /pm:epic-edit <name>       Edit epic details
  /pm:epic-close <name>      Mark epic complete
  /pm:epic-refresh <name>    Update progress from tasks

PARALLEL EXECUTION
  /pm:epic-start <name>    Launch parallel agents for epic
  /pm:epic-status <name>   Monitor parallel execution
  /pm:epic-merge <name>    Merge epic to main branch

ISSUE/TASK WORK
  /pm:issue-analyze <#>    Identify parallel work streams
  /pm:issue-start <#>      Start work (requires analysis)
  /pm:issue-sync <#>       Push progress to GitHub
  /pm:issue-show <#>       Display issue details
  /pm:issue-status <#>     Check issue status
  /pm:issue-close <#>      Mark issue complete
  /pm:issue-reopen <#>     Reopen closed issue
  /pm:issue-edit <#>       Edit issue details

WORKFLOW
  /pm:next                Find next priority task
  /pm:status              Project dashboard
  /pm:standup             Daily standup report
  /pm:blocked             Show blocked tasks
  /pm:in-progress         List active work

SYNC & MAINTENANCE
  /pm:sync                Full GitHub sync
  /pm:import              Import GitHub issues
  /pm:validate            Check system integrity
  /pm:clean               Archive completed work
  /pm:search <query>      Search all content

QUICK START
  1. Create PRD:        /pm:prd-new feature
  2. Create epic:       /pm:prd-parse feature
  3. Break down:        /pm:epic-oneshot feature
  4. Start work:        /pm:epic-start feature
  5. Check progress:    /pm:epic-status feature
  6. Merge:            /pm:epic-merge feature

For detailed docs: See README.md
```