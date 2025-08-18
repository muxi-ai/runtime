---
allowed-tools: Bash, Read, Write, LS
---

# Create Initial Context

This command creates the initial project context documentation in `.claude/context/` by analyzing the current project state and establishing comprehensive baseline documentation.

## Instructions
- Analyze the project structure, codebase, and documentation to understand the current state
- **IMPORTANT**: if this is a new project, engage with the user to understand the project better
- Create the `.claude/context/` directory if it doesn't exist
- Generate the following initial context files:
  - `progress.md` - Document current project status, completed work, and immediate next steps
  - `project-structure.md` - Map out the directory structure and file organization
  - `tech-context.md` - Catalog current dependencies, technologies, and development tools
  - `system-patterns.md` - Identify existing architectural patterns and design decisions
  - `product-context.md` - Define product requirements, target users, and core functionality
  - `project-brief.md` - Establish project scope, goals, and key objectives
  - `project-overview.md` - Provide a high-level summary of features and capabilities
  - `project-vision.md` - Articulate long-term vision and strategic direction
  - `project-style-guide.md` - Document coding standards, conventions, and style preferences
- Base documentation on existing code, README, package files, and any available documentation
- Create comprehensive but concise initial documentation
- Use consistent formatting and structure across all files
- Tell me which files were created and provide a brief summary of each

## Context
- Target directory: `.claude/context/` (create if needed)
- Current git status: `git status --short`
- Recent commits: `git log --oneline -10`
- Project README: `README.md`
- Package files: `package.json`, `requirements.txt`, `Cargo.toml`, etc.
- Existing documentation in `docs/` or similar directories

$ARGUMENTS
