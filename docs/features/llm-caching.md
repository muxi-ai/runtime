# LLM Response Caching

MUXI Runtime includes intelligent LLM response caching powered by OneLLM, providing significant cost savings and performance improvements through semantic similarity matching.

## Overview

The caching system automatically caches LLM responses and reuses them for semantically similar requests, reducing API calls and latency while maintaining response quality.

## Features

- **Semantic Similarity Matching**: Uses embeddings to match similar requests, not just exact duplicates
- **Streaming Support**: Intelligent chunking for streaming responses
- **Configurable TTL**: Automatic cache expiration
- **LRU Eviction**: Efficient memory management
- **Zero Code Changes**: Works transparently with all LLM calls

## Configuration

Caching is **enabled by default** with production-optimized settings. Configure in your formation YAML:

```yaml
llm:
  settings:
    caching:
      enabled: true                       # Enable/disable caching (default: true)
      max_entries: 10000                  # LRU eviction limit (default: 10000)
      p: 0.95                             # Similarity threshold 0.0-1.0 (default: 0.95)
      hash_only: false                    # Disable semantic matching (default: false)
      stream_chunk_strategy: "sentences"  # Chunking: words|sentences|paragraphs|characters
      stream_chunk_length: 1              # Chunk size (default: 1)
      ttl: 86400                          # Time-to-live in seconds (default: 86400 = 1 day)
```

## Default Values

The defaults are optimized for MUXI's conversational AI use case:

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `enabled` | `true` | Caching provides 70%+ cost savings |
| `max_entries` | `10000` | Supports multi-user scenarios |
| `p` | `0.95` | 95% similarity balances quality and cache hits |
| `hash_only` | `false` | Semantic matching catches paraphrased queries |
| `stream_chunk_strategy` | `"sentences"` | Natural streaming for conversation |
| `stream_chunk_length` | `1` | One sentence at a time feels responsive |
| `ttl` | `86400` | 24 hours keeps content fresh |

## Disabling for Development

**Important**: You should typically disable caching during development to see the effects of prompt changes immediately:

```yaml
llm:
  settings:
    caching:
      enabled: false  # Disable caching for development
```

Or set a very short TTL:

```yaml
llm:
  settings:
    caching:
      enabled: true
      ttl: 60  # 1 minute - useful for testing cache behavior
```

## How It Works

### Semantic Matching

When `hash_only: false` (default):

1. Request arrives → Generate embedding
2. Search cache for similar embeddings (cosine similarity ≥ `p`)
3. If match found → Return cached response
4. If no match → Call LLM, cache response with embedding

### Hash-Only Mode

When `hash_only: true`:

1. Request arrives → Generate hash
2. Search cache for exact hash match
3. If match found → Return cached response
4. If no match → Call LLM, cache response

**Trade-offs**:
- Semantic mode: Higher cache hit rate, uses more memory for embeddings
- Hash mode: Lower hit rate, faster lookups, less memory

## Streaming Behavior

The caching system handles streaming responses intelligently:

- **Chunking Strategy**: Controls how responses are broken into chunks
  - `"sentences"`: Split on sentence boundaries (recommended for conversation)
  - `"words"`: Word-by-word streaming (very granular)
  - `"paragraphs"`: Paragraph-level chunks (good for long-form content)
  - `"characters"`: Character-level streaming (not recommended)

- **Chunk Length**: Number of units per chunk
  - For `"sentences"` + `length: 1` → One sentence at a time
  - For `"words"` + `length: 8` → 8 words at a time

## Performance Impact

### Cost Savings

Typical cache hit rates by use case:

- **Chatbots with FAQs**: 60-80% hit rate
- **Code generation**: 30-50% hit rate (more diverse requests)
- **Document analysis**: 40-60% hit rate

**Example**: With 70% cache hit rate and $0.01/1K tokens:
- Without caching: 10,000 requests × $0.01 = $100
- With caching: 3,000 LLM calls × $0.01 = $30 (70% savings)

### Latency Reduction

- Cache hit: ~5-10ms (in-memory lookup)
- Cache miss: Normal LLM latency (1-3s)
- Average with 70% hit rate: ~350ms vs 1,500ms without cache

## Monitoring

The initialization logs show cache configuration:

```
OneLLM cache initialized with 10000 max entries, 0.95 similarity threshold, 86400s TTL
```

If caching fails to initialize:

```
Failed to initialize OneLLM cache: [error details]
```

The system continues without caching (fail-safe behavior).

## Advanced Configuration

### Fine-Tuning Similarity Threshold

Adjust `p` based on your needs:

- `p: 0.99` - Very strict, only near-duplicates match (lower hit rate, higher quality)
- `p: 0.95` - Balanced (recommended)
- `p: 0.90` - Looser, catches more variations (higher hit rate, may return less precise matches)

### Memory Management

Estimate memory usage:

```
Memory = (max_entries × (embedding_size + response_size))
```

Typical values:
- Embedding: ~6KB (1536 dimensions × 4 bytes)
- Response: 1-10KB average
- **Total per entry**: ~10KB
- **10,000 entries**: ~100MB

### Multi-Model Caching

Each model has its own cache. With 3 models:

```yaml
llm:
  models:
    - text: "openai/gpt-4o"
    - streaming: "openai/gpt-4o-mini"
    - vision: "openai/gpt-4o"
  settings:
    caching:
      max_entries: 10000  # Per model = 30,000 total entries
```

## Best Practices

### Development

```yaml
# development-formation.afs
llm:
  settings:
    caching:
      enabled: false  # Or very short TTL for testing
```

### Production

```yaml
# production-formation.afs
llm:
  settings:
    caching:
      enabled: true
      max_entries: 50000    # Scale up for production
      p: 0.95               # Keep balanced
      ttl: 86400            # 24 hours
      stream_chunk_strategy: "sentences"
      stream_chunk_length: 1
```

### High-Volume Production

```yaml
# high-volume-formation.afs
llm:
  settings:
    caching:
      enabled: true
      max_entries: 100000   # Large cache
      p: 0.93               # Slightly looser for higher hit rate
      ttl: 43200            # 12 hours (faster turnover)
      hash_only: true       # Faster lookups for high QPS
```

## Troubleshooting

### Cache Not Working

Check initialization logs for:
```
OneLLM cache not available - init_cache not found in onellm package
```

**Solution**: Update OneLLM to a version that supports caching:
```bash
pip install --upgrade onellm
```

### Unexpected Cached Responses

If getting stale or incorrect cached responses:

1. **Lower similarity threshold**: Try `p: 0.97` for stricter matching
2. **Reduce TTL**: Try `ttl: 3600` (1 hour)
3. **Disable semantic matching**: Try `hash_only: true` for exact matches only

### High Memory Usage

If memory usage is too high:

1. **Reduce max_entries**: Try `max_entries: 5000`
2. **Enable hash_only**: Try `hash_only: true` (no embeddings stored)
3. **Reduce TTL**: Shorter TTL = faster eviction

### Cache Not Helping

If cache hit rate is low:

1. **Check request diversity**: High variety = low cache effectiveness
2. **Increase similarity tolerance**: Try `p: 0.90`
3. **Consider disabling**: Some use cases don't benefit from caching

## Related Documentation

- [Formation Configuration](../configuration/formation-yaml.md)
- [LLM Configuration](../configuration/llm-config.md)
- [Performance Optimization](../performance.md)
- [Observability](../observability.md)
