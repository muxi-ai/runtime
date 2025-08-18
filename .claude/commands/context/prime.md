---
allowed-tools: Bash, Read, LS, WebFetch
---

# Prime context

This command loads essential context for a new agent session by reading the project context documentation and understanding the codebase structure.

## Instructions
- Read all files in the `.claude/context/` directory to understand the project comprehensively
- Run `git ls-files` to understand the codebase structure and file organization
- Read the `README.md` to understand the project's purpose, setup instructions, and key information
- Read the formation spec
   - [MUXI Formation Spec](schemas/formation/README.md)
   - [MUXI Formation directory](schemas/formation/)
- Tell me when you're done priming and provide a concise overview of the project based on the gathered context
