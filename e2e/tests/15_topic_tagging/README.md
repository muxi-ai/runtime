# Test Group 15: Topic Tagging

This test group validates the dynamic topic tagging feature - LLM-generated topic extraction from user requests for Trail dashboard categorization.

## Overview

Topic tagging automatically generates 1-5 topic tags from user requests using LLM analysis. These tags are emitted as observability events for consumption by the Trail dashboard service.

## Test Files

- `test_15a1_topic_extraction.py` - Tests LLM-based topic generation
  - Topic extraction from diverse request types
  - Topic normalization (lowercase-with-hyphens)
  - Observability event emission
  - Multiple topics per request
  
- `test_15a2_fallback_behavior.py` - Tests fallback scenarios
  - Heuristic mode returns empty topics
  - LLM errors return empty topics
  - Malformed responses handled gracefully

- `test_15a3_topic_diversity.py` - Tests topic generation across domains
  - Writing/content creation topics
  - Technical/debugging topics
  - Data analysis topics
  - Personal/lifestyle topics
  - Business/strategy topics

## Formations

- `formations/formation-topic-tagging/` - Formation with LLM configured for topic generation

## Configuration

Topic tagging is automatic when using LLM-based request analysis:

```yaml
llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"  # LLM required for topic generation

# Topics are extracted during workflow analysis (auto_decomposition enabled)
auto_decomposition: true
complexity_threshold: 7.0
```

## Features Tested

1. **Topic Generation**: Verifies LLM generates relevant topic tags
2. **Normalization**: Confirms lowercase-with-hyphens format
3. **Count Limits**: Tests 1-5 topic limit enforcement
4. **Observability**: Validates REQUEST_TOPICS_EXTRACTED events
5. **Fallback Safety**: Ensures empty list on errors/heuristic mode
6. **Diversity**: Tests across various request domains

## Dependencies

- LLM provider configured (OpenAI, Anthropic, etc.)
- Workflow analysis enabled (`auto_decomposition: true`)
- Observability system active

## Running Tests

```bash
# Run all topic tagging tests
bash .claude/scripts/test-and-log.sh e2e/tests/15_topic_tagging/

# Run specific test
bash .claude/scripts/test-and-log.sh e2e/tests/15_topic_tagging/test_15a1_topic_extraction.py

# Run with observability output
bash .claude/scripts/test-and-log.sh e2e/tests/15_topic_tagging/test_15a1_topic_extraction.py -v
```

## Expected Outputs

### Successful Topic Extraction
```json
{
  "event": "request.topics.extracted",
  "level": "info",
  "data": {
    "topics": ["writing", "blog", "quarterly-reports"],
    "topic_count": 3,
    "complexity_score": 7.5,
    "analysis_method": "llm"
  }
}
```

### Heuristic/Error Fallback
- No event emitted (topics list is empty)
- Normal processing continues
- System remains stable

## Trail Integration

Once deployed, Trail service can:
1. Listen for `request.topics.extracted` events
2. Build topic index with frequency counts
3. Apply similarity clustering ("docs" → "documentation")
4. Enable filtering by topic in dashboard
5. Show topic distribution charts

## Documentation

Topic tagging is part of the workflow analysis system. See:
- Formation workflow documentation
- Request analyzer implementation
- Observability event specifications
