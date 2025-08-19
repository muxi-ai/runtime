---
allowed-tools: Bash, Read, Write, LS
---

# How to run tests

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
   - [Runtime Test Plan.md](tests/Comprehensive_Test_Plan.md)
   - [Runtime Testing Guide](tests/Lessons-Learned.md)


### IMPORTANT
- Use the test-runner agent to execute tests.
- Do not use mock services for anything ever.
- Do not move on to the next test until the current test is complete.
- If the test fails, consider checking if the test is structured correctly before deciding we need to refactor the codebase.
- Tests to be verbose so we can use them for debugging.


