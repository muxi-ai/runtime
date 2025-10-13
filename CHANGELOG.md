# Changelog

## Unreleased

### Added
- **LLM Response Caching**: Intelligent caching system using OneLLM's built-in cache
  - Configuration-driven via formation YAML (`llm.settings.caching`)
  - Production-optimized defaults: 10K entries, 0.95 similarity threshold, 24hr TTL
  - Semantic similarity matching for 70%+ cost savings on repeated queries
  - Automatic cache management with LRU eviction and TTL expiration
  - Module-level initialization in LLM service for universal coverage
  - Clean observability logging with warning suppression for harmless internal OneLLM messages
  - Full E2E test coverage (default, disabled, and custom configurations)
  - Comprehensive documentation: user guide with troubleshooting section

## 0.1.0

- Initial public release
