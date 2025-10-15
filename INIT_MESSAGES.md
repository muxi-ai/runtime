# MUXI Formation Init Messages

This document lists all initialization messages shown during formation startup.
Edit these messages to improve clarity and consistency.

## Format

Each message follows the pattern: `[STATUS] Component/Service (details)`

- `[  OK  ]` - Success (green)
- `[ WARN ]` - Warning (yellow)
- `[ INFO ]` - Information (blue)
- `[ FAIL ]` - Failure (red)

---

## 1. Formation Banner

**Location:** `src/muxi/formation/formation.py:358`

**Current:**
```
MUXI Runtime v{version} (starting)
```

**Human-friendly alternative:**
```
Starting MUXI Runtime v{version}...
```

**Variables:**
- `{version}` - from `.version` file (e.g., "0.2025.0")

---

## 2. Buffer Memory

**Location:** `src/muxi/formation/initialization.py:1001`

**Current:**
```
[  OK  ] Buffer memory ({mode} mode, size={size}, vector search {enabled/disabled})
```

**Human-friendly alternative:**
```
[  OK  ] Initializing buffer memory ({mode}, {size} messages, contextual search {enabled/disabled})
```

**Variables:**
- `{mode}` - "local" or "remote"
- `{size}` - buffer size (e.g., "10", "50")
- `vector search enabled/disabled` - based on configuration

---

## 3. Database Tables

**Location:** `src/muxi/formation/initialization.py:781`

**Current:**
```
[  OK  ] Database tables ({count} tables ready)
```

**Human-friendly alternative:**
```
[  OK  ] Database schema ready ({count} tables initialized)
```

**Variables:**
- `{count}` - number of tables (e.g., "6")

---

## 4. Persistent Memory

**Location:** `src/muxi/formation/initialization.py:1117`

**Current:**
```
[  OK  ] Persistent memory ({type}, {mode})
```

**Human-friendly alternative:**
```
[  OK  ] Initializing persistent memory ({type} / {mode} mode)
```

**Variables:**
- `{type}` - "PostgreSQL" or "SQLite"
- `{mode}` - "multi-user" or "single-user"

---

## 5. MCP Servers (one line per server)

**Location:** `src/muxi/formation/initialization.py:549`

**Current:**
```
[  OK  ] MCP server: {server_id} ({tool_count} tools, {transport} transport)
```

**Human-friendly alternative:**
```
[  OK  ] Connected to MCP server '{server_id}' ({tool_count} tools available via {transport})
```

**Variables:**
- `{server_id}` - server identifier (e.g., "filesystem", "linear")
- `{tool_count}` - number of tools (e.g., "14", "23")
- `{transport}` - transport type (e.g., "command", "streamable_http", "sse")

**MCP Warnings:**

**Location:** `src/muxi/formation/formation.py:2376-2387`

**Current:**
```
[ WARN ] MCP server: {server_id} (authentication failed - check credentials)
[ WARN ] MCP server: {server_id} (connection failed - {error_message})
[ WARN ] MCP server: {server_id} (invalid configuration - {error_message})
[ WARN ] MCP server: {server_id} (registration failed - {error_message})
```

**Human-friendly alternatives:**
```
[ WARN ] Could not authenticate with MCP server '{server_id}' - check your credentials
[ WARN ] Could not connect to MCP server '{server_id}' - {error_message}
[ WARN ] MCP server '{server_id}' has invalid configuration - {error_message}
[ WARN ] Failed to register MCP server '{server_id}' - {error_message}
```

**MCP Info Summary (when failures occurred):**

**Location:** `src/muxi/formation/formation.py:2469`

**Current:**
```
[ INFO ] MCP initialization complete ({succeeded} succeeded, {failed} failed)
```

**Human-friendly alternative:**
```
[ INFO ] MCP initialization complete: {succeeded} server(s) connected, {failed} failed
```

---

## 6. A2A Server

**Location:** `src/muxi/formation/overlord/a2a_coordinator.py` (needs verification)

**Current:**
```
[  OK  ] A2A server ({host}:{port}, {auth_mode})
```

**Human-friendly alternative:**
```
[  OK  ] A2A server listening on {host}:{port} (authentication: {auth_mode})
```

**Variables:**
- `{host}:{port}` - server address
- `{auth_mode}` - authentication mode

---

## 7. A2A Registries (one line per registry)

**Location:** `src/muxi/formation/overlord/overlord.py:1133`

**Current:**
```
[  OK  ] A2A registry: {registry_url} (connected)
```

**Human-friendly alternative:**
```
[  OK  ] Connected to A2A registry at {registry_url}
```

**Variables:**
- `{registry_url}` - registry address (e.g., "registry.example.com:8080")

**Optional Summary (when multiple registries):**

**Location:** `src/muxi/formation/overlord/overlord.py:1140`

**Current:**
```
[ INFO ] Connected to {count} A2A registries (ready for agent discovery)
```

**Human-friendly alternative:**
```
[ INFO ] {count} A2A registries connected and ready
```

**Variables:**
- `{count}` - number of registries

---

## 8. Scheduler Service

**Location:** `src/muxi/services/scheduler/service.py:114`

**Current:**
```
[  OK  ] Scheduler service (interval={interval}, max_concurrent={max}, tz={timezone})
```

**Human-friendly alternative:**
```
[  OK  ] Background scheduler initialized (checks every {interval}, up to {max} concurrent jobs, {timezone})
```

**Variables:**
- `{interval}` - check interval (e.g., "1m", "5m")
- `{max}` - max concurrent jobs (e.g., "5")
- `{timezone}` - timezone (e.g., "UTC", "America/New_York")

---

## 9. Agents (one line per agent)

**Location:** `src/muxi/formation/initialization.py:919`

**Current:**
```
[  OK  ] Agent: {agent_name} ({role})
```

**Human-friendly alternative:**
```
[  OK  ] Loaded agent '{agent_name}' (role: {role})
```

**Variables:**
- `{agent_name}` - agent name (e.g., "IT Support", "Project Manager")
- `{role}` - agent role (e.g., "general", "specialist")

---

## 10. Formation Ready Summary

**Location:** `src/muxi/formation/formation.py:2558`

**Current:**
```
[  OK  ] Formation ready (initialized in {duration}s)
```

**Human-friendly alternative:**
```
[  OK  ] Formation initialized successfully in {duration}s
```

**Variables:**
- `{duration}` - initialization time in seconds (e.g., "2.3", "0.8")

---

## 12. Warnings

### Overlord Already Running

**Location:** `src/muxi/formation/formation.py:2480`

**Current:**
```
[ WARN ] Overlord already running (returning existing instance - use stop_overlord() to restart)
```

**Human-friendly alternative:**
```
[ WARN ] Formation is already running - returning existing instance (call stop_overlord() first to restart)
```

### Graceful Shutdown Timeout

**Location:** `src/muxi/formation/formation.py:2691`

**Current:**
```
[ WARN ] Graceful shutdown timeout (forcing termination after {timeout}s)
```

**Human-friendly alternative:**
```
[ WARN ] Shutdown taking too long - forcing termination after {timeout} seconds
```

**Variables:**
- `{timeout}` - timeout in seconds

---

## 13. Errors (with structured details)

### Configuration Not Found

**Location:** `src/muxi/formation/formation.py:487`

**Current:**
```
[ FAIL ] Formation loader

  Configuration file not found

  Common causes:
    • File path is incorrect
    • Formation directory doesn't exist
    • formation.yaml file is missing

  To fix:
    1. Check that {path} exists
    2. Verify the path in your formation.load() call
    3. Make sure formation.yaml is in the specified directory

  Config: Tried to load: {path}

  {technical_details}
```

**Human-friendly alternative:**
```
[ FAIL ] Could not load formation configuration

  Configuration file not found at: {path}

  This usually means:
    • The file path is incorrect or misspelled
    • The formation directory doesn't exist yet
    • The formation.yaml file is missing from the directory

  Try these fixes:
    1. Double-check the path: {path}
    2. Verify the path you passed to formation.load()
    3. Make sure formation.yaml exists in that directory

  Technical details:
  {technical_details}
```

**Variables:**
- `{path}` - attempted path
- `{technical_details}` - full exception traceback

### Configuration Validation Error

**Location:** `src/muxi/formation/formation.py:516`

**Current:**
```
[ FAIL ] Formation initialization

  {error_message}

  Common causes:
    • Invalid configuration
    • Missing required fields
    • Validation failed

  To fix:
    1. Check formation.yaml syntax
    2. Verify all required fields are present

  Config: Error during formation configuration loading

  {technical_details}
```

**Human-friendly alternative:**
```
[ FAIL ] Formation configuration is invalid

  {error_message}

  This usually means:
    • The YAML syntax is incorrect
    • Required fields are missing from your configuration
    • Field values don't match expected format

  Try these fixes:
    1. Check your formation.yaml for syntax errors (indentation, colons, quotes)
    2. Compare with a working example formation
    3. Make sure all required fields are present (llm, agents, etc.)

  Technical details:
  {technical_details}
```

**Variables:**
- `{error_message}` - first line of error
- `{technical_details}` - full exception

---

## Style Guidelines

1. **Component names**: Use title case (e.g., "Buffer memory", "Database manager")
2. **Details**: Use lowercase, parentheses for context (e.g., "(local mode, size=10)")
3. **Counts**: Always include units (e.g., "6 tables", "14 tools", not just "6", "14")
4. **Status indicators**: Be specific (e.g., "vector search enabled" not just "enabled")
5. **Errors**: Start with what failed, then provide causes and fixes
6. **Server IDs**: Use formation IDs/names, not full URLs or connection strings

## Review Checklist

- [ ] All messages are clear and actionable
- [ ] Technical jargon is minimized
- [ ] Error messages provide specific fixes
- [ ] Success messages show relevant details
- [ ] Consistent terminology across all messages
- [ ] No redundant information
- [ ] One line per distributed service (MCP, A2A, agent)
