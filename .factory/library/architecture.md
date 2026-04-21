# Architecture — Embedding Layer (post-migration target)

How the embedding layer works after this mission completes. Reflects the end-state that all features are building toward.

## High-level flow

```
Formation YAML (llm.models.embedding: local/nomic-ai/nomic-embed-text-v1.5)
        │
        ▼
LongTermMemory / WorkingMemory / SQLiteMemory constructors
        │ (store model name; self._dimension = None)
        ▼
First add() or search() call
        │
        ▼
await self._ensure_dim()  ─────►  services/memory/embedding.py ─ probe_dimension()
        │                             │
        │                             ▼
        │                         onellm.Embedding.acreate(input="_")
        │                             │
        │                             ▼
        │                         LocalProvider (ONNX Runtime)
        │                             │
        │                             ▼
        │                         resp.data[0].embedding  ───► len() == 768
        │
        ▼
self._dimension = 768     (cached on instance)
        │
        ▼
INSERT INTO memories_768 (..., embedding, ...)
```

## Invariants

1. **Single embedding entry point: `services/memory/embedding.py`.** Every consumer routes through it. No consumer imports `onellm.Embedding` directly.
2. **No dispatch in MUXI.** Neither memory layers nor any other consumer branches on "is this a local or cloud model." The slug shape (`local/...`, `openai/...`, etc.) is opaque to MUXI — OneLLM resolves it.
3. **Dim is lazy.** `self._dimension` starts `None` and resolves on first use. Repeated probes across the same instance are memoized.
4. **`EmbeddingResponse` is a dataclass.** Attribute access (`resp.data[0].embedding`), never dict access.
5. **Schema pre-creates all common dim tables.** `memories_{384,768,1024,1536,3072}` exist immediately after schema init. Memory layer picks the right table based on `self._dimension`.
6. **Task semantics.** `task="search_document"` on `add()`; `task="search_query"` on `search()`. Harmless for non-Nomic models (OneLLM's LocalProvider just prepends `"<task>: "`; ignored by models that don't interpret the prefix).
7. **The SOP adapter wraps the model name, not a provider instance.** `OneLLMEmbeddingAdapter(model_name: str)` → `generate_embeddings(texts)` returns `list[list[float]]`.

## Components (post-migration)

### `services/memory/embedding.py` (NEW)

Functions:
- `embed(model, text, *, dimensions=None, task=None) -> list[list[float]]` — the single call surface
- `probe_dimension(model) -> int` — lazy-dim resolution
- `DEFAULT_EMBEDDING_MODEL` — `"local/nomic-ai/nomic-embed-text-v1.5"`

### `services/memory/long_term.py`

- `LongTermMemory.__init__(embedding_model: str, ...)` — stores the model name; does not construct any provider; does not probe
- `_ensure_dim()` — cached probe
- `add()` / `search()` — award-winning flow via `embed()`

### `services/memory/working.py`

Mirror of `long_term.py` with the same patterns.

### `services/memory/sqlite.py`

Mirror of `long_term.py` for SQLite backing. BLOB-packed embedding column at the probed dim.

### `services/multimodal/fusion_engine.py`

Text embedding in the fusion pipeline uses `embed()` with no fallback branches.

### `formation/workflow/sops.py`

`OneLLMEmbeddingAdapter` wraps `embedding_model_name` and exposes `generate_embeddings(texts)`. SOP search (`_add_to_faiss`, `_hydrate_working_memory`) uses the adapter unchanged.

### `formation/agents/knowledge/handler.py`

Dim-bucket decisions use `await probe_dimension(model)` instead of the deleted `resolve_embedding_dimension` / `get_local_embedding_dimension` helpers.

### `services/memory/__init__.py`

Slim exports list. Legacy symbols (`LocalEmbeddingProvider`, `get_local_embedding_async`, `LOCAL_EMBEDDING_MODEL_NAME`) are **removed**.

### `formation/config/validation.py`

Slug allowlist includes `local/*` alongside existing `openai/*`, `ollama/*`, `cohere/*`, etc. Validity of the specific slug is delegated to OneLLM via probe at formation load.

## Schema (after Milestone 2)

PostgreSQL and SQLite both pre-create:

```sql
memories_384    -- legacy MiniLM migration target
memories_768    -- DEFAULT (Nomic v1.5 + v2 MoE, all-mpnet, GTE)
memories_1024   -- Arctic, bge-m3, Cohere v3
memories_1536   -- OpenAI ada-002, text-embedding-3-small
memories_3072   -- OpenAI text-embedding-3-large
```

All `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` — idempotent; safe to re-apply.

## What's gone

- `services/memory/local_embeddings.py` (~340 LOC) — **deleted**
- Direct `sentence-transformers` in `pyproject.toml` — **removed**
- Legacy symbols from `services/memory/__init__.py` re-exports — **removed**
- All `is_local_model` / `_use_local_embeddings` / `resolve_embedding_dimension` call sites — **rewritten**

## External dependencies (post-migration)

- `onellm[cache]>=0.20260421.0` — ONNX Runtime backend, faiss-cpu, transformers (tokenizer)
- `OPENAI_API_KEY` (env) — for OpenAI regression test only
- HuggingFace public access — for Nomic weights (no token required)
