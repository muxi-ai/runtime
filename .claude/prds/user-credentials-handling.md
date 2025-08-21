---
name: user-credentials-handling
description: Secure credential handling modes for MUXI Runtime with enterprise and developer options
status: backlog
created: 2025-08-20T22:01:11Z
---

# PRD: user-credentials-handling

## Executive Summary

This feature introduces two credential handling modes for the MUXI Runtime: **Redirect Mode** for enterprise security compliance and **Dynamic Mode** for developer-friendly workflows. The system intelligently manages how users provide credentials for MCP services, balancing security requirements with usability. Redirect Mode ensures credentials never touch the chat interface, while Dynamic Mode allows simple tokens inline but redirects complex authentication flows like OAuth.

## Problem Statement

The current MUXI Runtime accepts credentials directly in chat, creating significant security and usability challenges:

**Security Risks:**
- Credentials exposed in chat history, logs, and LLM context
- No guarantee of proper redaction from debug output
- Potential for credential leakage through error messages
- Non-compliance with enterprise security policies

**Usability Issues:**
- OAuth flows cannot be completed in chat
- JSON credentials and certificates are impractical to paste
- Users expect full CRUD operations if we accept credentials in chat
- No standardized approach for different credential types

**Why Now:**
- Enterprise customers require SOC2/HIPAA compliance
- Increasing adoption in production environments
- Security audits flagging credential handling as critical issue
- Developer feedback requesting smoother credential workflows

## User Stories

### Enterprise Security Administrator
**As an** enterprise security administrator
**I want** credentials to never appear in chat logs
**So that** we maintain compliance with our security policies
**Acceptance Criteria:**
- Redirect mode can be enforced via configuration
- All credential operations go through external UI
- Complete audit trail of credential access
- Support for SSO and MFA integration

### Developer Using MUXI Locally
**As a** developer testing locally
**I want** to quickly add API keys without leaving the chat
**So that** I can maintain my development flow
**Acceptance Criteria:**
- Simple API keys accepted inline in dynamic mode
- Clear feedback when credentials are accepted
- Automatic redaction from logs
- Security warning displayed for awareness

### DevOps Engineer
**As a** DevOps engineer
**I want** OAuth flows to work seamlessly
**So that** I can connect services requiring OAuth authentication
**Acceptance Criteria:**
- System detects OAuth requirements and redirects
- Clear instructions for OAuth completion
- Smooth return to chat after OAuth flow
- Token refresh handled automatically

### End User
**As an** end user
**I want** to manage my connected services easily
**So that** I can control which services have access
**Acceptance Criteria:**
- List all connected services
- Remove credentials when needed
- Clear messaging about credential usage
- No ability to view stored credentials

## Requirements

### Functional Requirements

**Configuration System:**
- Top-level `user_credentials` configuration in formation YAML
- Support `mode` selection: "redirect" or "dynamic"
- Optional `encryption_key` (defaults to formation_id if not specified)
- Customizable `redirect_message` per formation
- Default to redirect mode for security
- Per-service configuration via `accept_inline` hint

**Redirect Mode:**
- Never accept credentials in chat
- Always redirect to configured URL
- Support custom messages per formation
- Handle return flow after external credential addition

**Dynamic Mode:**
- Detect credential type from MCP service metadata
- Accept simple tokens (API keys, PATs) inline
- Redirect OAuth and complex credentials
- Show security warnings for inline credentials

**Credential Management:**
- List credentials (names only, no values)
- Remove credentials with confirmation
- No edit capability (must remove and re-add)
- Credential isolation per user

**Security Features:**
- Auto-redaction from all logs
- Encryption in buffer memory
- Exclusion from LLM context after input
- Session-only storage for inline credentials

### Non-Functional Requirements

**Performance:**
- Credential detection < 100ms
- Inline acceptance < 500ms
- List/remove operations < 1 second
- No performance impact on non-credential flows

**Security:**
- AES-256 encryption for stored credentials
- Zero credentials in logs or debug output
- Compliance with SOC2 Type 2 requirements
- Support for enterprise SSO integration

**Scalability:**
- Support 10,000+ users
- 50+ credentials per user
- Concurrent credential operations
- Stateless credential detection logic

**Reliability:**
- 99.9% uptime for credential operations
- Graceful fallback if external UI unavailable
- Automatic retry for transient failures
- Clear error messages for credential issues

## Success Criteria

**Security Metrics:**
- 0 credentials leaked in logs (measured via automated scanning)
- 100% of credentials encrypted at rest
- 0 security audit findings related to credential handling

**Usability Metrics:**
- < 30 seconds to add any credential type
- < 5% of users need support for credential operations
- > 90% success rate for first-time credential addition

**Adoption Metrics:**
- 50% of enterprise customers adopt redirect mode within 3 months
- 80% of developers use dynamic mode in development
- < 10% of users request missing credential features

**Performance Metrics:**
- P95 latency < 500ms for credential operations
- 0 timeout errors for credential flows
- < 0.1% error rate for credential management

## Constraints & Assumptions

**Technical Constraints:**
- Must maintain backward compatibility with existing MCP services
- Cannot modify MCP protocol specification
- Limited to authentication types supported by MCP
- Must work with existing buffer memory system

**Assumptions:**
- External credential UI will be provided by implementers
- Users have access to create credentials externally
- MCP services correctly declare their auth types
- Network connectivity available for redirect flows

**Resource Constraints:**
- 2 engineers for 4-week implementation
- Must reuse existing clarification system
- Limited to current database schema
- No additional infrastructure requirements

## Technical Implementation

**Formation YAML Configuration:**
```yaml
# Top-level configuration (not under clarification)
user_credentials:
  encryption_key: "your-encryption-key"  # Optional - defaults to formation_id
  mode: "redirect"  # or "dynamic"
  redirect_message: |
    For security compliance, credentials must be managed through:
    https://secure.enterprise.com/credentials
```

**Encryption Approach:**
- Zero-configuration: Uses formation_id as default encryption key
- Per-user isolation: Combines encryption_key (or formation_id) + user_id
- Uses PBKDF2 key derivation with Fernet encryption
- Credentials stored encrypted in existing `credentials` table (JSONB field)
- No key files to manage - keys derived deterministically

**Database:**
- Uses existing `credentials` table - no migration needed
- Table already has user_id, service, credentials (JSONB) fields
- Encryption happens at repository layer, not database level

## Out of Scope

- Credential rotation automation
- Credential expiry detection and notifications
- Team credential sharing
- Credential backup and restore
- Custom authentication providers
- Biometric authentication
- Hardware security module (HSM) integration
- Credential usage analytics
- Rate limiting per credential
- Cost tracking for API usage

## Dependencies

**Internal Dependencies:**
- UnifiedClarificationSystem for credential flow integration
- Buffer memory system for state management
- MCP service registry for auth type detection
- Database credentials table for storage

**External Dependencies:**
- External credential management UI (customer-provided)
- OAuth provider endpoints
- SSO identity providers (for enterprise)
- MCP service authentication endpoints

**Technical Dependencies:**
- Python cryptography library for encryption
- Database with JSON field support
- Redis/memory cache for session storage
- HTTPS for secure redirect flows

## Risk Mitigation

**Security Risks:**
- Risk: Credentials leaked through logs
- Mitigation: Automated scanning and redaction

**Usability Risks:**
- Risk: Users confused by redirect flow
- Mitigation: Clear messaging and documentation

**Technical Risks:**
- Risk: External UI unavailable
- Mitigation: Graceful degradation with clear errors

**Adoption Risks:**
- Risk: Enterprises don't trust the implementation
- Mitigation: Security audit and compliance certification

## Timeline

**Phase 1 - Core Implementation (Week 1-2):**
- Configuration schema
- Redirect mode implementation
- Basic credential detection

**Phase 2 - Dynamic Mode (Week 3):**
- Auth type detection logic
- Inline acceptance for simple tokens
- Security warnings and redaction

**Phase 3 - Management & Polish (Week 4):**
- List/remove operations
- Documentation and examples
- Security audit preparation

## Appendix

### Configuration Examples

**Enterprise Configuration:**
```yaml
clarification:
  credential_handling: "redirect"
  credential_redirect_message: |
    For security compliance, credentials must be managed through:
    https://secure.enterprise.com/credentials
```

**Developer Configuration:**
```yaml
clarification:
  credential_handling: "dynamic"
```

### Dynamic Mode Decision Logic Example

```python
def determine_credential_flow(mcp_service, mode):
    """
    Determine how to handle credential request.

    Returns:
        "inline" - Accept credential in chat
        "redirect" - Redirect to external UI
    """
    if mode == "redirect":
        return "redirect"  # Always redirect in redirect mode

    # Dynamic mode logic
    auth = mcp_service.auth
    if not auth or auth.type == "none":
        return None  # No credentials needed

    # Check explicit hint first
    if "accept_inline" in auth:
        return "inline" if auth["accept_inline"] else "redirect"

    # Default behavior by type
    if auth.type == "api_key":
        return "inline"  # Simple API keys
    elif auth.type == "basic":
        return "inline"  # Username/password (with security warning)
    elif auth.type == "bearer":
        return "redirect"  # Default OAuth assumption
    else:
        return "redirect"  # Unknown = safer to redirect
```

### Supported Authentication Types

| Type | Inline (Dynamic) | Example Services |
|------|-----------------|------------------|
| api_key | Yes | OpenAI, Brave Search |
| basic | Yes (with warning) | PostgreSQL, MySQL |
| bearer (PAT) | Yes (with hint) | GitHub, GitLab |
| bearer (OAuth) | No | Google, Slack |
| none | N/A | Public services |
