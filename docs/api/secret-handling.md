# Secret Handling in MUXI Formation API

## Overview

The MUXI Formation API implements comprehensive secret protection to ensure that sensitive information is never exposed through API responses. This document describes how secrets are handled throughout the API.

## Secret Protection Mechanisms

### 1. Placeholder Preservation

When secrets are loaded from the formation configuration using placeholder syntax (e.g., `${{ secrets.API_KEY }}`), the API tracks these placeholders and restores them in API responses instead of returning the actual secret values.

**Example:**
```yaml
# In formation.afs
llm:
  api_keys:
    openai: ${{ secrets.OPENAI_API_KEY }}
```

**API Response:**
```json
{
  "llm": {
    "api_keys": {
      "openai": "${{ secrets.OPENAI_API_KEY }}"
    }
  }
}
```

### 2. Hardcoded Secret Masking

When secrets are hardcoded directly in the configuration (not using placeholders), the API automatically detects and masks them based on:
- Known secret paths (e.g., `server.api_keys.*`, `llm.api_keys.*`)
- API key patterns (e.g., `sk-*`, `AIza*`, etc.)

**Example:**
```yaml
# In formation.afs (hardcoded - not recommended)
server:
  api_keys:
    admin_key: sk_muxi_admin_actual_key_12345
```

**API Response:**
```json
{
  "server": {
    "api_keys": {
      "admin_key": "sk_••••••••2345"
    }
  }
}
```

### 3. Masking Rules

The masking algorithm follows these rules:

1. **Placeholder Check**: Values starting with `${{` and ending with `}}` are never masked
2. **Length Check**: Values shorter than 8 characters are not masked
3. **Already Masked Check**: Values containing `•` or `***` are not re-masked
4. **Pattern-Based Masking**:
   - For keys with underscores (e.g., `sk_*`): Shows prefix up to first underscore + last 4 characters
   - For other patterns: Shows first 3 and last 3 characters

## Known Secret Paths

The following paths are automatically checked for hardcoded secrets:

### Server API Keys
- `server.api_keys.admin_key`
- `server.api_keys.client_key`

### LLM API Keys
- `llm.api_keys.openai`
- `llm.api_keys.anthropic`
- `llm.api_keys.google`
- `llm.api_keys.cohere`
- `llm.api_keys.huggingface`

### Agent Model API Keys
- `agents[*].model.api_key`

### MCP Server Environment Variables
- `mcp.servers[*].env.API_KEY`
- `mcp.servers[*].env.API_TOKEN`
- `mcp.servers[*].env.SECRET_KEY`
- `mcp.servers[*].env.ACCESS_TOKEN`
- `mcp.servers[*].env.AUTH_TOKEN`

### Other Sensitive Paths
- `overlord.api_key`
- `database.connection_string`
- `memory.database.url`
- `async.webhook_secret`
- `webhooks.secret`

## API Key Pattern Detection

The system recognizes common API key patterns:

- **OpenAI**: `sk-[a-zA-Z0-9]{20,}`, `sk-proj-[a-zA-Z0-9]{20,}`
- **Anthropic**: `sk-ant-[a-zA-Z0-9-]{40,}`
- **Google/GCP**: `AIza[a-zA-Z0-9-_]{35}`
- **Generic patterns**:
  - Stripe-like: `sk_[a-zA-Z0-9_]{20,}`
  - Hex keys: `[a-f0-9]{32,64}`
  - All caps: `[A-Z0-9]{20,40}`
- **MUXI-specific**: `sk_muxi_[a-zA-Z0-9_]+`

## Affected Endpoints

All configuration endpoints apply secret protection:

- `GET /v1/config` - Returns configuration summary (no secrets)
- `GET /v1/formation` - Returns full config with masked secrets
- `GET /v1/llm/settings` - LLM config with masked API keys
- `GET /v1/agents` - Agent list with masked model API keys
- `GET /v1/agents/{agent_id}` - Individual agent with masked API key
- `GET /v1/mcp/servers` - MCP servers with masked environment secrets
- `GET /v1/mcp/servers/{server_id}` - Individual server with masked env
- `GET /v1/overlord` - Overlord config with masked API key
- `GET /v1/async` - Async config with masked webhook secrets
- `GET /v1/a2a` - A2A config with masked service secrets

## Implementation Details

### Secret Tracking During Load

When a formation is loaded, the system:
1. Processes all `${{ secrets.* }}` placeholders
2. Tracks the original placeholder values and their paths
3. Stores this mapping in the Formation instance

### Secret Restoration in API Responses

When returning configuration through the API:
1. Makes a deep copy of the configuration
2. Restores all tracked placeholders to their original values
3. Masks any remaining hardcoded secrets
4. Returns the safe configuration

### Code Structure

The implementation consists of:
- `src/muxi/formation/config/loader.py` - Modified to track placeholders during loading
- `src/muxi/formation/server/secrets.py` - Core restoration and masking utilities
- API route handlers - Updated to use `restore_secret_placeholders()`

## Best Practices

1. **Always use placeholders** for secrets in formation configurations:
   ```yaml
   llm:
     api_keys:
       openai: ${{ secrets.OPENAI_API_KEY }}  # Good
       # openai: sk-actual-key-12345         # Bad - will be masked
   ```

2. **Use environment-specific secrets** for different deployments:
   ```yaml
   server:
     api_keys:
       admin_key: ${{ secrets.ADMIN_KEY_PROD }}
       client_key: ${{ secrets.CLIENT_KEY_PROD }}
   ```

3. **Store secrets securely** using the MUXI secrets manager or environment variables

## Security Considerations

- The masking shows partial information (prefix/suffix) to help identify keys while protecting the actual values
- Masked values cannot be reversed to obtain the original secret
- The system errs on the side of caution - if something looks like a secret, it gets masked
- Secret detection works recursively through nested configurations

## Example API Responses

### GET /v1/llm/settings
```json
{
  "data": {
    "api_keys": {
      "openai": "${{ secrets.OPENAI_API_KEY }}",     // Placeholder preserved
      "anthropic": "sk-ant-••••••••890",             // Hardcoded key masked
      "google": "${{ secrets.GEMINI_API_KEY }}"      // Placeholder preserved
    }
  }
}
```

### GET /v1/mcp/servers
```json
{
  "data": {
    "servers": [
      {
        "id": "github",
        "env": {
          "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}",  // Placeholder preserved
          "API_KEY": "ghp_••••••••xyz",                    // Hardcoded token masked
          "LOG_LEVEL": "info"                              // Non-secret unchanged
        }
      }
    ]
  }
}
```

This comprehensive secret protection ensures that the MUXI Formation API never exposes sensitive information while still providing useful configuration data for debugging and management.
