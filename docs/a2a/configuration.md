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

### Outbound Configuration

Controls how your formation sends A2A messages to external agents.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable outbound A2A |
| `registries` | array | `[]` | Registries for agent discovery |
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