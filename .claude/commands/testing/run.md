---
allowed-tools: Bash, Read, Write, LS, Task
---

# Run Tests

Execute tests with the configured test-runner agent.

## Usage

```
/testing:run [test_target]
```

Where `test_target` can be:
- Empty (run all tests)
- Test file path
- Test pattern
- Test suite name

## Quick Check

If test target provided, verify it exists:

```bash
# For file targets
test -f "$ARGUMENTS" || echo "⚠️ Test file not found: $ARGUMENTS"
```

## Instructions

### 1. Determine Test Command

Based on testing-config.md and target:

- No arguments → Run full test suite from config
- File path → Run specific test file
- Pattern → Run tests matching pattern

### 2. Execute Tests

Use the test-runner agent from `.claude/agents/test-runner.md` to run tests and analyze the test results.

Using the test-runner agent ensures:

- Full test output is captured for debugging
- Main conversation stays clean and focused
- Context usage is optimized
- All issues are properly surfaced
- No approval dialogs interrupt the workflow

```markdown
Execute tests for: $ARGUMENTS (or "all" if empty)

Requirements:
- Run with verbose output for debugging
- No mocks - use real services
- Capture full output, including stack traces
- If the test fails, check the test structure before assuming a code issue
```

### 3. Monitor Execution

- Show test progress
- Capture stdout and stderr
- Note execution time

### 4. Report Results

**Success:**

```
✅ All tests passed ({count} tests in {time}s)
```

**Failure:**

```
❌ Test failures: {failed_count} of {total_count}

{test_name} - {file}:{line}
  Error: {error_message}
  Likely: {test issue | code issue}
  Fix: {suggestion}

Run with more detail: /testing:run {specific_test}
```

**Mixed:**

```
Tests complete: {passed} passed, {failed} failed, {skipped} skipped

Failed:
- {test_1}: {brief_reason}
- {test_2}: {brief_reason}
```


## Note About E2E Tests

Ensure every test ends up with a summary and the correspondence between the user and the overlord.

After all the logs are printed, add:

```
========================================

### Chat transcript:

User: ...
System: ...
User: ...
System: ...
```

## Error Handling

- Test command fails → "❌ Test execution failed: {error}. Check test framework is installed."
- Timeout → Kill process and report: "❌ Tests timed out after {time}s"
- No tests found → "❌ No tests found matching: $ARGUMENTS"

## Important Notes

- Always use the test-runner agent for analysis
- No mocking - real services only
- Keep a group-level report updated with progress in tests/reports/
- Make sure that tests are running with the chat flow. Each report should have the user prompts and the overlord's response (example report: tests/reports/1a.md).
- You can find the test mapping in tests/Comprehensive_Test_Plan.md.
- Do not move on to the next test until the current test is complete.
- If the test fails, consider checking if the test is structured correctly before deciding we need to refactor the codebase.
- Please consult this guide for more information on how to run the tests: tests/Lessons-Learned.md
