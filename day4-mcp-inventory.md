# Day 4: MCP Integration & User Credentials - Test Inventory


https://mcpservers.org/remote-mcp-servers

{
  "mcpServers": {
    "github": {
      "url": "https://api.githubcopilot.com/mcp/",
      "authorization_token": "Bearer <your GitHub PAT>"
    }
  }
}

https://mcp.linear.app/sse + oauth


This document provides a detailed inventory for Day 4 testing, which focuses on MCP (Model Context Protocol) integration and user credential management.

## 🎯 Day 4 Test Goals
- Validate tool discovery and invocation
- Test multi-server MCP management
- Implement and test user credential system
- Verify credential isolation and security

## 📋 Quick Checklist

### Infrastructure
- [ ] PostgreSQL running with credentials table
- [ ] All MCP servers ready to start
- [ ] Test formations created
- [ ] Encryption keys configured

### MCP Servers
- [ ] Filesystem MCP
- [ ] Web Search MCP
- [ ] Gmail MCP
- [ ] Database MCP
- [ ] Stock API MCP

### Test Data
- [ ] Sample OAuth tokens
- [ ] Test API keys
- [ ] Database connection strings
- [ ] Test user IDs (user1, user2, user3)

## 1. Database Setup

### PostgreSQL Requirements
```sql
-- Create test database
CREATE DATABASE muxi_test;

-- Credentials table (auto-created by system, but verify schema)
-- Should include:
-- - user_id
-- - service
-- - credential_type
-- - encrypted_credentials
-- - created_at
-- - updated_at
```

### Connection
```bash
# Test connection
psql -d muxi_test -c "SELECT 1"

# Connection string for formations
postgresql://localhost/muxi_test
```

## 2. MCP Servers Setup

### 2.1 Filesystem MCP
**Purpose**: File operations (list, read, write, create)
```bash
# Start command (example - adjust to your implementation)
python -m muxi.runtime.services.mcp.servers.filesystem --port 8001
```

**Test Operations**:
- List files in directory
- Create test.txt with content
- Read file contents
- Delete test files

### 2.2 Web Search MCP
**Purpose**: Internet search capabilities
```bash
# Start command
python -m muxi.runtime.services.mcp.servers.websearch --port 8002
```

**Required API Keys**:
- [ ] Search API key (Google/Bing/etc.)
- [ ] Weather API key for weather queries

**Test Queries**:
- "What's the current weather in New York?"
- "Search for Python tutorials"
- "Find information about AI"

### 2.3 Gmail MCP
**Purpose**: Email operations
```bash
# Start command
python -m muxi.runtime.services.mcp.servers.gmail --port 8003
```

**Required Credentials**:
- [ ] OAuth client ID and secret
- [ ] Sample OAuth tokens for test users

**Test Operations**:
- Check latest emails
- Send email to test address
- Search emails by subject

### 2.4 Database MCP
**Purpose**: Database queries
```bash
# Start command
python -m muxi.runtime.services.mcp.servers.database --port 8004
```

**Test Connections**:
- `postgresql://user1:pass@localhost/user1_db`
- `postgresql://user2:pass@localhost/user2_db`

**Test Operations**:
- "Show me my customer data"
- Database schema queries
- Data retrieval tests

### 2.5 Stock API MCP
**Purpose**: Financial data access
```bash
# Start command
python -m muxi.runtime.services.mcp.servers.stocks --port 8005
```

**Required API Keys**:
- [ ] Stock data provider API key
- [ ] Test keys for user1 and user2

**Test Queries**:
- "Get AAPL stock price"
- "Get TSLA stock price"
- Market data retrieval

## 3. Test Formations

### 3.1 formations/mcp-filesystem.yaml
```yaml
name: "mcp-filesystem-test"
agents:
  - id: "assistant"
    specialty: "general"
    model: "openai/gpt-4o-mini"
    system_message: "You are a helpful assistant with filesystem access"
mcp:
  servers:
    - name: "filesystem"
      url: "http://localhost:8001"
      description: "Filesystem operations"
memory:
  buffer: {enabled: true, size: 10}
```

### 3.2 formations/mcp-websearch.yaml
```yaml
name: "mcp-websearch-test"
agents:
  - id: "assistant"
    specialty: "general"
    model: "openai/gpt-4o-mini"
    system_message: "You are a helpful assistant with web search capabilities"
mcp:
  servers:
    - name: "websearch"
      url: "http://localhost:8002"
      description: "Web search and weather"
      api_key: "${{ secrets.SEARCH_API_KEY }}"
memory:
  buffer: {enabled: true, size: 10}
```

### 3.3 formations/multi-mcp.yaml
```yaml
name: "multi-mcp-test"
agents:
  - id: "assistant"
    specialty: "general"
    model: "openai/gpt-4o-mini"
    system_message: "You are a helpful assistant with multiple tools"
mcp:
  servers:
    - name: "filesystem"
      url: "http://localhost:8001"
    - name: "websearch"
      url: "http://localhost:8002"
memory:
  buffer: {enabled: true, size: 10}
```

### 3.4 formations/credentials.yaml
```yaml
name: "credentials-test"
agents:
  - id: "assistant"
    specialty: "general"
    model: "openai/gpt-4o-mini"
    system_message: "You are a helpful assistant with access to user services"
memory:
  buffer: {enabled: true, size: 10}
database:
  url: "postgresql://localhost/muxi_test"
```

### 3.5 formations/mcp-gmail.yaml
```yaml
name: "mcp-gmail-test"
agents:
  - id: "assistant"
    specialty: "general"
    model: "openai/gpt-4o-mini"
    system_message: "You are a helpful assistant with email access"
mcp:
  servers:
    - name: "gmail"
      url: "http://localhost:8003"
      description: "Gmail operations"
      # Credentials provided per-user at runtime
memory:
  buffer: {enabled: true, size: 10}
database:
  url: "postgresql://localhost/muxi_test"
```

## 4. Test Credentials

### 4.1 Sample OAuth Tokens (Gmail)
```json
{
  "user1": {
    "access_token": "ya29.sample_token_user1",
    "refresh_token": "1//sample_refresh_user1",
    "expires_at": "2025-12-31T23:59:59Z"
  },
  "user2": {
    "access_token": "ya29.sample_token_user2",
    "refresh_token": "1//sample_refresh_user2",
    "expires_at": "2025-12-31T23:59:59Z"
  }
}
```

### 4.2 API Keys
```json
{
  "weather_api": {
    "user1": "weather_key_user1",
    "user2": "weather_key_user2"
  },
  "stock_api": {
    "user1": "stock_key_user1",
    "user2": "stock_key_user2"
  }
}
```

### 4.3 Database Connections
```json
{
  "user1": "postgresql://user1:pass1@localhost/user1_db",
  "user2": "postgresql://user2:pass2@localhost/user2_db"
}
```

## 5. Test Execution Order

### Phase 1: Single MCP Tests (4A)
1. Start filesystem MCP server
2. Run test 4A1 (filesystem operations)
3. Stop filesystem MCP
4. Start websearch MCP server
5. Run test 4A2 (web search)
6. Stop websearch MCP

### Phase 2: Multi-MCP Tests (4B)
1. Start both filesystem and websearch MCPs
2. Run test 4B1 (coordinated operations)
3. Run test 4B2 (failure handling)
4. Stop all MCPs

### Phase 3: Credential Tests (4C)
1. Ensure PostgreSQL is running
2. Run test 4C1 (store credentials)
3. Run test 4C2 (retrieve credentials)
4. Run test 4C3 (user isolation)
5. Run test 4C4 (encryption verification)

### Phase 4: MCP + Credentials (4D)
1. Start all MCP servers
2. Run test 4D1 (Gmail with OAuth)
3. Run test 4D2 (Database with connection string)
4. Run test 4D3 (Multi-user API access)
5. Run test 4D4 (Credential auto-discovery)

## 6. Validation Commands

### Pre-test Validation
```bash
# Check PostgreSQL
psql -d muxi_test -c "\dt"  # List tables

# Test MCP connectivity (adjust ports)
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health

# Verify formations
python -m muxi.runtime.formation.validate formations/mcp-filesystem.yaml
python -m muxi.runtime.formation.validate formations/credentials.yaml
```

### During Testing
```bash
# Monitor MCP logs
tail -f mcp-filesystem.log
tail -f mcp-websearch.log

# Check database for credentials
psql -d muxi_test -c "SELECT user_id, service, credential_type FROM credentials;"
```

## 7. Common Issues & Solutions

### Issue: MCP Connection Refused
```bash
# Check if MCP server is running
ps aux | grep mcp

# Check port availability
netstat -an | grep 8001
```

### Issue: Credential Encryption Fails
```bash
# Verify master key is set
echo $MUXI_MASTER_KEY

# Check encryption module
python -c "from muxi.runtime.utils.encryption import encrypt; print('OK')"
```

### Issue: OAuth Token Invalid
- Ensure test tokens are properly formatted
- Check token expiration dates
- Verify OAuth client configuration

## 8. Test Data Cleanup

After testing:
```sql
-- Clean up test credentials
DELETE FROM credentials WHERE user_id IN ('user1', 'user2', 'user3');

-- Clean up test files
rm -f test.txt
rm -f search_results.txt
```

## 9. Success Metrics

### Expected Results:
- **Test Group 4A**: 2/2 tests pass (single MCP operations)
- **Test Group 4B**: 2/2 tests pass (multi-MCP coordination)
- **Test Group 4C**: 4/4 tests pass (credential management)
- **Test Group 4D**: 4/4 tests pass (MCP with credentials)
- **Total**: 12/12 tests pass

### Performance Targets:
- MCP tool discovery: < 100ms
- Tool invocation: < 500ms
- Credential retrieval: < 50ms
- Multi-MCP coordination: < 2s

---

**Ready for Day 4?** Work through this checklist to ensure all MCP servers and credentials are properly configured before running the tests!
