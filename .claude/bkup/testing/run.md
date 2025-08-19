---
allowed-tools: Bash, Read, Write, LS
---

# Run test(s)

I want to test $ARGUMENTS.

### Important:

- Keep a group-level report updated with progress in tests/reports/
- Make sure that tests are running with the chat flow. Each report should have the user prompts and the overlord's response (example report: tests/reports/1a.md).
- You can find the test mapping in tests/Comprehensive_Test_Plan.md.
- Do not use mock services for anything ever.
- Do not move on to the next test until the current test is complete.
- If the test fails, consider checking if the test is structured correctly before deciding we need to refactor the codebase.
- Please consult this guide for more information on how to run the tests: tests/Lessons-Learned.md

### Remember...
- Use the test-runner agent to execute tests.
- Do not use mock services for anything ever.
- Do not move on to the next test until the current test is complete.
- If the test fails, consider checking if the test is structured correctly before deciding we need to refactor the codebase.
- Tests to be verbose so we can use them for debugging.

