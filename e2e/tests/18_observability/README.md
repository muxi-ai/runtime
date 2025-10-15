# E2E Tests: Observability & Init Formatting

Tests for initialization event formatting and observability system behavior.

## Test Suite Overview

### test_init_formatting_success.py
Tests successful formation initialization with Linux-style formatted output.

**Test Formations:**
- `1_foundation_basic` - Basic foundation with single agent
- `2_memory_persistent` - PostgreSQL persistent memory
- `7_multi_agent_mcp` - Multi-agent with MCP servers
- `12_scheduling` - Scheduler service enabled

**What It Tests:**
- Formation startup banner with version
- Database manager initialization
- Database table creation
- Buffer memory initialization (mode, size, vector search)
- Persistent memory initialization (type, multi-user mode)
- MCP server registration (tool count, transport type)
- A2A server/registry initialization
- Scheduler service initialization
- Agent loading (count, names)
- Formation ready summary with duration

**Output:**
All initialization output is captured to log files in:
```
e2e/results/<timestamp>/18_observability_init_success/
```

Each formation test creates:
- `<formation_name>_init.log` - Captured init output
- `<formation_name>_error.log` - Error details (if failed)
- `summary.txt` - Overall test summary

### test_init_formatting_failures.py
Tests failure scenarios to verify error formatting and graceful degradation.

**Test Scenarios:**
- `bad_postgres` - Invalid PostgreSQL connection string
- `bad_mcp_command` - Non-existent MCP server command
- `bad_a2a_registry` - Unreachable A2A registry

**What It Tests:**
- Structured error messages with operational guidance
- Graceful degradation when services unavailable
- Error formatting with causes and fixes
- Formation continues despite non-critical failures

**Output:**
All failure scenario output is captured to log files in:
```
e2e/results/<timestamp>/18_observability_init_failures/
```

Each scenario creates:
- `<scenario_name>_init.log` - Captured init output (may contain errors)
- `<scenario_name>_traceback.log` - Full Python traceback
- `summary.txt` - Overall test summary

## Running the Tests

### Success Scenarios
```bash
cd /Users/ran/Projects/muxi/code/runtime
python e2e/tests/18_observability/test_init_formatting_success.py
```

### Failure Scenarios
```bash
cd /Users/ran/Projects/muxi/code/runtime
python e2e/tests/18_observability/test_init_formatting_failures.py
```

## Expected Output Format

### Successful Initialization
```
============================================================
[  OK  ] MUXI Runtime v0.0.1 (starting)
============================================================

[  OK  ] Database manager (postgresql)
[  OK  ] Database tables (6 tables ready)
[  OK  ] Buffer memory (local mode, size=50, vector search enabled)
[  OK  ] Persistent memory (PostgreSQL, multi-user)
[  OK  ] MCP server: filesystem (14 tools, command transport)
[  OK  ] MCP server: web-search (5 tools, streamable_http transport)
[  OK  ] A2A server (localhost:8080, auth=none)
[  OK  ] Scheduler service (interval=1m, max_concurrent=5, tz=UTC)
[  OK  ] Agents (4 agents: IT Support, Project Manager, Researcher, +1 more)

[  OK  ] Formation ready (initialized in 2.3s)
============================================================
```

### Failure Formatting (Future Enhancement)
```
[ FAIL ] Database: PostgreSQL

  Connection refused (connection refused)
  
  The database server is not accepting connections. Common causes:
    • Database server is not running
    • Incorrect host or port in connection string
    • Firewall blocking the connection
    
  To fix:
    1. Check if PostgreSQL is running: pg_isready -h localhost -p 5432
    2. Verify connection string in formation config
    3. Check firewall/security group settings
  
  Config: formation.yaml:12 (memory.persistent.connection_string)
  
  Traceback (most recent call last):
    ...
```

## Implementation Status

✅ **Completed:**
- Linux-style formatted output ([OK], [WARN], [INFO])
- One line per service initialization
- Startup banner with version
- Formation ready summary with duration
- Output capture to files for inspection
- Test suite for success scenarios
- Test suite for failure scenarios

⏳ **Future Enhancements:**
- Structured error formatting (InitFailureInfo dataclass is ready)
- Fail-fast with [ FAIL ] indicators
- Startup warnings with [ WARN ] indicators
- More detailed failure scenario tests

## Test Results Location

All test results are saved with timestamps for easy inspection:
```
e2e/results/
└── YYYYMMDD_HHMMSS/
    ├── 18_observability_init_success/
    │   ├── 1_foundation_basic_init.log
    │   ├── 7_multi_agent_mcp_init.log
    │   ├── 12_scheduling_init.log
    │   └── summary.txt
    └── 18_observability_init_failures/
        ├── bad_postgres_init.log
        ├── bad_postgres_traceback.log
        ├── bad_mcp_command_init.log
        └── summary.txt
```

## Verifying Output

To view the formatted init output:
```bash
# Find latest test results
ls -t e2e/results/ | head -1

# View a specific init log
cat e2e/results/YYYYMMDD_HHMMSS/18_observability_init_success/7_multi_agent_mcp_init.log

# View summary
cat e2e/results/YYYYMMDD_HHMMSS/18_observability_init_success/summary.txt
```

## Notes

- Tests quit immediately after formation initialization (no chat interaction)
- All output is captured to files for visual inspection
- ANSI color codes are preserved in log files
- Tests verify formatting works across various formation configurations
- Failure tests verify graceful degradation and error handling
