# PRD: A2A Extended Authentication Types Support

**Document Version**: 1.0
**Created**: August 5, 2025
**Status**: Future Implementation
**Prerequisites**: A2A SDK Authentication Migration (Phases 1-2) completed

## Executive Summary

This PRD outlines the implementation of extended authentication types for A2A communication, specifically HMAC signature validation, OAuth 2.0, mTLS (Mutual TLS), and OpenID Connect. These authentication methods are part of the A2A protocol specification but require more complex implementations than the basic auth types (API Key, Bearer, Basic).

## Context

During the A2A SDK Authentication Migration, we identified that the A2A protocol supports multiple authentication types beyond the basic ones (API Key, Bearer, Basic). However, implementing these advanced authentication methods requires:

1. **HMAC**: Signature generation/validation, timestamp verification, and replay attack prevention
2. **OAuth 2.0**: Full OAuth flow implementation including token refresh, scope management, and authorization server integration
3. **mTLS**: Certificate management infrastructure, SSL context handling, and PKI integration
4. **OpenID Connect**: JWT validation, JWKS endpoint integration, and identity provider configuration

Given the early stage of A2A adoption and the complexity of these flows, we've deferred this implementation to focus on core authentication stability first.

## Business Value

### Benefits
- **Enterprise Integration**: Many enterprise systems require OAuth/mTLS for third-party integrations
- **Enhanced Security**: mTLS provides the highest level of security for A2A communication
- **Federated Identity**: OpenID Connect enables single sign-on across formations
- **Compliance**: Some industries require specific authentication methods for regulatory compliance

### Use Cases
1. **HMAC**: Secure API access with signature verification, webhook endpoints
2. **OAuth 2.0**: Integration with enterprise API gateways, third-party services
3. **mTLS**: High-security environments, financial services, healthcare
4. **OpenID Connect**: Multi-tenant deployments, federated formations

## Technical Requirements

### 1. HMAC Support

#### Configuration Schema
```yaml
a2a:
  outbound:
    services:
      - service_id: "webhook-service"
        auth:
          type: "hmac"
          secret: "${{ secrets.HMAC_SECRET }}"
          algorithm: "sha256"  # or sha512
          header_format: "X-Signature"
          include_timestamp: true

  inbound:
    mode: "hmac"
    secrets:
      - client_id: "client1"
        secret: "${{ secrets.CLIENT1_HMAC_SECRET }}"
    timestamp_tolerance: 300  # seconds
    replay_prevention: true
```

#### Implementation Requirements
- Signature generation for outbound requests
- Signature validation for inbound requests
- Timestamp validation to prevent replay attacks
- Support for multiple hashing algorithms (SHA256, SHA512)
- Configurable signature header names
- Request body canonicalization

### 2. OAuth 2.0 Support

#### Configuration Schema
```yaml
a2a:
  outbound:
    services:
      - service_id: "oauth-service"
        auth:
          type: "oauth"
          client_id: "${{ secrets.OAUTH_CLIENT_ID }}"
          client_secret: "${{ secrets.OAUTH_CLIENT_SECRET }}"
          token_url: "https://auth.example.com/oauth/token"
          scope: "a2a:read a2a:write"
          grant_type: "client_credentials"  # or "authorization_code"
```

#### Implementation Requirements
- Token acquisition and caching
- Automatic token refresh before expiry
- Support for multiple OAuth grant types
- Scope validation and management
- Error handling for token revocation

### 2. mTLS Support

#### Configuration Schema
```yaml
a2a:
  outbound:
    services:
      - service_id: "secure-service"
        auth:
          type: "mtls"
          cert_path: "${{ secrets.CLIENT_CERT_PATH }}"
          key_path: "${{ secrets.CLIENT_KEY_PATH }}"
          ca_path: "${{ secrets.CA_CERT_PATH }}"
          verify_hostname: true

  inbound:
    mode: "mtls"
    ca_path: "${{ secrets.CA_CERT_PATH }}"
    require_client_cert: true
    verify_depth: 2
```

#### Implementation Requirements
- SSL context creation and management
- Certificate validation chain
- Certificate revocation list (CRL) support
- Client certificate extraction and validation
- Hostname verification options

### 3. OpenID Connect Support

#### Configuration Schema
```yaml
a2a:
  inbound:
    mode: "openid"
    issuer: "https://auth.example.com"
    audience: "formation-api"
    jwks_url: "https://auth.example.com/.well-known/jwks.json"
    allowed_algorithms: ["RS256", "RS384"]
    clock_skew_seconds: 30
```

#### Implementation Requirements
- JWT token validation
- JWKS endpoint caching and rotation
- Issuer verification
- Audience validation
- Claims extraction and mapping
- Token expiry handling

## Technical Design

### Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                 A2A Extended Auth Layer                │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐  │
│  │   OAuth     │  │    mTLS     │  │     OpenID     │  │
│  │  Handler    │  │   Handler   │  │    Handler     │  │
│  └──────┬──────┘  └───────┬─────┘  └────────┬───────┘  │
│         │                 │                 │          │
│         └─────────────────┴─────────────────┘          │
│                           │                            │
│                    ┌──────▼──────┐                     │
│                    │  A2A SDK    │                     │
│                    │  Security   │                     │
│                    │  Schemes    │                     │
│                    └─────────────┘                     │
└────────────────────────────────────────────────────────┘
```

### Component Design

#### OAuth Handler
- Manages OAuth client credentials
- Handles token lifecycle (acquisition, refresh, revocation)
- Implements token caching with TTL
- Supports multiple grant types
- Integrates with secrets manager for credentials

#### mTLS Handler
- Creates and manages SSL contexts
- Loads and validates certificates
- Implements certificate rotation support
- Handles certificate chain validation
- Provides connection pooling for performance

#### OpenID Handler
- Validates JWT tokens
- Manages JWKS cache
- Implements token introspection
- Handles clock skew
- Extracts and maps claims to A2A context

## Implementation Plan

### Phase A: OAuth 2.0 Implementation (2 weeks)
1. Design OAuth token management system
2. Implement client credentials grant
3. Add token caching and refresh logic
4. Create OAuth configuration validation
5. Add comprehensive OAuth tests

### Phase B: mTLS Implementation (2 weeks)
1. Design certificate management system
2. Implement SSL context creation
3. Add certificate validation logic
4. Create mTLS server support
5. Add certificate rotation support

### Phase C: OpenID Connect Implementation (1 week)
1. Implement JWT validation
2. Add JWKS endpoint support
3. Create claims mapping system
4. Add issuer/audience validation
5. Implement token introspection

### Phase D: Integration & Testing (1 week)
1. Integration with existing A2A system
2. End-to-end testing of all auth flows
3. Performance testing
4. Security audit
5. Documentation

## Dependencies

### External Dependencies
- A2A SDK v0.3.0+ with full security scheme support
- PyJWT or similar for JWT handling
- cryptography library for certificate operations
- httpx or aiohttp for OAuth token requests

### Internal Dependencies
- Completed A2A SDK Authentication Migration (Phases 1-2)
- Secrets Manager support for certificate/credential storage
- Formation schema updates

## Success Criteria

1. **OAuth 2.0**
   - Successfully acquire and use OAuth tokens
   - Automatic token refresh works correctly
   - Support for at least 2 grant types
   - Token caching reduces auth server load by 90%

2. **mTLS**
   - Bidirectional certificate validation works
   - Certificate rotation without downtime
   - Performance impact < 10ms per request
   - Support for multiple CA chains

3. **OpenID Connect**
   - JWT validation < 5ms per request
   - JWKS caching works correctly
   - Support for major OIDC providers
   - Claims mapping configurable

## Risks & Mitigations

### High Risks
1. **Certificate Management Complexity**
   - Risk: Certificate expiry causing outages
   - Mitigation: Automated rotation, monitoring, alerts

2. **OAuth Token Expiry**
   - Risk: Failed requests due to expired tokens
   - Mitigation: Proactive refresh, retry logic

### Medium Risks
1. **Performance Impact**
   - Risk: Authentication overhead affecting latency
   - Mitigation: Caching, connection pooling, async operations

2. **Configuration Complexity**
   - Risk: Misconfiguration causing auth failures
   - Mitigation: Validation tools, clear documentation

## Future Considerations

1. **SAML Support**: Some enterprises may require SAML
2. **Custom Auth**: Pluggable authentication providers
3. **Multi-factor**: Support for MFA in A2A scenarios
4. **Zero Trust**: Integration with zero trust architectures

## Conclusion

Extended authentication types are essential for A2A protocol completeness and enterprise adoption. However, given the complexity and current A2A maturity level, deferring this implementation allows us to focus on core functionality and stability first.

When A2A adoption increases and enterprise integration requirements emerge, this PRD provides a clear path for implementing these advanced authentication methods.

---

**Next Steps When Ready to Implement:**
1. Review and update this PRD based on A2A protocol evolution
2. Assess current A2A adoption and enterprise requirements
3. Allocate 6-week development timeline
4. Coordinate with security team for certificate infrastructure
5. Plan phased rollout with pilot customers
