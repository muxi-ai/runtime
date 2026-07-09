# Knowledge Trees (Reasoning-Based RAG)

How MUXI retrieves from large knowledge documents with hierarchical tree
indexes instead of (or alongside) flat vector search. PRD:
`engineering/prds/knowledge-reasoning-rag.md`. Code:
`src/muxi/runtime/formation/agents/knowledge/reasoning/`.

## Why trees

Flat chunk similarity degrades on long structured documents: chunking
fragments context, similarity is not relevance, and retrieval has no
concept of the document's hierarchy. A tree index is a structural table
of contents (titles + LLM summaries + node ids) compact enough to fit in
one LLM call; raw content lives in a separate node->raw KV store and is
fetched only for selected nodes.

## Retrieval modes

Each knowledge source declares a `retrieval:` mode:

| Mode          | How it retrieves                                     | Query cost          |
|---------------|------------------------------------------------------|---------------------|
| `vector`      | Flat chunk similarity (unchanged pipeline)           | none                |
| `tree`        | Method A: one LLM call navigates the compressed tree | 1 LLM call          |
| `tree-vector` | Method B: per-node chunk-embedding scoring           | 1 query embed       |
| `hybrid`      | A and B in parallel, dedup by node_id, sufficiency loop | 2+ LLM calls + embed |

Defaults: files under `knowledge.reasoning_threshold` tokens (40000;
`0` disables) stay on `vector`; files above it get `tree`. `tree-vector`
and `hybrid` are explicit per-source opt-ins.

Method B's node score is the PageIndex production formula:

```
NodeScore(n) = (1 / sqrt(N + 1)) * sum(ChunkScore(c))    N = chunks in n
```

You retrieve **nodes**, not chunks — the chunks are scoring scaffolding.
The `1/sqrt(N+1)` denominator rewards multi-chunk relevance with
diminishing returns so a 200-chunk node cannot dominate a genuinely more
relevant 5-chunk node. The formula lives in `ScoringService`
(`scoring_service.py`) — a standalone, memory-agnostic primitive
(`embed` / `score` / `aggregate_with_diminishing_returns`) that the
memory-revamp Layer 3 hybrid search reuses.

Hybrid runs a sufficiency evaluator after the A+B merge: a dedicated
single LLM call (`{"enough_info": bool, "gaps": [...]}`) on the
terminator model. Gaps expand via Method B scoring over unfetched nodes.
Loop bounds: `tree.max_sufficiency_rounds` (default 3) and
`tree.max_fetched_nodes_pct` (default 50% of the tree's nodes).

## Configuration

```yaml
knowledge:
  enabled: true
  reasoning_threshold: 40000     # tokens; 0 disables auto tree-indexing
  tree:
    model: null                  # tree build + Method A; null = agent text model
    terminator_model: null       # hybrid evaluator; null = tree model
    max_depth: 3
    max_tokens_per_node: 20000
    max_document_tokens: 500000  # above this: vector, with a warning event
    max_sufficiency_rounds: 3
    max_fetched_nodes_pct: 50
  sources:
    - path: "knowledge/manuals/large.pdf"
      description: "Product manual"
      retrieval: tree
    - path: "knowledge/policies/"
      description: "Policy corpus"
      retrieval: hybrid
    - path: "knowledge/regulations/"
      description: "Regulation corpus"
      retrieval: hybrid
      agent_tree:                # persistent formation-level tree
        regenerate: on-source-change
```

`model` / `terminator_model` accept an `llm.aliases` name or a
`provider/model` string, resolved through the hierarchical
model-selection path. All keys are fail-fast validated at load
(`config/validation.py`). MUXI ships the mechanism, not a price table:
picking a cheap terminator is the formation author's call via
`terminator_model`.

## Per-document vs per-agent trees

- **Per-document** (default): built per file at ingest, cached under the
  knowledge cache dir keyed on `(file_path, file_md5)` as
  `<hash>_<md5>.tree.json` + `.tree.kv.jsonl` + (Method B)
  `.tree.emb.jsonl`. Same MD5 never rebuilds; an embedding-model swap
  invalidates only the embeddings sidecar.
- **Per-agent** (`agent_tree:` block): ONE tree for the whole source,
  persisted in `<formation_dir>/.knowledge-trees/<source_id>.json` +
  `.kv.jsonl` + `.emb.jsonl` + `.meta.json` (schema version, aggregate
  `source_md5`, build timestamp, embedding model). Deterministic given
  the source content, so it can be committed to the formation repo —
  deployments then load without rebuilding. Requires an explicit
  tree-serving `retrieval:` mode.

Regeneration triggers (`agent_tree.regenerate`):

- `manual` (default) — only an explicit rebuild rebuilds; a persisted
  tree is served even when the source changed.
- `on-source-change` — rebuild when the aggregate source MD5 drifts from
  `meta.json.source_md5`.
- `on-formation-load` — rebuild every load.

### Rebuilding

The runtime side of `muxi knowledge rebuild` (the CLI subcommand lives in
the CLI repo) is the admin endpoint:

```
POST /v1/knowledge/rebuild          (admin key)
{"agent_id": "librarian", "source_id": "regulations"}   # both optional
```

which walks agents and calls
`KnowledgeHandler.rebuild_agent_trees(source_id=...)` — a force rebuild
regardless of trigger. Internal callers can use that method directly.

## Failure isolation

Everything degrades, nothing breaks a user turn:

- Tree build failure / size cap / missing tree model at ingest ->
  vector pipeline + `KNOWLEDGE_TREE_FALLBACK_TO_VECTOR` (with cause).
- Method B embedding failure at ingest -> the tree serves Method A only.
- Retrieval failure at query time -> vector results serve the turn.
- In hybrid, one method failing degrades to the other; the sufficiency
  evaluator failing serves the current fetched set.

## Gotchas (pinned by unit tests and mental-model.md)

1. Every reasoning LLM call passes `caching=False` — the semantic
   response cache matches near-identical prompts and replays node
   selections/verdicts from unrelated queries.
2. `temperature=0.0` is coerced to the instance default by `LLM.chat`'s
   falsy check — the reasoning calls use `0.1`.
3. Every reasoning LLM call pins an explicit `max_tokens` — a
   formation-level `llm.settings.max_tokens` chat cap would truncate the
   structured JSON mid-object and fail the call.

## Observability

`KNOWLEDGE_TREE_BUILD_STARTED/_COMPLETED/_FAILED`,
`KNOWLEDGE_TREE_FALLBACK_TO_VECTOR`, `KNOWLEDGE_TREE_NODE_SELECTED`
(method "a"/"b"), `KNOWLEDGE_TREE_HYBRID_QUEUED`,
`KNOWLEDGE_TREE_SUFFICIENCY_EVALUATED`,
`KNOWLEDGE_TREE_HYBRID_TERMINATED_EARLY`,
`KNOWLEDGE_TREE_HYBRID_LOOP_CAPPED`, `KNOWLEDGE_AGENT_TREE_REGENERATED`.
Hybrid results carry a `cost` metadata block (`llm_calls`,
`evaluator_rounds`); token totals flow through the standard LLM request
events tagged with `component: knowledge_tree_*`.

## Testing

- Unit: `tests/unit/test_knowledge_reasoning*.py`,
  `test_knowledge_scoring_service.py`, `test_knowledge_tree_search_b.py`,
  `test_knowledge_tree_hybrid.py`, `test_knowledge_agent_trees.py`.
- E2E: `e2e/tests/6_knowledge/test_6g1*`, `test_6g2*` (Method A),
  `test_6h1*` (tree-vector), `test_6h2*` (hybrid + agent tree).
- Bench: `bench/knowledge/` compares all four modes on a fixture corpus
  (`cd bench && uv run python -m knowledge.compare_retrieval`).
