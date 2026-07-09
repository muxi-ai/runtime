# Knowledge Retrieval Comparison Bench

Compares the four knowledge retrieval modes of the reasoning-RAG system
(`engineering/prds/knowledge-reasoning-rag.md`, Phase 5) against a REAL
MUXI formation — no mocks:

| Mode          | What it tests                                            |
|---------------|----------------------------------------------------------|
| `vector`      | Flat chunk similarity (the pre-reasoning pipeline)       |
| `tree`        | Method A: pure LLM tree navigation                       |
| `tree-vector` | Method B: per-node chunk-embedding value scoring         |
| `hybrid`      | Parallel A+B, node dedup, sufficiency evaluator          |

## What it measures

For every fixture question the harness runs `KnowledgeHandler.search`
(top-k, default 5) and checks whether ALL expected substrings appear in
the retrieved contents (hit@k). Per mode it reports:

- **Hit rate** — questions where the buried fact was retrieved. Note:
  the handler truncates flat vector results to 200 chars (tree results
  return whole nodes), so `vector` scores what agents actually receive —
  which is exactly the long-document failure mode the PRD targets.
- **Query latency** — mean/median seconds per search
- **Ingest time** — formation load incl. tree build (fresh run dir, so
  tree builds are NOT cache-amortized between modes)
- **Token usage** — from the request-context tally (same mechanism as
  `bench/memory`)

## Corpus

`fixtures/colony-handbook.md` (~97KB, ~24k tokens): a structured
operations handbook with eight `FACT:` lines buried across six chapters —
the same fixture family as the `6_knowledge` e2e tests.
`fixtures/questions.json` maps one query to each fact.

## Cheap-model configuration

`formation/formation.yaml` is the run template:

- **Embeddings:** `openai/text-embedding-3-small` — cloud on purpose:
  ingesting the ~24k-token corpus through a local sentence-transformer
  triggers the multi-gigabyte CoreML compile documented in
  mental-model.md (macOS jetsam kills). The cloud embed costs well under
  a cent per four-mode run.
- **Text model:** `openai/gpt-4o-mini` — tree builds (~2 summary calls
  per build), Method A navigation (1 call/query), hybrid sufficiency
  (1-2 calls/query). A full four-mode run costs on the order of a cent.

Secrets: reuses the e2e pair. `secrets.enc` is committed under
`e2e/assets/`; `.key` is gitignored — copy it from your main checkout
(override the location with `--secrets-dir`).

## Running

```bash
cd bench
uv run python -m knowledge.compare_retrieval                 # all four modes
uv run python -m knowledge.compare_retrieval --modes tree,hybrid
uv run python -m knowledge.compare_retrieval --top-k 3
```

Reports land in `bench/knowledge/compare_retrieval.json` and `.md`
(gitignored artifacts of a run; commit a snapshot deliberately if you
want to pin numbers).
