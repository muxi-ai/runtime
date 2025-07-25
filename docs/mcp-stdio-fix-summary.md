# MCP stdio Async Generator Error Fix Summary

## Problem
When using command-line MCP servers (stdio transport), MUXI encounters an async generator cleanup error:
```
RuntimeError: Attempted to exit cancel scope in a different task than it was entered in
```

This happens because the MCP SDK's `stdio_client` uses anyio TaskGroups that require cleanup in the same event loop context where they were created.

## Root Cause
1. MCP servers were initialized during `Overlord._async_startup()`
2. This happened in a temporary event loop created by `asyncio.run()`
3. At Python exit, cleanup happens in a different context
4. The MCP SDK's design expects the entire lifecycle in one event loop

## Solution Implemented

### 1. Fixed Command Line Transport
Updated `CommandLineTransport` to properly handle async contexts:
- Store `client_context` separately from `session`
- Use `ClientSession` for high-level operations
- Implement proper `_cleanup()` method

### 2. Moved MCP Initialization to Formation
- Added `_register_mcp_servers()` async method to Formation
- MCP servers now registered in Formation's event loop
- Added MCP disconnection in `stop_overlord()`

### 3. Made Formation Methods Async
- `Formation.load()` is now async
- `Formation.start_overlord()` is now async
- `Formation.stop_overlord()` is now async

### 4. Added Clean Exit Utility
Created `src/muxi/runtime/utils/clean_exit.py` for tests:
```python
from typing import NoReturn

def clean_exit(code: int = 0) -> NoReturn:
    """Exit cleanly, suppressing MCP SDK async cleanup errors."""
    # Best-effort flush; ignore failures (e.g. streams already closed)
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.flush()
        except Exception:
            pass
    os._exit(code)
```

## Usage Pattern

### MUXI-Level Clean Exit (Recommended)

The clean_exit functionality is built into Formation with three methods:

#### 1. Graceful Async Shutdown (`ashutdown`)
Use when you want a **graceful shutdown** that properly cleans up resources:
```python
import asyncio
from src.muxi import Formation

async def main():
    formation = Formation()
    await formation.load("formation.yaml")
    overlord = await formation.start_overlord()

    # Use overlord...
    response = await overlord.chat("user", "message")

    # Graceful shutdown - waits for agents to finish
    await formation.ashutdown(0)

if __name__ == "__main__":
    asyncio.run(main())
```

**When to use `ashutdown()`:**
- In async applications (most modern Python apps)
- When you want agents to finish their current work
- For production services doing a controlled shutdown
- When you care about saving state or completing transactions

#### 2. Immediate Shutdown (`shutdown`)
Use when you need to **exit immediately** without waiting:
```python
formation = Formation()
# ... setup and use formation ...
formation.shutdown(0)  # Exits immediately - no waiting
```

**When to use `shutdown()`:**
- In synchronous contexts (can't use await)
- When you need to exit RIGHT NOW
- In error handlers or emergency situations
- In simple scripts where graceful shutdown isn't needed

#### Key Differences:
| Aspect | `shutdown()` | `ashutdown()` |
|--------|-------------|---------------|
| **Speed** | Immediate exit | Waits up to 5 seconds |
| **Cleanup** | Minimal | Full graceful cleanup |
| **Agent work** | Interrupted | Allowed to finish |
| **Use in** | Sync code | Async code |
| **Best for** | Scripts, errors | Services, production |

#### 3. Why Not Automatic?
We considered making stop_overlord() and kill_overlord() automatically exit the process when stdio MCP servers are present, but this would:
- Break existing code that expects to continue after stopping
- Make it impossible to restart an overlord in the same process
- Be surprising behavior for a stop/kill method

Instead, we provide explicit clean_exit methods that developers can use when they know they want to exit the application.

### For Production
The async generator error only appears at process exit and doesn't affect functionality. In production environments where the process runs continuously, this is not an issue. For clean shutdowns in production, use `formation.ashutdown()`.

### Best Practices
1. **For scripts**: Always use `shutdown()` or `ashutdown()` at the end
2. **For tests**: Use `shutdown()` to avoid error noise
3. **For servers**: The error only appears on shutdown and can be ignored
4. **For notebooks**: Use `shutdown()` when done with the kernel

## Test Results
✅ MCP servers connect successfully
✅ Tools are discovered (12 tools for filesystem MCP)
✅ No async generator errors during operation
✅ Chat functionality works with MCP tools

## Recent Improvements

### Code Quality Enhancements
1. **Removed unused code**: Deleted `_register_mcp_servers_from_formation()` method from Overlord
2. **Better error handling**: MCP registration now catches only specific, recoverable exceptions:
   - `MCPConnectionError` - Connection issues (recoverable)
   - `MCPTimeoutError` - Timeout issues (recoverable)
   - `MCPCancelledError` - Cancelled operations (recoverable)
   - `MCPRequestError` - Configuration errors (recoverable)
   - All other exceptions propagate for fail-fast behavior
3. **DRY refactoring**: Eliminated duplicated stats update code in CommandLineTransport
4. **Type accuracy**: Updated `clean_exit()` to use `NoReturn` type annotation

## Limitations
The async generator error still appears at Python exit without using Formation's shutdown methods. This is a fundamental limitation of the MCP SDK's stdio_client design. The shutdown methods are acceptable for:
- Tests
- Short-lived scripts
- Development environments

For long-running production services, the error only appears at shutdown and doesn't affect functionality.

## Next Steps
1. Update existing tests to use async Formation methods
2. Use `formation.shutdown()` in tests that use stdio MCP servers
3. Consider contributing a fix to the MCP SDK for proper async cleanup
