# Test Group 8E: Credential Handling Modes

## Overview

Test Group 8E validates the credential handling modes (Redirect and Dynamic) and their behavior with different authentication types. These tests ensure proper security, user experience, and configuration compliance.

## Test Scenarios

### 8E1: Redirect Mode Tests

#### 8E1a: API Key in Redirect Mode
- **Scenario**: User tries to add API key credential with redirect mode enabled
- **Expected**: System redirects to external UI, never accepts inline
- **Flow**:
  1. Request service requiring API key
  2. System asks which account
  3. User says "add new"
  4. System provides redirect URL
  5. User confirms completion
  6. System proceeds with new credential

#### 8E1b: Bearer Token in Redirect Mode  
- **Scenario**: User tries to add GitHub PAT with redirect mode enabled
- **Expected**: System redirects even though it's a simple PAT
- **Flow**:
  1. Request GitHub repositories
  2. System asks which account
  3. User says "none of these"
  4. System provides redirect URL (no inline option)
  5. User confirms completion
  6. System proceeds with new credential

#### 8E1c: OAuth in Redirect Mode
- **Scenario**: User tries to add Google account with redirect mode
- **Expected**: System redirects to OAuth flow
- **Flow**:
  1. Request Gmail access
  2. System asks which account
  3. User says "add my work account"
  4. System provides OAuth redirect URL
  5. User confirms completion
  6. System proceeds with OAuth token

### 8E2: Dynamic Mode Tests - Inline Allowed

#### 8E2a: API Key in Dynamic Mode
- **Scenario**: User adds simple API key (Brave Search)
- **Expected**: System accepts inline
- **Flow**:
  1. Request web search
  2. System asks for API key directly
  3. User provides key: "BSA_abc123..."
  4. System accepts and uses key
  5. Verify key is redacted from logs

#### 8E2b: PAT with allow_inline Hint
- **Scenario**: User adds GitHub PAT (with allow_inline: true)
- **Expected**: System accepts inline
- **MCP Config**: `auth: {type: "bearer", allow_inline: true}`
- **Flow**:
  1. Request GitHub repositories
  2. System asks which account
  3. User says "add new"
  4. System asks for PAT directly
  5. User provides: "ghp_abc123..."
  6. System accepts and uses token

#### 8E2c: Basic Auth in Dynamic Mode
- **Scenario**: User adds username/password
- **Expected**: System accepts inline with security warning
- **Flow**:
  1. Request database access
  2. System asks for credentials
  3. System shows security warning
  4. User provides username/password
  5. System accepts credentials

### 8E3: Dynamic Mode Tests - Redirect Required

#### 8E3a: OAuth Bearer without Hint
- **Scenario**: User adds Google account (no allow_inline)
- **Expected**: System redirects to OAuth
- **MCP Config**: `auth: {type: "bearer"}` (no allow_inline)
- **Flow**:
  1. Request Google Drive access
  2. System asks which account
  3. User says "add new"
  4. System provides OAuth URL (no inline option)
  5. User confirms OAuth completion
  6. System proceeds with OAuth token

#### 8E3b: Bearer with allow_inline: false
- **Scenario**: User adds Slack (explicitly no inline)
- **Expected**: System redirects to OAuth
- **MCP Config**: `auth: {type: "bearer", allow_inline: false}`
- **Flow**:
  1. Request Slack access
  2. System asks which account
  3. User says "add new"
  4. System provides OAuth URL
  5. User confirms completion
  6. System proceeds with OAuth token

### 8E4: Credential Management Operations

#### 8E4a: List Credentials
- **Scenario**: User lists configured credentials
- **Expected**: Shows credential names without values
- **Test both modes**: Should work identically
- **Flow**:
  1. User: "What GitHub accounts do I have?"
  2. System lists accounts with metadata
  3. Verify no credential values shown

#### 8E4b: Remove Credential
- **Scenario**: User removes a credential
- **Expected**: Confirmation and removal
- **Test both modes**: Should work identically
- **Flow**:
  1. User: "Remove my personal GitHub"
  2. System asks for confirmation
  3. User confirms
  4. System removes credential
  5. Verify credential is gone

#### 8E4c: Edit Credential (Not Supported)
- **Scenario**: User tries to edit credential
- **Expected**: System explains edit not supported
- **Test both modes**: Should work identically
- **Flow**:
  1. User: "Update my GitHub token"
  2. System explains must remove and re-add
  3. System offers to remove existing
  4. User proceeds or cancels

### 8E5: Security and Edge Cases

#### 8E5a: Credential Redaction
- **Scenario**: Verify credentials are redacted from logs
- **Expected**: No credentials in logs/debug output
- **Test**:
  1. Enable debug logging
  2. Add credential inline (dynamic mode)
  3. Verify credential not in logs
  4. Verify "[REDACTED]" appears instead

#### 8E5b: Context Switching During Credential Flow
- **Scenario**: User changes topic during credential clarification
- **Expected**: Credential flow cancelled, new request processed
- **Flow**:
  1. Start credential addition
  2. User asks unrelated question
  3. System cancels credential flow
  4. System processes new request

#### 8E5c: Invalid Credential Format
- **Scenario**: User provides malformed credential
- **Expected**: System detects and asks again
- **Flow**:
  1. System asks for GitHub PAT
  2. User provides invalid format
  3. System explains format requirement
  4. User provides correct format

#### 8E5d: Missing Configuration
- **Scenario**: No credential_handling mode specified
- **Expected**: Defaults to safe "redirect" mode
- **Test**: Load formation without config, verify redirect behavior

## Test Data Requirements

### MCP Service Configurations

#### github-mcp.yaml (PAT supported)
```yaml
schema: "1.0.0"
id: "github"
type: "http"
auth:
  type: "bearer"
  allow_inline: true  # PAT can be entered directly
```

#### google-mcp.yaml (OAuth only)
```yaml
schema: "1.0.0"
id: "google-drive"
type: "http"
auth:
  type: "bearer"
  # No allow_inline = OAuth required
```

#### brave-mcp.yaml (Simple API key)
```yaml
schema: "1.0.0"
id: "brave-search"
type: "http"
auth:
  type: "api_key"
  header: "X-API-Key"
```

#### postgres-mcp.yaml (Basic auth)
```yaml
schema: "1.0.0"
id: "postgres"
type: "http"
auth:
  type: "basic"
```

### Formation Configurations

#### formation-redirect.yaml
```yaml
clarification:
  credential_handling: "redirect"
  credential_redirect_message: |
    To add and manage services, please visit:
    https://test.example.com/credentials
```

#### formation-dynamic.yaml
```yaml
clarification:
  credential_handling: "dynamic"
  # No redirect message needed for inline cases
```

## Success Criteria

### Functional Requirements
- ✅ Redirect mode always redirects (never inline)
- ✅ Dynamic mode correctly identifies inline vs redirect
- ✅ API keys accepted inline in dynamic mode
- ✅ OAuth always redirects
- ✅ PAT handling respects allow_inline hint
- ✅ Basic auth works with security warning
- ✅ List/Remove operations work in both modes
- ✅ Edit operation properly rejected

### Security Requirements
- ✅ No credentials in logs/debug output
- ✅ No credentials in LLM context after initial input
- ✅ No credentials in error messages
- ✅ Security warnings shown for basic auth
- ✅ Credentials properly isolated per user

### User Experience
- ✅ Clear messages for each credential type
- ✅ Consistent behavior within each mode
- ✅ Helpful error messages for invalid input
- ✅ Smooth flow for both inline and redirect paths

## Test Implementation Notes

1. **Mock External UI**: Tests should mock the external credential UI response
2. **Credential Storage**: Verify credentials stored correctly in database
3. **Multiple Formations**: Test with different formation configs
4. **State Management**: Verify clarification state properly managed
5. **Timeout Handling**: Use 2-minute timeouts like 8B tests

## Migration from 8C1

The current 8C1 credential rejection test should be moved to 8E1b as it tests redirect behavior. The 8C group should focus on complex multi-step clarifications that don't involve credentials.