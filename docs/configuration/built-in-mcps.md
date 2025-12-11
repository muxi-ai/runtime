# Built-in MCP Configuration Guide

MUXI Runtime includes built-in MCP (Model Context Protocol) servers that provide additional capabilities to agents without requiring external setup. This guide explains how to configure and manage these built-in MCPs.

## Overview

Built-in MCPs are:
- Pre-installed with MUXI Runtime
- Automatically registered based on configuration
- Secure and sandboxed
- Zero-configuration by default

## Configuration Options

### Simple Mode (Default)

Enable or disable all built-in MCPs with a boolean value:

```yaml
# formation.afs (or .yaml)

# Enable all built-in MCPs (default behavior)
runtime:
  built_in_mcps: true

# Disable all built-in MCPs
runtime:
  built_in_mcps: false
```

### MCP Service Configuration

Configure advanced MCP behavior including intelligent tool chaining:

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

  # External MCP servers
  servers:
    - id: "github"
      url: "https://api.github.com/mcp"
      active: true    # Set to false to disable loading this server
      auth:
        token: "${{ user.credentials.github }}"
    - id: "disabled-server"
      url: "https://example.com/mcp"
      active: false   # This server will be ignored during formation load
```

### Granular Mode

Control individual MCPs by specifying a list:

```yaml
# formation.afs (or .yaml)

# Enable only specific built-in MCPs
runtime:
  built_in_mcps:
    - file-generation
    # - web-search      # Coming soon?
    # - database        # Coming soon?
```

### Default Behavior

If the `runtime` section or `built_in_mcps` field is not specified, all built-in MCPs are enabled by default:

```yaml
# No runtime section = all built-in MCPs enabled
agents:
  - id: my-agent
    name: My Agent
```

## Available Built-in MCPs

### file-generation

Enables agents to generate files including charts, documents, spreadsheets, and images.

**Capabilities:**
- Data visualization (matplotlib, plotly, seaborn)
- Document creation (Word, PDF, Markdown)
- Spreadsheet generation (Excel, CSV)
- Image creation (PNG, JPEG, QR codes)
- Presentation creation (PowerPoint)

**Configuration:**
```yaml
runtime:
  built_in_mcps:
    - file-generation
```

**Dependencies:**
```bash
pip install muxi[file-generation]
```

### web-search (Coming Soon)

Will enable agents to search the web and retrieve information.

### database (Coming Soon)

Will provide database query and manipulation capabilities.

## System Prompt Integration

When built-in MCPs are enabled, their usage instructions are automatically added to the agent's system prompt. This means agents immediately know how to use these tools without additional configuration.

Example of automatic prompt augmentation:

```
# Base system prompt
You are a helpful assistant.

# Automatically added when file-generation is enabled
## Built-in Tools

### File Generation

When users request file generation (charts, documents, spreadsheets, images, presentations), you have access to the `generate_file` tool...
```

## Security Considerations

Built-in MCPs include security features:

1. **Sandboxed Execution**: Run in isolated subprocesses
2. **Resource Limits**: Timeout and memory constraints
3. **Whitelisted Operations**: Only approved actions allowed
4. **Output Isolation**: Restricted to designated directories
5. **No Network Access**: Cannot make external requests

## Performance Impact

Built-in MCPs have minimal performance impact:
- Loaded on-demand
- Separate process execution
- Automatic cleanup
- Resource monitoring

## Troubleshooting

### MCPs Not Available

Check that:
1. MCPs are enabled in configuration
2. Required dependencies are installed
3. No errors during Formation startup

### Checking MCP Status

```python
# List registered MCP servers
formation = Formation()
await formation.load("formation.afs")
overlord = await formation.start_overlord()

# Check available MCPs
mcp_servers = await overlord.list_mcp_servers()
print(mcp_servers)
```

## Server Management

### Active/Inactive Servers

Use the `active` field to control which MCP servers are loaded:

```yaml
# formation.afs (or .yaml)
mcp:
  servers:
    - id: "production-server"
      url: "https://api.example.com/mcp"
      active: true     # This server will be loaded and used

    - id: "development-server"
      url: "https://dev.example.com/mcp"
      active: false    # This server will be ignored completely

    - id: "legacy-server"
      url: "https://legacy.example.com/mcp"
      # active defaults to true if not specified
```

**Benefits:**
- **Memory efficiency**: Inactive servers are not loaded into memory
- **Environment-specific configs**: Enable different servers per environment
- **Gradual migration**: Disable old servers without removing configuration

### Tool Chaining

Agent tool chaining allows intelligent error recovery and is controlled by the MCP execution settings:

```yaml
mcp:
  max_tool_iterations: 10      # Maximum execution loops
  max_tool_calls: 50           # Maximum total tool calls
  max_repeated_errors: 3       # Stop after N repeated errors
```

**How it works:**
1. Agent calls an MCP tool
2. If the tool fails, agent analyzes the error
3. Agent attempts corrective actions (e.g., create missing directories)
4. Agent retries the original operation
5. Process repeats until success or max iterations reached

**Note:** Tool chaining is always enabled and helps agents complete complex tasks without manual intervention.

### Viewing System Prompts

To see the augmented system prompt:

```python
# Get the complete system message
system_message = overlord._create_overlord_system_message()
print(system_message)
```

## Migration Guide

### From External MCP Servers

If you're currently using external MCP servers that duplicate built-in functionality:

1. Remove external MCP configuration
2. Enable corresponding built-in MCP
3. Update any custom prompts (built-in prompts are automatic)

Example migration:

```yaml
# Before: External file generation MCP
mcp:
  servers:
    - id: external-file-gen
      type: command
      command: python /path/to/file_gen_server.py

# After: Built-in file generation
runtime:
  built_in_mcps:
    - file-generation
# Remove the external MCP configuration
```

### Backwards Compatibility

The configuration is fully backwards compatible:
- Existing formations without `runtime` section work unchanged
- Default behavior (all MCPs enabled) matches expected functionality
- Granular control is opt-in

## Best Practices

1. **Start with Defaults**: Use default configuration unless you have specific requirements
2. **Gradual Adoption**: Test built-in MCPs in development before production
3. **Monitor Usage**: Use observability to track MCP utilization
4. **Document Overrides**: If disabling MCPs, document the reason
5. **Keep Dependencies Updated**: Regularly update optional dependencies

## Configuration Examples

### Development Environment

Enable all MCPs for maximum capability:

```yaml
runtime:
  built_in_mcps: true  # All capabilities available
```

### Production Environment

Enable only required MCPs:

```yaml
runtime:
  built_in_mcps:
    - file-generation  # Only what's needed
```

### Security-Conscious Setup

Disable all built-in MCPs and use only vetted external MCPs:

```yaml
runtime:
  built_in_mcps: false  # No built-in code execution

mcp:
  servers:
    - id: approved-tool
      type: http
      endpoint: https://internal.api/mcp
      auth:
        type: bearer
        token: ${{ secrets.MCP_TOKEN }}
```

### Mixed Configuration

Combine built-in and external MCPs:

```yaml
runtime:
  built_in_mcps:
    - file-generation  # Use built-in file generation

mcp:
  servers:
    - id: custom-database  # Add custom database MCP
      type: command
      command: python /opt/mcp/database_server.py
```

## Future Enhancements

Planned improvements:
- Additional built-in MCPs (web-search, database, etc.)
- Per-agent MCP overrides
- MCP versioning and updates
- Performance metrics per MCP
- Custom built-in MCP development framework
