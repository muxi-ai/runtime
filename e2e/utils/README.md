# E2E Test Utilities

This directory contains shared utilities for e2e tests.

## Async Cleanup (`async_cleanup.py`)

Utilities for properly cleaning up asyncio tasks in tests to prevent "Task was destroyed but it is pending!" warnings.

### Quick Start

```python
import asyncio
from pathlib import Path
import sys

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # e2e/ for utils

from muxi.formation import Formation
from utils.async_cleanup import standard_test_cleanup

async def test_something():
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    try:
        # ... your test code ...
        pass

    except Exception as e:
        print(f"Test failed: {e}")
        raise

    finally:
        # Standard cleanup with task waiting
        await standard_test_cleanup(
            formation,
            wait_for_tasks=True,
            timeout=5.0,
            verbose=True
        )

if __name__ == "__main__":
    exit_code = asyncio.run(test_something())
    sys.exit(exit_code)
```

### Available Functions

#### `standard_test_cleanup(formation, wait_for_tasks=True, timeout=5.0, verbose=False)`

All-in-one cleanup for formation-based tests. Handles:
1. Waiting for background tasks (buffer memory writes, observability events)
2. Stopping the overlord
3. Stopping the formation
4. Final cleanup of any remaining tasks

**Parameters:**
- `formation`: The Formation instance to clean up
- `wait_for_tasks`: If True, wait for background tasks before shutdown
- `timeout`: Maximum seconds to wait for tasks
- `verbose`: Print cleanup progress

**Example:**
```python
finally:
    await standard_test_cleanup(formation, verbose=True)
```

#### `cleanup_pending_tasks(timeout=5.0, verbose=False)`

Clean up ALL pending asyncio tasks. Waits for tasks to complete, then cancels any that remain after timeout.

**Use when:** You need aggressive cleanup of all tasks, not just fire-and-forget ones.

```python
# At end of test
await cleanup_pending_tasks(timeout=5.0, verbose=True)
```

#### `wait_for_background_tasks(category=None, timeout=2.0, verbose=False)`

Wait for background tasks to complete naturally, without forcing cancellation.

**Use when:** You want to give fire-and-forget tasks time to finish, but don't want to block long.

```python
# After creating lots of buffer memory writes
await wait_for_background_tasks("memory writes", timeout=1.0)
```

#### `print_task_summary(verbose=True)`

Print debugging information about all asyncio tasks.

```python
# For debugging task leaks
print_task_summary(verbose=True)
```

### Why This Matters

Formation uses fire-and-forget tasks for performance:
- Buffer memory writes (`asyncio.create_task()`)
- Observability event emission (background threads)
- Memory extraction
- Credential updates

These tasks complete in milliseconds but might still be running when tests end. Without cleanup:
- Tests see "Task was destroyed but it is pending!" warnings
- Python's asyncio exception handler recurses (now fixed with custom handler)
- Logs are noisy

With cleanup:
- Background tasks complete gracefully
- Clean test output
- No warnings
- Proper resource cleanup

### Notes

- **Production impact**: None. This only affects tests that use `asyncio.run()`. Production servers run indefinitely.
- **Performance**: Adds 0-2 seconds to test cleanup (waiting for background tasks)
- **Required for**: Any test that creates fire-and-forget tasks (buffer memory, multi-turn conversations, etc.)
- **Optional for**: Simple single-request tests

### Troubleshooting

**"Still seeing task warnings"**
- Some warnings may occur mid-test during intermediate cleanup. This is normal.
- Cleanup only runs at test END, so can't catch mid-test warnings.
- As long as test passes, these are harmless.

**"Cleanup times out"**
- Check if tasks are truly stuck (deadlock, infinite loop)
- Increase timeout if tasks legitimately need more time
- Use `verbose=True` to see which tasks are pending

**"Import error"**
- Ensure path includes e2e/ directory: `sys.path.insert(0, str(Path(__file__).parent.parent.parent))`
- Check that `e2e/utils/__init__.py` exists
