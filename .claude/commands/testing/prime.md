---
allowed-tools: Bash, Read, Write, LS
---

# Prime Testing Environment

This command prepares the testing environment by detecting the test framework, validating dependencies, and configuring the test-runner agent for optimal test execution.


## Preflight Checklist

Before proceeding, consume the following context:

- Codebase structure git accessible: !`git ls-files`
- Codebase structure all: !`eza . --tree`
- Project README: @README.md
- Read the formation spec
   - [MUXI Formation Spec](schemas/formation/README.md)
   - [MUXI Formation directory](schemas/formation/)
- Read the test plan
   - [Runtime Test Plan.md](tests/Comprehensive_Test_Plan.md)
   - [Runtime Testing Guide](tests/Lessons-Learned.md)
   
## Instructions

### Always use the test-runner sub-agent to run tests and analyze the test results.

Using the test-runner agent ensures:

- Full test output is captured for debugging
- Main conversation stays clean and focused
- Context usage is optimized
- All issues are properly surfaced
- No approval dialogs interrupt the workflow

### Note about e2e tests

Ensure every test ends up with a summary and the correspondence between the user and the overlord.

After all the logs are printed, add:

```
========================================

### Test Result:
  🎉 SUCCESS: ...
  ✓ ...
  ✓ ...
  ✓ ...

========================================

### Chat transcript:

User: ...
System: ...
User: ...
System: ...
```

## Important Notes

- **Always detect** rather than assume test framework
- **Validate dependencies** before claiming ready
- **Configure for debugging** - verbose output is critical
- **No mocking** - use real services for accurate testing
- **Sequential execution** - avoid parallel test issues
- **Store configuration** for consistent future runs

$ARGUMENTS
