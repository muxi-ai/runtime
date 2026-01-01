# MUXI Runtime Features

Comprehensive guides for MUXI Runtime's key features.

## Core Features

- **[Multi-Identity User Management](multi-identity.md)** - Sophisticated user management with multiple identifiers per user
  - [Quick Start Guide](multi-identity-quickstart.md) - Get started in 5 minutes
- **[LLM Caching](llm-caching.md)** - Intelligent response caching with 70%+ cost savings
- **[Streaming Responses](streaming.md)** - Real-time streaming for conversational AI
- **[Response Formats](response-formats.md)** - Structured outputs with JSON Schema

## Feature Comparison

| Feature | Single-User (SQLite) | Multi-User (PostgreSQL) |
|---------|---------------------|-------------------------|
| Multiple identifiers per user | ❌ | ✅ |
| User isolation | ✅ (single user) | ✅ (per user) |
| Formation isolation | ✅ | ✅ |
| KV cache optimization | ✅ | ✅ |
| Auto-migration | ✅ | ✅ |

## Quick Links

- [Multi-Identity Quick Start](multi-identity-quickstart.md) - 5-minute guide
- [Multi-Identity Full Guide](multi-identity.md) - Comprehensive documentation
- [Multi-User Architecture](../multi-user-architecture.md) - High-level overview
