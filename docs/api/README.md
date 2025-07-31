# MUXI Formation API Documentation

This directory contains the living documentation for the MUXI Formation API implementation. It tracks what's actually built versus what's planned.

## 📁 Documentation Structure

- **[formation-api-implemented.yaml](./formation-api-implemented.yaml)** - OpenAPI 3.0 specification containing ONLY implemented endpoints
- **[implementation-status.md](./implementation-status.md)** - Detailed tracking of implementation progress with notes
- **[migration-guide.md](./migration-guide.md)** - Guide for API changes from design to implementation

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

## 📊 Implementation Progress

### Summary
- **Total Planned Endpoints**: 42
- **Implemented**: 38 (90%)
- **Partially Implemented**: 4 (10%)
- **Not Started**: 0 (0%)

### By Category
| Category | Implemented | Partial | Not Started |
|----------|-------------|---------|-------------|
| Health | ✅ 1/1 | - | - |
| Configuration | ✅ 2/2 | - | - |
| Overlord | ✅ 2/2 | - | - |
| Secrets | ✅ 5/5 | - | - |
| Agents | ✅ 5/5 | - | - |
| MCP | ✅ 8/8 | - | - |
| LLM | ✅ 3/3 | - | - |
| Logging | ✅ 2/2 | - | - |
| Memory | ✅ 4/4 | - | - |
| Async | ✅ 2/2 | 🔶 1/1 | - |
| Scheduler | ✅ 2/2 | - | - |
| A2A | ✅ 3/3 | - | - |
| Chat | ✅ 1/1 | - | - |
| Events | - | 🔶 1/1 | - |
| Jobs | - | 🔶 2/2 | - |
| Memories | - | 🔶 3/3 | - |

### Legend
- ✅ Fully implemented and tested
- 🔶 Partially implemented (core functionality exists but needs completion)
- ❌ Not started

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

## 🔄 Recent Updates

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
