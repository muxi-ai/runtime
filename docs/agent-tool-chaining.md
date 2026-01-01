# Agent Tool Chaining

Agent Tool Chaining is an intelligent error recovery mechanism that allows agents to make multiple sequential tool calls to resolve failures and complete tasks. When an MCP tool returns an error, the agent automatically analyzes the error and attempts to resolve it by making additional tool calls.

## Overview

Tool chaining enables agents to be more autonomous and intelligent when working with MCP tools. Instead of simply passing errors back to the user, agents can:

1. **Analyze tool errors** intelligently to understand what went wrong
2. **Make corrective tool calls** to resolve the underlying issue
3. **Retry the original operation** after fixing the problem
4. **Chain multiple tools together** to complete complex workflows

## How It Works

### Chain Lifecycle

1. **Initial Tool Call**: Agent attempts to execute an MCP tool
2. **Error Analysis**: If the tool fails, agent analyzes the error message
3. **Corrective Action**: Agent determines if the error can be resolved with additional tool calls
4. **Chain Execution**: Agent makes corrective tool calls and retries the original operation
5. **Completion**: Process continues until success or maximum iterations reached

### Chain Identification

Each tool chain is assigned a unique identifier with the format `chn_` + nanoId (e.g., `chn_V1StGXR8_Z5jdHi6B-myT`). This identifier:

- Groups related tool operations together
- Enables observability tracking across the entire chain
- Helps debug complex multi-step workflows

### Safety Mechanisms

Tool chaining includes several safety mechanisms to prevent infinite loops:

- **Maximum Iterations**: Default limit of 10 iterations per chain (`max_tool_iterations`)
- **Total Call Limit**: Maximum 50 total tool calls across all iterations (`max_tool_calls`)
- **Error Pattern Detection**: Stops after 3 repeated identical errors (`max_repeated_errors`)
- **Timeout Protection**: Per-tool timeout and total operation timeout
- **Graceful Degradation**: Falls back to error reporting if resolution fails

## Configuration

Tool chaining is configured in the formation's MCP section:

```yaml
# formation.afs (or .yaml)
mcp:
  # Connection/retry settings (for transient failures)
  default_retry_attempts: 3           # Retry attempts for server connection issues
  default_timeout_seconds: 30         # Timeout per individual tool call

  # Tool execution settings (for intelligent chaining)
  max_tool_iterations: 10             # Max loops of (execute → analyze → decide)
  max_tool_calls: 50                  # Max total individual tool calls
  max_repeated_errors: 3              # Number of same errors before stopping

  # Timeout settings
  max_timeout_in_seconds: 300         # Total timeout for entire operation
  max_tool_timeout_in_seconds: 30     # Timeout per individual tool call
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `default_retry_attempts` | `3` | Retry attempts for transient server connection failures |
| `default_timeout_seconds` | `30` | Default timeout for MCP server requests |
| `max_tool_iterations` | `10` | Maximum execution loops for intelligent problem solving |
| `max_tool_calls` | `50` | Maximum total tool calls across all iterations |
| `max_repeated_errors` | `3` | Number of similar errors before stopping |
| `max_timeout_in_seconds` | `300` | Total timeout for entire operation chain |
| `max_tool_timeout_in_seconds` | `30` | Timeout per individual tool call |

### Server Filtering

Use the `active` field to control which MCP servers are loaded:

```yaml
mcp:
  servers:
    - id: "github"
      url: "https://api.github.com/mcp"
      active: true    # This server will be loaded and used
    - id: "legacy-server"
      url: "https://old.example.com/mcp"
      active: false   # This server will be completely ignored
```

Servers with `active: false` are filtered out during formation loading, reducing memory usage and improving performance.

## Common Use Cases

### 1. File System Operations

**Scenario**: Creating a file in a non-existent directory

```
Initial Call: write_file("/path/to/new/dir/file.txt", content)
Error: "Directory does not exist"
Corrective Action: create_directory("/path/to/new/dir")
Retry: write_file("/path/to/new/dir/file.txt", content)
Result: Success
```

### 2. API Resource Creation

**Scenario**: Creating a resource that depends on another resource

```
Initial Call: create_issue(project_id="unknown-project", title="Bug")
Error: "Project not found"
Corrective Action: create_project(name="unknown-project")
Retry: create_issue(project_id="new-project-id", title="Bug")
Result: Success
```

### 3. Credential Resolution

**Scenario**: Tool requires authentication that needs to be set up

```
Initial Call: list_repositories()
Error: "Authentication required"
Corrective Action: setup_authentication(token="user-provided-token")
Retry: list_repositories()
Result: Success
```

## Implementation Details

### Agent Intelligence

The agent's tool chaining logic is implemented in `src/muxi/formation/agents/agent.py`. The agent:

1. **Parses error messages** to understand the failure type
2. **Identifies corrective actions** based on error patterns
3. **Constructs appropriate tool calls** to resolve the issue
4. **Manages the chain state** and iteration counting

### Error Analysis Patterns

The agent recognizes common error patterns:

- **File/Directory Not Found**: Creates missing directories or files
- **Resource Not Found**: Attempts to create missing resources
- **Authentication Errors**: Triggers credential setup flows
- **Permission Errors**: Attempts to adjust permissions when possible
- **Dependency Errors**: Resolves missing dependencies

### Observability Events

Tool chaining emits several observability events:

- **`AGENT_TOOL_CHAIN_STARTED`**: When a new chain begins
- **`AGENT_TOOL_CHAIN_ITERATION`**: For each iteration in the chain
- **`AGENT_TOOL_CHAIN_COMPLETED`**: When a chain completes successfully
- **`AGENT_TOOL_CHAIN_FAILED`**: When a chain exhausts all attempts

Each event includes the `chain_id` for correlation.

## Best Practices

### 1. MCP Server Design

When building MCP servers, provide detailed error messages that agents can parse:

```python
# Good: Specific, actionable error
return {"error": "Directory '/path/to/dir' does not exist"}

# Bad: Generic, unhelpful error
return {"error": "Operation failed"}
```

### 2. Formation Configuration

Configure appropriate limits based on your use case:

```yaml
# For simple workflows
mcp:
  max_tool_iterations: 3        # Fewer iterations for simple tasks
  max_tool_calls: 10           # Lower total tool call limit

# For complex workflows
mcp:
  max_tool_iterations: 10      # More iterations for complex recovery
  max_tool_calls: 50           # Higher limit for complex chains
  max_timeout_in_seconds: 600  # Longer total timeout
```

### 3. Error Handling

Design your applications to handle both successful chains and failed chains gracefully:

```python
# The agent will attempt chaining automatically
response = await overlord.run_agent("Create file in new directory")

# Check if the operation succeeded
if response.status == "success":
    print("File created successfully")
elif "chain_failed" in response.metadata:
    print("Could not resolve the issue automatically")
```

## Debugging Tool Chains

### Observability

Use the observability system to track chain execution:

```python
# Enable chain debugging
observability.set_level(observability.EventLevel.DEBUG)

# Look for chain events
events = observability.get_events(event_type="AGENT_TOOL_CHAIN_*")
```

### Formation Configuration

Temporarily adjust chain limits for debugging:

```yaml
mcp:
  max_tool_iterations: 1       # Minimal chaining to see raw errors
  max_repeated_errors: 1       # Stop immediately on repeated errors
```

### Agent Logs

The agent logs detailed information about chain decisions:

```
[Agent] Starting tool chain chn_V1StGXR8_Z5jdHi6B-myT for tool 'write_file'
[Agent] Chain iteration 1: Analyzing error "Directory does not exist"
[Agent] Chain iteration 1: Attempting corrective action with tool 'create_directory'
[Agent] Chain iteration 2: Retrying original tool 'write_file'
[Agent] Tool chain chn_V1StGXR8_Z5jdHi6B-myT completed successfully
```

## Limitations

### Current Limitations

1. **Static Error Patterns**: The agent currently uses predefined error patterns
2. **Limited Context**: Chaining decisions are based on the immediate error, not broader context
3. **No Learning**: The agent doesn't learn from successful chains to improve future decisions

### Future Enhancements

1. **Dynamic Pattern Learning**: Train the agent to recognize new error patterns
2. **Context-Aware Chaining**: Consider conversation history and user intent
3. **Cross-Chain Learning**: Share successful patterns across different agents
4. **User Preference Learning**: Adapt chaining behavior based on user feedback

## API Reference

### Chain Events

```python
# Chain started
{
    "event_type": "AGENT_TOOL_CHAIN_STARTED",
    "data": {
        "chain_id": "chn_V1StGXR8_Z5jdHi6B-myT",
        "initial_tool": "write_file",
        "initial_args": {...},
        "max_iterations": 3
    }
}

# Chain iteration
{
    "event_type": "AGENT_TOOL_CHAIN_ITERATION",
    "data": {
        "chain_id": "chn_V1StGXR8_Z5jdHi6B-myT",
        "iteration": 1,
        "corrective_tool": "create_directory",
        "corrective_args": {...},
        "reason": "Directory does not exist"
    }
}

# Chain completed
{
    "event_type": "AGENT_TOOL_CHAIN_COMPLETED",
    "data": {
        "chain_id": "chn_V1StGXR8_Z5jdHi6B-myT",
        "total_iterations": 2,
        "final_result": {...}
    }
}
```

### Configuration Schema

```yaml
mcp:
  # Connection/retry settings
  default_retry_attempts: int          # Server connection retries (default: 3)
  default_timeout_seconds: int         # Default timeout per request (default: 30)

  # Tool execution settings (controls chaining behavior)
  max_tool_iterations: int             # Max execution loops (default: 10)
  max_tool_calls: int                  # Max total tool calls (default: 50)
  max_repeated_errors: int             # Stop after N repeated errors (default: 3)

  # Timeout settings
  max_timeout_in_seconds: int          # Total operation timeout (default: 300)
  max_tool_timeout_in_seconds: int     # Per-tool-call timeout (default: 30)
```

## Related Documentation

- [MCP Integration Guide](mcp/README.md) - General MCP server integration
- [Agent Collaboration](agent-collaboration.md) - Multi-agent coordination
- [Observability](observability.md) - Monitoring and debugging
- [Formation Configuration](../schemas/formation/README.md) - Formation YAML structure
