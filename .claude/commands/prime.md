---
allowed-tools: Bash, Read
---

# Prime context

This command loads essential context for a new agent session by reading the project context documentation and understanding the codebase structure.

## Instructions
- Read all files in the `/Users/ran/Projects/muxi/code/context/` directory (no recursion) to understand the project comprehensively
- Run `git ls-files` to understand the codebase structure and file organization
- Read the README.md to understand the project purpose, setup instructions, and key information
- Read the formation spec
   - [MUXI Formation Spec](schemas/formation/README.md)
   - [MUXI Formation directory](schemas/formation/)
- Provide a concise overview of the project based on the gathered context
- Tell me when you're done priming
