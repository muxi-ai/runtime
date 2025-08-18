---
allowed-tools: Bash, Read, Write, LS
---

# Update Context

This command updates the project context documentation in `.claude/context/` to reflect the current state of the project. Run this at the end of each development session to keep context accurate.

## Instructions
- Review the current state of the project by examining recent changes and progress
- Update the following context files as needed:
  - `progress.md` - Update with any completed tasks, new issues, or status changes
  - `project-structure.md` - Update if directory structure or organization changed
  - `tech-context.md` - Update if new dependencies or technologies were added
  - `system-patterns.md` - Update if new architectural patterns were introduced
  - `product-context.md` - Update if product direction or user needs have evolved
  - `project-brief.md` - Update if project scope or goals changed
  - `project-overview.md` - Update if major features or status have changed
  - `project-vision.md` - Update if vision or strategic direction changed
  - `project-style-guide.md` - Update if project style guide changed
- Only update files that have actual changes to reflect
- Keep updates concise and focused on what changed
- Preserve the existing structure and format of each document
- Tell me which files were updated and summarize the changes

## Context
- Context directory: `.claude/context/`
- Current git status: `git status --short`
- Recent commits: `git log --oneline -10`
- Project README: `README.md`

$ARGUMENTS
