# A2A Authentication Guide

This guide covers authentication mechanisms for A2A communication in MUXI Runtime.

## Overview

A2A authentication secures communication between formations. While agents within the same formation trust each other, external A2A communication requires proper authentication.

## Authentication Types

### 1. Bearer Token
Most common method using bearer tokens in the Authorization header.

**Configuration**:
```yaml
# Inbound (receiving messages)
a2a:
  inbound:
    auth:
      type: "bearer"
      token: "${{ secrets.A2A_BEARER_TOKEN }}"

# Outbound (sending messages)
a2a:
  outbound:
    services:
      - service_id: "partner-formation"
        auth:
          type: "bearer"
          token: "${{ secrets.PARTNER_BEARER_TOKEN }}"
```

**HTTP Header**:
```
Authorization: Bearer <token>
```

### 2. API Key
Uses a custom header for API key authentication.

**Configuration**:
```yaml
# Inbound
a2a:
  inbound:
    auth:
      type: "api_key"
      key: "${{ secrets.A2A_API_KEY }}"
      header: "X-API-Key"  # Optional, defaults to X-API-Key

# Outbound
a2a:
  outbound:
    services:
      - service_id: "api.example.com"
        auth:
          type: "api_key"
          key: "${{ secrets.EXTERNAL_API_KEY }}"
          header: "X-Custom-Key"  # Custom header name
```

**HTTP Header**:
```
X-API-Key: <key>
# or
X-Custom-Key: <key>
```

### 3. Basic Authentication
Traditional username/password authentication.

**Configuration**:
```yaml
# Inbound
a2a:
  inbound:
    auth:
      type: "basic"
      username: "${{ secrets.A2A_USERNAME }}"
      password: "${{ secrets.A2A_PASSWORD }}"

# Outbound
a2a:
  outbound:
    services:
      - service_id: "legacy-system"
        auth:
          type: "basic"
          username: "${{ secrets.LEGACY_USER }}"
          password: "${{ secrets.LEGACY_PASS }}"
```

**HTTP Header**:
```
Authorization: Basic <base64(username:password)>
```

### 4. Custom Headers
For systems requiring custom authentication headers.

**Configuration**:
```yaml
# Outbound only (inbound not supported for custom)
a2a:
  outbound:
    services:
      - service_id: "custom-api"
        auth:
          type: "custom"
          headers:
            X-Client-ID: "${{ secrets.CLIENT_ID }}"
            X-Client-Secret: "${{ secrets.CLIENT_SECRET }}"
            X-Timestamp: "dynamic"  # Special handling
```

**HTTP Headers**:
```
X-Client-ID: <client_id>
X-Client-Secret: <secret>
X-Timestamp: <generated_timestamp>
```

### 5. No Authentication
For public or development environments.

**Configuration**:
```yaml
a2a:
  inbound:
    auth:
      type: "none"  # Or omit auth section entirely
```

## Service ID Matching

The `service_id` in outbound configuration determines which authentication to use for external requests.

### Matching Precedence

1. **Exact Match**: `agent-id@hostname:port`
   ```yaml
   service_id: "calendar-agent@api.example.com:8181"
   ```

2. **Host and Port**: `hostname:port`
   ```yaml
   service_id: "api.example.com:8181"
   ```

3. **Host Only**: `hostname`
   ```yaml
   service_id: "api.example.com"
   ```

4. **Port Only**: `port` (for localhost)
   ```yaml
   service_id: "8181"
   ```

### Examples

```yaml
outbound:
  services:
    # Most specific - only for calendar agent at this location
    - service_id: "calendar-agent@partner.com:8181"
      auth:
        type: "bearer"
        token: "${{ secrets.CALENDAR_TOKEN }}"
    
    # All agents at partner.com on port 8181
    - service_id: "partner.com:8181"
      auth:
        type: "api_key"
        key: "${{ secrets.PARTNER_KEY }}"
    
    # All services at partner.com (any port)
    - service_id: "partner.com"
      auth:
        type: "basic"
        username: "${{ secrets.PARTNER_USER }}"
        password: "${{ secrets.PARTNER_PASS }}"
    
    # All localhost services on port 8080
    - service_id: "8080"
      auth:
        type: "bearer"
        token: "${{ secrets.LOCAL_TOKEN }}"
```

## Authentication Flow

### Inbound Authentication

```python
# src/muxi/services/a2a/auth/inbound.py

class A2AInboundAuthenticator:
    async def authenticate_request(
        self,
        request: Request,
        authorization: Optional[str],
        x_api_key: Optional[str],
        x_signature: Optional[str],
        x_timestamp: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Returns: (authenticated, client_id, error_message)
        """
```

**Flow**:
1. Extract headers from request
2. Determine authentication type
3. Validate credentials
4. Return authentication result

### Outbound Authentication

```python
# src/muxi/services/a2a/auth/outbound.py

class A2AOutboundAuthenticator:
    def add_auth_headers(
        self,
        headers: Dict[str, str],
        auth_config: Dict[str, Any]
    ) -> Dict[str, str]:
        """Add authentication headers based on config"""
```

**Flow**:
1. Determine target service from URL
2. Find matching auth configuration
3. Add appropriate headers
4. Send authenticated request

## Security Best Practices

### 1. Use Secrets Management
Never hardcode credentials:
```yaml
# Good
auth:
  token: "${{ secrets.A2A_TOKEN }}"

# Bad
auth:
  token: "hardcoded-secret-token"
```

### 2. Rotate Credentials
Implement regular rotation:
- Use versioned secrets
- Support multiple valid tokens during rotation
- Monitor usage of old tokens

### 3. Use HTTPS
Always use HTTPS for external A2A:
```yaml
registries:
  - "https://registry.example.com"  # Good
  - "http://registry.example.com"   # Avoid
```

### 4. Implement Rate Limiting
Protect against abuse:
```python
# Custom rate limiting in formation
rate_limiter = RateLimiter(
    max_requests=100,
    time_window=60  # seconds
)
```

### 5. Audit Logging
Log authentication events:
```python
observability.observe(
    event_type="a2a.auth.success",
    data={
        "client_id": client_id,
        "service_id": service_id,
        "ip": request.client.host
    }
)
```

## Troubleshooting Authentication

### Common Issues

#### 1. 401 Unauthorized
**Symptoms**: Request rejected with 401 status

**Causes**:
- Missing authentication headers
- Invalid token/credentials
- Expired token

**Debug**:
```bash
# Test with curl
curl -H "Authorization: Bearer $TOKEN" \
     https://formation.example.com/agents
```

#### 2. 403 Forbidden
**Symptoms**: Request rejected with 403 status

**Causes**:
- Wrong authentication type
- Valid credentials but insufficient permissions

**Debug**:
```python
# Check logs for auth type mismatch
"Authentication failed: Expected bearer auth, got api_key"
```

#### 3. Token Not Found
**Symptoms**: Service can't find auth configuration

**Causes**:
- No matching service_id
- Typo in configuration

**Debug**:
```yaml
# Check service_id matches exactly
services:
  - service_id: "api.example.com:8181"  # Must match URL
```

### Debug Mode

Enable debug logging for authentication:

```yaml
logging:
  streams:
    - transport: "stdout"
      level: "debug"
      events:
        - "a2a.auth.*"
```

## Advanced Topics

### Multi-Tenant Authentication

Support multiple tenants with different credentials:

```yaml
outbound:
  services:
    # Tenant A
    - service_id: "tenant-a.example.com"
      auth:
        type: "bearer"
        token: "${{ secrets.TENANT_A_TOKEN }}"
    
    # Tenant B
    - service_id: "tenant-b.example.com"
      auth:
        type: "bearer"
        token: "${{ secrets.TENANT_B_TOKEN }}"
```

### Dynamic Token Generation

For tokens that need to be generated:

```python
class CustomAuthenticator:
    def generate_token(self, service_id: str) -> str:
        # Generate JWT or other dynamic token
        payload = {
            "sub": self.formation_id,
            "aud": service_id,
            "exp": time.time() + 3600
        }
        return jwt.encode(payload, self.secret_key)
```

### Mutual Authentication

For bidirectional trust:

1. Configure inbound auth for your formation
2. Configure outbound auth for partner formation
3. Exchange credentials securely
4. Both sides validate on each request

### Authentication Proxies

When behind a corporate proxy:

```yaml
outbound:
  proxy:
    url: "https://proxy.company.com:8080"
    auth:
      type: "basic"
      username: "${{ secrets.PROXY_USER }}"
      password: "${{ secrets.PROXY_PASS }}"
```

## Migration Guide

### From Old Format to New Format

**Old** (pre-August 2025):
```yaml
inbound:
  mode: "bearer"
  shared_key: "${{ secrets.TOKEN }}"
```

**New**:
```yaml
inbound:
  auth:
    type: "bearer"
    token: "${{ secrets.TOKEN }}"
```

The system automatically handles both formats for backward compatibility.