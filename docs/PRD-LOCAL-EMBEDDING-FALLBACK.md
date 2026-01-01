# PRD: Local Embedding Fallback

## Overview

When no embedding model is configured in `formation.afs`, the runtime should automatically fall back to a local sentence-transformer model (`all-MiniLM-L6-v2`) instead of using the current basic linguistic fallback.

## Problem

Currently, if `llm.models.embedding` is not configured:
1. Memory service uses `_generate_semantic_fallback_embedding()` - a basic linguistic feature extraction
2. This produces poor quality embeddings (not truly semantic)
3. Vector search/semantic memory quality suffers significantly
4. Users may not realize their setup is degraded

## Solution

Use the already-installed `sentence-transformers` library to provide a high-quality local embedding fallback.

### Model Selection

**Model:** `all-MiniLM-L6-v2`
- Already used in runtime for document processing
- 384 dimensions (vs 1536 for OpenAI)
- ~22MB download (one-time)
- ~10-15s first load, then cached
- Good quality for semantic similarity

**Alternative considered:** `paraphrase-multilingual-MiniLM-L12-v2` (used in OneLLM)
- 50+ language support
- 384 dimensions
- ~118MB download
- Better for multilingual, but larger

**Recommendation:** Start with `all-MiniLM-L6-v2` for consistency with existing document processing. Can add multilingual option later.

## Implementation

### 1. Memory Service Changes

**File:** `src/muxi/services/memory/long_term.py`

```python
# In __init__ or property getter
@property
def embedding_model(self):
    """Get the embedding model, creating it lazily if needed."""
    if self._embedding_model is None:
        if self._embedding_model_name:
            # User configured a model - use it
            self._embedding_model = LLMClass(model=self._embedding_model_name)
        else:
            # No model configured - use local fallback
            self._use_local_embeddings = True
            observability.observe(
                event_type=observability.MemoryEvents.MEMORY_INITIALIZED,
                level=observability.EventLevel.INFO,
                data={"embedding_model": "all-MiniLM-L6-v2", "type": "local_fallback"},
                description="Using local embedding model (all-MiniLM-L6-v2). "
                           "For better quality, configure llm.models.embedding"
            )
    return self._embedding_model
```

### 2. Local Embedding Helper

**File:** `src/muxi/services/memory/local_embeddings.py` (new)

```python
"""Local embedding support using sentence-transformers."""

from typing import List, Optional
import threading

_model = None
_model_lock = threading.Lock()

def get_local_embedding(text: str, model_name: str = "all-MiniLM-L6-v2") -> List[float]:
    """
    Generate embedding using local sentence-transformer model.

    Args:
        text: Text to embed
        model_name: Model name (default: all-MiniLM-L6-v2)

    Returns:
        List of floats (384 dimensions for MiniLM)
    """
    global _model

    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(model_name)

    embedding = _model.encode(text, convert_to_numpy=True)
    return embedding.tolist()

def get_local_embedding_dimension(model_name: str = "all-MiniLM-L6-v2") -> int:
    """Get embedding dimension for the model."""
    dimensions = {
        "all-MiniLM-L6-v2": 384,
        "paraphrase-multilingual-MiniLM-L12-v2": 384,
        "all-mpnet-base-v2": 768,
    }
    return dimensions.get(model_name, 384)
```

### 3. Integration Points

Update these locations to use local embeddings when no model configured:

1. **LongTermMemory** (`long_term.py`)
   - `_get_embedding()` method
   - Vector dimension handling (384 vs 1536)

2. **Knowledge Service** (if applicable)
   - Document embedding during knowledge loading

3. **Multimodal Fusion Engine** (`fusion_engine.py`)
   - Already has `_generate_semantic_fallback_embedding()` - replace with local model

### 4. Configuration

No new configuration needed - this is automatic fallback behavior.

Optional future enhancement in `formation.afs`:
```yaml
llm:
  settings:
    local_embedding_model: "all-MiniLM-L6-v2"  # Override local fallback model
```

## Logging & Observability

### On Initialization (once)
```
INFO: No embedding model configured. Using local model 'all-MiniLM-L6-v2'.
      For better quality, configure: llm.models.embedding: "openai/text-embedding-3-large"
```

### On First Use (once)
```
INFO: Loading local embedding model (one-time, ~10s)...
INFO: Local embedding model ready (384 dimensions)
```

## Vector Dimension Handling

**Important:** Local model produces 384-dim vectors vs OpenAI's 1536-dim.

The memory service should:
1. Auto-detect dimension from configured/fallback model
2. Create appropriate vector index
3. Handle dimension mismatch gracefully (error if mixing)

```python
# In LongTermMemory.__init__
if self._use_local_embeddings:
    self.dimension = 384  # MiniLM
else:
    self.dimension = 1536  # OpenAI default (or from model config)
```

## Testing

1. **No config test:** Verify local embeddings work when `llm.models.embedding` not set
2. **Quality test:** Compare semantic search results local vs OpenAI
3. **Performance test:** Measure first-load time and subsequent embedding time
4. **Dimension test:** Verify correct vector dimensions stored

## Migration Notes

- Existing formations with no embedding config will start using local embeddings
- This is a **quality improvement** over current linguistic fallback
- No breaking changes - just better default behavior
- Users can still configure API-based embeddings for production quality

## Success Criteria

1. Memory/knowledge features work out-of-box without embedding config
2. Log message informs users about fallback and how to upgrade
3. Semantic search quality is reasonable (not perfect, but usable)
4. No errors or crashes when embedding not configured

## Timeline

- Implementation: 1-2 hours
- Testing: 1 hour
- Total: Half day

## References

- OneLLM caching implementation: `onellm/cache.py`
- Current fallback: `src/muxi/services/multimodal/fusion_engine.py`
- Sentence-transformers docs: https://www.sbert.net/
