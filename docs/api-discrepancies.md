# Formation API v1 - Specification vs Implementation Discrepancies

This document outlines the differences between the OpenAPI specification (`schemas/api/formation-api-v1.yaml`) and the actual API implementation discovered through comprehensive testing.

## Summary

The Formation API implementation differs from its OpenAPI specification in several key areas:
- Response envelope formats
- Object type naming conventions  
- Authentication error codes
- List endpoint response structures
- Special endpoint behaviors

## Detailed Discrepancies

### 1. Health Endpoint

**Specification Expected:**
```json
{
  "object": "health",
  "timestamp": "2024-01-01T00:00:00Z",
  "success": true,
  "error": null,
  "data": {
    "status": "healthy",
    "formation_id": "...",
    "version": "..."
  }
}
```

**Actual Implementation:**
```json
{
  "status": "healthy"
}
```

**Discrepancy:** No envelope format, returns simple JSON object.

### 2. Authentication Errors

**Specification:** Returns HTTP 401 (Unauthorized)
**Actual:** Returns HTTP 403 (Forbidden)

**Affected Scenarios:**
- Missing authentication headers
- Invalid API keys
- Wrong key type (client key for admin endpoint)

### 3. Object Type Naming

**Specification vs Actual:**
- `formation_status` → `status`
- `formation_config` → `config`
- `overlord_config` → `overlord`
- `overlord_persona` → `persona`
- `llm_settings` → `llm_settings` (matches)
- `logging_config` → `logging`
- `memory_config` → `memory`
- `async_settings` → `async`
- `scheduler_settings` → `scheduler`
- `a2a_settings` → `a2a`
- `mcp_defaults` → `mcp`

**Pattern:** Actual implementation uses simpler, shorter object names.

### 4. List Endpoints

**Specification Expected:**
```json
{
  "object": "list",
  "type": "agent",
  "data": [
    {"id": "...", "name": "...", ...}
  ]
}
```

**Actual Implementation:**
```json
{
  "object": "agent_list",
  "data": {
    "agents": [
      {"id": "...", "name": "...", ...}
    ],
    "count": 5
  }
}
```

**Affected Endpoints:**
- `/v1/agents` → `{agents: [...], count: N}`
- `/v1/secrets` → `{secrets: {...}, count: N}` (dict not array!)
- `/v1/mcp/servers` → `{servers: [...], count: N}`
- `/v1/jobs/{user_id}` → `{jobs: [...], count: N}`
- `/v1/memories/{user_id}` → `{memories: [...], count: N}`

### 5. Secrets Endpoint Special Behavior

**Specification:** Returns array of secret objects
**Actual:** Returns dictionary mapping keys to masked values

**Example:**
```json
{
  "object": "secret_list",
  "data": {
    "secrets": {
      "API_KEY": "••••••••",
      "DATABASE_URL": "••••••••"
    },
    "count": 2
  }
}
```

### 6. Config Endpoint Behavior

**Specification:** Returns full formation configuration
**Actual:** Returns resource summary with links

**Actual Response Example:**
```json
{
  "object": "config",
  "data": {
    "agents": {
      "resource": "/v1/agents",
      "total": 4
    },
    "secrets": {
      "resource": "/v1/secrets",
      "total": 10
    }
    // ... other resources
  }
}
```

## Impact Assessment

### Breaking Changes
1. **Health endpoint** - Clients expecting envelope format will fail
2. **Authentication errors** - Clients checking for 401 will miss 403 errors
3. **List endpoints** - Different data structure requires client updates
4. **Secrets format** - Dictionary instead of array is fundamentally different

### Non-Breaking Differences
1. **Object naming** - Still parseable, just different string values
2. **Config endpoint** - Different but valid data structure

## Recommendations

1. **Update OpenAPI Spec**: Align specification with actual implementation
2. **Version the API**: Consider this the v1.0 behavior and document it properly
3. **Client Libraries**: Update any generated clients to handle actual response formats
4. **Migration Guide**: If spec alignment is chosen, provide migration guide for existing clients

## Test Coverage

All discrepancies documented here are covered by the test suite in:
- `tests/api/test_get_endpoints_comprehensive.py` - Full documentation and validation
- `tests/api/test_get_endpoints_actual.py` - Validates actual behavior

Last Updated: 2025-01-31