# A2A Configuration Guide

This guide explains how to configure A2A (Agent-to-Agent) communication in your MUXI formation.

## Basic Configuration

### Minimal A2A Setup

```yaml
# formation.yaml
a2a:
  enabled: true  # Enable A2A functionality
```

This enables internal A2A communication between agents in the same formation.

### Full A2A Configuration

```yaml
a2a:
  enabled: true
  
  # Inbound configuration - for receiving A2A messages
  inbound:
    enabled: true
    host: "0.0.0.0"      # Default: 0.0.0.0
    port: 8181           # Default: 8181
    registries:          # External registries to register with
      - "https://registry.example.com"
      - "https://backup-registry.example.com"
    trusted_endpoints:   # Optional: IP/hostname whitelist
      - "trusted.partner.com"
      - "192.168.1.0/24"
    auth:               # Authentication for incoming requests
      type: "bearer"
      token: "${{ secrets.A2A_INBOUND_TOKEN }}"
  
  # Outbound configuration - for sending A2A messages  
  outbound:
    enabled: true
    startup_policy: "lenient"      # Registry connection policy: lenient, strict, retry
    retry_timeout_seconds: 30      # Retry duration for 'retry' policy
    registries:         # Registries to discover agents from
      - "https://registry.example.com"
    default_retry_attempts: 3      # Default: 3
    default_timeout_seconds: 30    # Default: 30
    services:           # Service-specific auth configurations
      - service_id: "partner-api.com:8181"
        auth:
          type: "bearer"
          token: "${{ secrets.PARTNER_TOKEN }}"
      - service_id: "localhost:8080"
        auth:
          type: "api_key"
          key: "${{ secrets.LOCAL_API_KEY }}"
```

## Configuration Options

### Global A2A Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable/disable entire A2A system |
| `filtering` | object | see below | Intelligent agent filtering configuration |

### Inbound Configuration

Controls how your formation receives A2A messages from external sources.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable inbound A2A server |
| `host` | string | `"0.0.0.0"` | Host to bind server to |
| `port` | integer | `8181` | Port for A2A server |
| `registries` | array | `[]` | External registries to register with |
| `trusted_endpoints` | array | `[]` | Whitelist of trusted IPs/hostnames |
| `auth` | object | none | Authentication configuration |

#### Authentication Configuration

```yaml
auth:
  type: "bearer"    # Options: bearer, api_key, basic, none
  token: "..."      # For bearer auth
  key: "..."        # For api_key auth
  username: "..."   # For basic auth
  password: "..."   # For basic auth
  header: "..."     # Custom header name for api_key
```

### Intelligent Agent Filtering

Controls how agents are filtered for task planning when there are many available agents.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable intelligent agent filtering |
| `threshold` | integer | `50` | Number of agents that triggers filtering |
| `always_include_threshold` | float | `0.8` | Relevance score (0-1) for automatic inclusion |
| `min_relevance_score` | float | `0.3` | Minimum relevance score for consideration |
| `cache_ttl` | integer | `1800` | Cache duration in seconds (30 minutes default) |

#### How Filtering Works

1. **Threshold Check**: Filtering only activates when available agents exceed the `threshold`
2. **Task Analysis**: Uses AI to analyze the task and identify required capabilities
3. **Scoring**: Each agent is scored based on capability matches
4. **Selection**: Agents scoring above thresholds are included
5. **Caching**: Results are cached to avoid repeated analysis

#### Example Configuration

```yaml
a2a:
  enabled: true
  
  # Intelligent filtering for large agent pools
  filtering:
    enabled: true
    threshold: 10           # Filter when >10 agents available
    always_include_threshold: 0.8  # Always include if score >= 0.8
    min_relevance_score: 0.3       # Consider if score >= 0.3
    cache_ttl: 3600               # Cache for 1 hour
```

### Outbound Configuration

Controls how your formation sends A2A messages to external agents.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable outbound A2A |
| `registries` | array | `[]` | Registries for agent discovery |
| `startup_policy` | string | `"lenient"` | Registry connection policy on startup |
| `retry_timeout_seconds` | integer | `30` | Retry duration for 'retry' policy |
| `default_retry_attempts` | integer | `3` | Default retry attempts |
| `default_timeout_seconds` | integer | `30` | Default timeout in seconds |
| `services` | array | `[]` | Service-specific configurations |

#### Service Configuration

```yaml
services:
  - service_id: "api.example.com:8181"  # Required
    auth:                               # Required
      type: "bearer"
      token: "${{ secrets.TOKEN }}"
    retry_attempts: 5                   # Optional override
    timeout_seconds: 60                 # Optional override
```

## Intelligent Agent Filtering

### Overview

When formations have access to many agents (internal and external), intelligent filtering helps select the most relevant agents for each task. This improves performance and reduces costs by avoiding unnecessary agent invocations.

### When to Use Filtering

Enable filtering when:
- Your formation has access to >10 agents
- You connect to external registries with many agents
- You want to optimize agent selection for specific tasks
- You need to reduce latency in agent discovery

### Configuration Example

```yaml
a2a:
  enabled: true
  
  filtering:
    enabled: true                    # Turn on intelligent filtering
    threshold: 10                    # Activate when >10 agents available
    always_include_threshold: 0.8    # High-confidence agents always included
    min_relevance_score: 0.3         # Minimum score to consider an agent
    cache_ttl: 1800                  # Cache results for 30 minutes
```

### How It Works

1. **Agent Discovery**: System discovers all available agents (internal + external)
2. **Threshold Check**: If agent count > `threshold`, filtering activates
3. **Task Analysis**: AI analyzes the task to identify required capabilities
4. **Scoring**: Each agent is scored based on:
   - Capability matches with task requirements
   - Tool availability
   - Agent type (internal agents get slight preference)
5. **Filtering**: Agents are filtered based on scores:
   - Score >= `always_include_threshold`: Always included
   - Score >= `min_relevance_score`: Included if relevant
   - Score < `min_relevance_score`: Filtered out
6. **Caching**: Results cached to avoid repeated analysis

### Agent-Level Control

Individual agents can opt out of filtering:

```yaml
# In agent configuration
agents:
  - id: "critical-agent"
    allow_filtering: false  # Never filter this agent
    # ... other config
```

### Performance Benefits

With intelligent filtering enabled:
- **Reduced Latency**: Fewer agents to evaluate
- **Lower Costs**: Fewer LLM calls for agent selection
- **Better Accuracy**: Most relevant agents prioritized
- **Cache Efficiency**: ~97% reduction in repeated analysis

### Example Scenarios

#### Scenario 1: Large Enterprise Formation

```yaml
# 100+ agents available from multiple registries
a2a:
  filtering:
    enabled: true
    threshold: 20        # Filter when >20 agents
    always_include_threshold: 0.9  # Very strict inclusion
    min_relevance_score: 0.5       # Higher minimum score
    cache_ttl: 7200               # Cache for 2 hours
```

#### Scenario 2: Development Environment

```yaml
# Testing with many mock agents
a2a:
  filtering:
    enabled: true
    threshold: 5         # Low threshold for testing
    always_include_threshold: 0.7  # More permissive
    min_relevance_score: 0.2       # Include more agents
    cache_ttl: 300                # Short cache for development
```

#### Scenario 3: Production API Gateway

```yaml
# Gateway with access to all company services
a2a:
  filtering:
    enabled: true
    threshold: 50        # Many services available
    always_include_threshold: 0.85
    min_relevance_score: 0.4
    cache_ttl: 3600     # Standard 1-hour cache
```

### Monitoring and Debugging

To see filtering in action:

```python
# The system logs filtering decisions
[A2A] Planning filter initialized with threshold: 10
[A2A] Filtering applied: 10 agents reduced to 3
[A2A] Cache hit for task hash: abc123
```

### Best Practices

1. **Start Conservative**: Begin with default values and adjust based on results
2. **Monitor Cache Hits**: High cache hit rate indicates good TTL settings
3. **Adjust Thresholds**: Lower `min_relevance_score` if too many agents filtered
4. **Test with Real Tasks**: Filtering effectiveness depends on task clarity
5. **Exclude Critical Agents**: Use `allow_filtering: false` for essential agents

## Common Configurations

### 1. Internal Only (Default)

For formations that only communicate internally:

```yaml
a2a:
  enabled: true
  # No inbound or outbound configuration needed
```

### 2. Public API Formation

Formation that provides services to others:

```yaml
a2a:
  enabled: true
  
  inbound:
    enabled: true
    port: 8181
    auth:
      type: "bearer"
      token: "${{ secrets.PUBLIC_API_TOKEN }}"
    # No registries - direct connection only
```

### 3. Client Formation

Formation that only consumes external services:

```yaml
a2a:
  enabled: true
  
  outbound:
    enabled: true
    registries:
      - "https://registry.example.com"
    services:
      - service_id: "api.service.com"
        auth:
          type: "api_key"
          key: "${{ secrets.SERVICE_API_KEY }}"
```

### 4. Full Participant

Formation that both provides and consumes services:

```yaml
a2a:
  enabled: true
  
  inbound:
    enabled: true
    port: 8181
    registries:
      - "https://registry.example.com"
    auth:
      type: "bearer"
      token: "${{ secrets.MY_A2A_TOKEN }}"
  
  outbound:
    enabled: true
    registries:
      - "https://registry.example.com"
    services:
      - service_id: "partner.com"
        auth:
          type: "bearer"
          token: "${{ secrets.PARTNER_TOKEN }}"
```

### 5. Development Setup

Simplified configuration for development:

```yaml
a2a:
  enabled: true
  
  inbound:
    enabled: true
    port: 8181
    auth:
      type: "none"  # No auth for development
  
  outbound:
    enabled: true
    # No auth needed for local development
```

## Registry Configuration

### Startup Policy

The `startup_policy` configuration determines how your formation handles registry connectivity during startup. This is crucial for distributed systems where registry availability can impact operations.

#### Available Policies

| Policy | Behavior | Use Case |
|--------|----------|----------|
| `lenient` (default) | Continue startup regardless of registry health | Development, optional services |
| `strict` | Fail startup if registries are unreachable | Production, critical dependencies |
| `retry` | Attempt connections for configured duration | Temporary network issues |

#### Configuration Examples

**Lenient Policy (Default)**
```yaml
a2a:
  outbound:
    startup_policy: "lenient"  # Continue even if registry is down
    registries:
      - "https://registry.example.com"
```

**Strict Policy**
```yaml
a2a:
  outbound:
    startup_policy: "strict"   # Fail fast if registry unreachable
    registries:
      - "https://critical-registry.com"
```

**Retry Policy**
```yaml
a2a:
  outbound:
    startup_policy: "retry"     # Retry for 60 seconds
    retry_timeout_seconds: 60   # Duration to retry
    registries:
      - "https://registry.example.com"
```

#### Extended Registry Configuration

For fine-grained control, you can configure individual registries:

```yaml
a2a:
  outbound:
    startup_policy: "strict"
    registries:
      # Simple format (backward compatible)
      - "https://registry1.com"
      
      # Extended format with per-registry settings
      - url: "https://critical-registry.com"
        required: true                    # Must be reachable
        health_check_timeout_seconds: 10  # Custom timeout
        
      - url: "https://optional-registry.com"
        required: false                   # Can be down
        health_check_timeout_seconds: 5
```

#### Policy Behavior Details

**Lenient Policy**
- Logs warnings for unreachable registries
- Formation starts normally
- Registry connections attempted in background
- Best for: Development, non-critical external dependencies

**Strict Policy**
- Performs health checks on all registries
- Fails immediately if any registry is unreachable
- Shows user-friendly error message with resolution steps
- Best for: Production systems with critical dependencies

**Retry Policy**
- Attempts connections for `retry_timeout_seconds`
- If all registries become reachable, startup continues
- After timeout, applies `required` flags from extended config
- Best for: Handling temporary network issues

#### Error Messages

When using strict policy with unreachable registries, you'll see:

```
============================================================
⚠️  FORMATION STARTUP FAILED
============================================================

Policy: STRICT
Required registries are unreachable:

  ❌ https://registry.example.com

To resolve this issue, you can:
  1. Start the registry server(s) listed above
  2. Change startup_policy to 'lenient' in formation.yaml
  3. Remove the unreachable registries from configuration

============================================================
```

### Using Multiple Registries

```yaml
# Registries are tried in order
registries:
  - "https://primary-registry.com"    # Primary
  - "https://backup-registry.com"     # Failover
  - "https://tertiary-registry.com"   # Last resort
```

### Local Registry

For testing with local registry:

```yaml
registries:
  - "http://localhost:9090"  # Local registry
```

## Security Considerations

### 1. Use Environment Variables

Always use secrets for sensitive data:

```yaml
auth:
  token: "${{ secrets.A2A_TOKEN }}"      # Good
  # token: "hardcoded-token-value"      # Bad!
```

### 2. Enable Authentication

For production, always enable authentication:

```yaml
inbound:
  auth:
    type: "bearer"  # or api_key, basic
    token: "${{ secrets.SECURE_TOKEN }}"
```

### 3. Use HTTPS for Registries

```yaml
registries:
  - "https://registry.example.com"  # Secure
  # - "http://registry.example.com" # Avoid in production
```

### 4. Restrict Trusted Endpoints

Limit who can connect:

```yaml
inbound:
  trusted_endpoints:
    - "trusted-partner.com"
    - "10.0.0.0/8"  # Internal network only
```

## Advanced Configuration

### Custom Headers

For services requiring custom headers:

```yaml
outbound:
  services:
    - service_id: "custom-api.com"
      auth:
        type: "custom"
        headers:
          X-Client-ID: "${{ secrets.CLIENT_ID }}"
          X-Client-Secret: "${{ secrets.CLIENT_SECRET }}"
```

### Per-Service Timeouts

Override defaults for specific services:

```yaml
outbound:
  default_timeout_seconds: 30  # Default for all
  services:
    - service_id: "slow-service.com"
      timeout_seconds: 120     # Override for slow service
      retry_attempts: 5        # More retries too
```

### Load Balancing

When multiple agents provide same capability:

```yaml
# The system automatically load balances between
# discovered agents with the same capabilities
outbound:
  registries:
    - "https://registry-1.com"  # May have agent-a
    - "https://registry-2.com"  # May also have agent-a
```

## Validation

### Check Configuration

The formation validates A2A configuration on startup:

```bash
# Validation happens automatically
python -m muxi run formation.yaml

# Errors will be shown:
# ConfigurationError: A2A inbound auth requires 'token' field
```

### Common Validation Errors

1. **Missing required fields**
   ```
   Error: A2A inbound auth requires 'type' field
   ```

2. **Invalid port number**
   ```
   Error: A2A inbound port must be between 1024 and 65535
   ```

3. **Invalid auth type**
   ```
   Error: A2A auth type 'custom' not supported for inbound
   ```

## Migration from Old Format

### Old Format (deprecated)
```yaml
a2a:
  inbound:
    mode: "bearer"
    shared_key: "${{ secrets.KEY }}"
```

### New Format
```yaml
a2a:
  inbound:
    auth:
      type: "bearer"
      token: "${{ secrets.KEY }}"
```

The system supports both formats for backward compatibility.

## Environment-Specific Configuration

### Using Formation Overlays

```yaml
# base-formation.yaml
a2a:
  enabled: true
  inbound:
    enabled: true
    port: 8181

# production-overlay.yaml
a2a:
  inbound:
    auth:
      type: "bearer"
      token: "${{ secrets.PROD_A2A_TOKEN }}"
    registries:
      - "https://prod-registry.com"

# development-overlay.yaml
a2a:
  inbound:
    auth:
      type: "none"  # No auth for dev
    registries:
      - "http://localhost:9090"
```

### Runtime Selection

```bash
# Production
muxi run base-formation.yaml --overlay production-overlay.yaml

# Development
muxi run base-formation.yaml --overlay development-overlay.yaml
```