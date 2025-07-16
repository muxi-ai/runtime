---
allowed-tools: Bash, Read
---

# Prime tests

This command loads essential context for a new agent session by examining the codebase structure and reading the project README.

## Instructions
- Run `git ls-files` to understand the codebase structure and file organization
- Read the README.md to understand the project purpose, setup instructions, and key information
- Provide a concise overview of the project based on the gathered context
- Read the formation spec
- Read the test plan and guide

## Context
- Codebase structure git accessible: !`git ls-files`
- Codebase structure all: !`eza . --tree`
- Project README: @README.md
- Read the formation spec
   - [MUXI Formation Spec](schemas/formation/README.md)
   - [MUXI Formation directory](schemas/formation/)
- Read the test plan
   - [Runtime Test Plan.md](MUXI_Runtime_Comprehensive_Test_Plan.md)
   - [Runtime Testing Guide](MUXI_Runtime_Testing_Guide.md)
