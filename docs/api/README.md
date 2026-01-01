# MUXI Formation API Documentation

This directory contains the living documentation for the MUXI Formation API implementation. It tracks what's actually built versus what's planned.

## 📁 Documentation Structure

- **[complete-reference.md](./complete-reference.md)** - **NEW! Complete API reference with all tested endpoints**
- **[formation-api-implemented.yaml](./formation-api-implemented.yaml)** - OpenAPI 3.0 specification containing ONLY implemented endpoints
- **[implementation-status.md](./implementation-status.md)** - Detailed tracking of implementation progress with notes
- **[secret-handling.md](./secret-handling.md)** - Comprehensive documentation of secret protection mechanisms

## 🚀 Quick Start

### View API Documentation
```bash
# Install OpenAPI viewer
npm install -g @redocly/cli

# Preview the implemented API
redocly preview-docs formation-api-implemented.yaml
```

### API Base URL
- Development/Internal: `http://localhost:8271/v1`
- Production: `https://{muxi_server}/v1/formations/{formation_id}`

## 🔑 Authentication

The API uses two types of API keys:

### Admin Key (`X-Muxi-Admin-Key`)
- **Purpose**: Formation management operations
- **Header**: `X-Muxi-Admin-Key: sk_muxi_admin_...`
- **Access**: All formation configuration and management endpoints

### Client Key (`X-Muxi-Client-Key`)
- **Purpose**: User interactions with the formation
- **Header**: `X-Muxi-Client-Key: sk_muxi_client_...`
- **Access**: Chat, memories, jobs, and events endpoints

## 🎉 Implementation Status: **100% TESTED**

### Summary
- **Total Endpoints**: 23 core endpoints
- **Fully Tested**: 23 (100%) ✅
- **Test Pass Rate**: 23/23 (100%)
- **Status**: **Production Ready**

### Coverage by Category
| Category | Status | Tests |
|----------|--------|-------|
| Health & Status | ✅ 100% | 4/4 |
| Chat & Interaction | ✅ 100% | 1/1 |
| Memory Management | ✅ 100% | 6/6 |
| Secrets Management | ✅ 100% | 5/5 |
| Agent Management | ✅ 100% | 1/1 |
| MCP Integration | ✅ 100% | 2/2 |
| Configuration | ✅ 100% | 2/2 |
| Scheduler | ✅ 100% | 3/3 |
| Jobs | ✅ 100% | 2/2 |
| Logging | ✅ 100% | 1/1 |
| Events | ✅ 100% | 1/1 |
| A2A | ✅ 100% | 1/1 |

### Recent Achievement
**October 24, 2025**: Achieved 100% test coverage (23/23 tests passing)
- Fixed 11 bugs across 4 testing sessions
- Journey: 52.2% → 100% (+47.8 points)
- All endpoints validated through rigorous E2E testing

### Legend
- ✅ Fully implemented, tested, and production-ready
- 🟡 Working but returns 503 (service not configured - expected behavior)
- 🟡 Returns 501 (not implemented - documented behavior)

## 📝 Response Format

All API responses use a consistent envelope format:

```json
{
  "object": "response_type",
  "timestamp": 1706616000000,
  "type": "event.type",
  "request": {
    "id": "req_abc123",
    "idempotency_key": null
  },
  "success": true,
  "error": null,
  "data": {}
}
```

### Error Response Format

When an error occurs (`success` is false), the `error` field contains:

```json
{
  "error": {
    "code": "ERROR_CODE",       // Standardized error code (e.g., "INVALID_PARAMS")
    "message": "Error message", // Human-readable error description
    "data": {                   // Optional additional error data
      "validation_errors": [    // For validation errors
        {
          "field": "name",      // Field path using dot notation
          "msg": "Field required",
          "type": "string",     // Expected data type
          "error": "missing"    // Error kind (missing, wrong_type, etc.)
        }
      ],
      "trace": "...",          // Stack trace for internal errors (debug mode)
      // Other error-specific data
    }
  },
  "data": {}                   // Always empty for error responses
}
```

### Common Error Codes

- `INVALID_REQUEST` - Invalid request format or missing required fields
- `INVALID_PARAMS` - Request validation failed
- `UNAUTHORIZED` - Invalid or missing API key
- `FORBIDDEN` - Operation not permitted
- `AGENT_NOT_FOUND` - Requested agent doesn't exist
- `RESOURCE_NOT_FOUND` - Requested resource doesn't exist
- `INTERNAL_ERROR` - Server error occurred

## 🎨 Content Response Formats

MUXI Runtime supports multiple content formats within API responses. The formation configuration determines how response content is formatted.

### Supported Formats

| Format | Description | Use Case | Example |
|--------|-------------|----------|---------|
| `markdown` | Rich text with headers, lists, code blocks | Documentation, default usage | `# Title\n\n**Bold text**` |
| `json` | Structured JSON data | Programmatic processing | `{"content": "...", "type": "response"}` |
| `text` | Plain text without formatting | Simple integrations, logs | `Clean text output` |
| `html` | Semantic HTML markup | Web integration, rich UI | `<h1>Title</h1><p>Content</p>` |

### Configuration

Set the response format in your formation YAML:

```yaml
overlord:
  response:
    format: "markdown"  # Options: "json", "text", "markdown", "html"
```

### API Usage

The content format affects the `data.content` field in chat responses:

```json
{
  "object": "chat.completion",
  "success": true,
  "data": {
    "content": "# Cloud Computing Benefits\n\n**Cost Efficiency**: Reduces infrastructure costs...",
    "format": "markdown",
    "artifacts": []
  }
}
```

For more details, see [Response Formats Documentation](../features/response-formats.md).

## 🔄 Recent Updates

### 2025-10-24: 100% Test Coverage Achieved ✅
- **Complete API Reference**: Created comprehensive, tested API documentation
- **23/23 Tests Passing**: All endpoints validated through E2E testing
- **Bug Fixes**: Resolved 10+ bugs including critical DELETE buffer memory issue
- **Production Ready**: All endpoints working correctly with proper error handling
- **Documentation**: Complete reference guide with examples and best practices

### 2025-01-31: Error Response Format Improvements ✅
- **Simplified Error Structure**: Removed redundant `trace` field from error responses
- **Unified Error Data**: All additional error information now uses `error.data` field
- **Enhanced Validation Errors**: Changed `loc` to `field` for clearer field identification
- **Improved Error Types**: Added explicit `type` and `error` fields for validation errors

### 2025-01-31: Secret Protection Implementation ✅
- **Placeholder Tracking**: Formation loader now tracks original secret placeholders during configuration loading
- **Secret Restoration**: All API endpoints restore placeholders instead of exposing actual secret values
- **Hardcoded Secret Masking**: Automatic detection and masking of hardcoded secrets at known paths
- **Pattern Detection**: Recognizes common API key patterns (OpenAI, Anthropic, Google, etc.)
- **Comprehensive Coverage**: Applied to all configuration endpoints (/v1/config, /v1/llm/settings, /v1/agents, etc.)
- **Config Endpoint Update**: `/v1/config` now returns summary with resource links per spec
- **Formation Endpoint**: `/v1/formation` returns full config with secrets properly masked

### 2025-01-31: API Specification Alignment Completed ✅
- **Envelope Format**: All endpoints now use consistent envelope format with proper error handling
- **Object Types**: Updated to use spec-compliant object types (`formation_status`, `formation_config`)
- **List Endpoints**: All list endpoints now return arrays directly with generic `list` object type
- **Authentication**: Fixed HTTP status codes (401 instead of 403 for auth errors)
- **Error Handling**: 404 and other HTTP exceptions now use proper envelope structure
- **Root Endpoints**: Both `/` and `/v1` return HTML status pages as specified
- Initial API documentation structure created
- Implemented endpoints documented in OpenAPI spec
- Implementation status tracking established

## 📖 Additional Resources

- [Original PRD](../../context/prds/formation-api.md) - Product requirements document
- [Full OpenAPI Spec](../../schemas/api/formation-api-v1.yaml) - Complete planned API specification
- [API v1 Guide](../api-v1.md) - High-level API overview

## 🤝 Contributing

When implementing new endpoints:
1. Update the implementation in the code
2. Add the endpoint to `formation-api-implemented.yaml`
3. Update the status in `implementation-status.md`
4. Update the progress counters in this README
