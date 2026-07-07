# Memory Benchmarking Harness (Tier 1)

Runs the standard academic long-term-memory benchmarks against a REAL
MUXI formation — no mocks. This is Tier 1 of the memory benchmarking
PRD (`engineering/prds/memory-benchmarking.md`): directly comparable
scores on LongMemEval, LoCoMo, and ConvoMem.

## What it measures

For every question the harness reports two numbers:

1. **Retrieval recall (R@K)** — is the evidence in the top-K retrieved
   results? Session-level R@K is the headline (comparable to published
   Mem0 / Mastra / Zep / MemPalace numbers); turn-level R@K is also
   reported when the dataset labels evidence turns. Coverage@K and MRR
   are included for diagnosis.
2. **QA accuracy** (optional, `--qa`) — does the full stack (retrieval
   + LLM) answer the question correctly? Scored by an LLM judge
   against the ground truth.

Abstention questions (LongMemEval `_abs` ids, LoCoMo adversarial) have
no evidence by design: they are excluded from retrieval aggregates and
counted separately, but still scored for QA (correct = declining).

## Retrieval modes

| Mode         | What it tests                                        |
|--------------|------------------------------------------------------|
| `working`    | FAISS working-memory search only                     |
| `persistent` | SQLite (sqlite-vec) persistent-memory search only    |
| `combined`   | Both backends, merged with Reciprocal Rank Fusion    |

RRF is used for `combined` because the two backends score on
different scales; rank fusion is scale-free and deterministic. The
PRD's fourth mode (combined + KG routing) is not part of Tier 1: it
depends on per-turn KG extraction (one LLM call per turn, which turns
a $0 retrieval run into a multi-dollar one) and is deferred to the
Tier 2 structured-recall work where the KG is the subject under test.

## Cheap-model configuration

`formation/formation.yaml` is the run template:

- **Embeddings:** `local/nomic-ai/nomic-embed-text-v1.5` (ONNX,
  on-box, free). Retrieval-only runs make **zero** API calls.
- **Text model:** `openai/gpt-4o-mini` — only used with `--qa`
  (one answer + one judge call per question). The fixture run costs
  well under $0.01; a full LongMemEval `--qa` run is on the order of
  $1-2 at current list prices.
- **Persistent memory:** SQLite + sqlite-vec, in a per-run temp
  directory. Every run is isolated; per-case `user_id` scoping keeps
  haystacks from bleeding into each other.

Every report includes the run's LLM request count, token totals per
model, and an estimated cost, so spend is always visible.

Secrets: the harness reuses the e2e secrets pair. It looks for
`.key`/`secrets.enc` in `e2e/assets/` (override with `--secrets-dir`).
`secrets.enc` is committed; `.key` is gitignored — copy it from your
main checkout as for the e2e suite.

## Running

```bash
# Committed fixture samples (CI-safe, no downloads, ~1 min each)
uv run python -m bench.memory.longmemeval_runner --fixture --qa
uv run python -m bench.memory.locomo_runner --fixture --qa
uv run python -m bench.memory.convomem_runner --fixture --qa

# Full datasets
uv run python -m bench.memory.download_datasets --data-dir ~/datasets/membench
export MUXI_BENCH_DATA_DIR=~/datasets/membench

# Dev split (50 questions, for tuning) vs holdout (for publishing)
uv run python -m bench.memory.longmemeval_runner --split dev --mode combined
uv run python -m bench.memory.longmemeval_runner --split holdout --mode combined --qa

# Full mode matrix for one benchmark
for mode in working persistent combined; do
    uv run python -m bench.memory.longmemeval_runner --split holdout --mode "$mode"
done
```

Useful flags: `--limit N` (smoke runs), `--k`, `--fetch-limit`,
`--seed` (split shuffle), `--output`. The per-run temp dir (rendered
formation, SQLite DB, `membench-events.jsonl` event log) is removed
after the run — the JSON report is the durable artifact. To inspect
it, pass `--keep-run-dir` (or set `MUXI_BENCH_KEEP_RUN_DIR=1`), or
supply an explicit `--run-dir`, which is never deleted. Exit code is
0 only when every question completed without a harness error.

## Datasets and licensing

The committed files under `fixtures/` are small **synthetic** samples
that follow each dataset's published schema — no third-party data is
committed. The full datasets are for local benchmarking only:

| Dataset     | Source                                        | License |
|-------------|-----------------------------------------------|---------|
| LongMemEval | HF `xiaowu0162/longmemeval-cleaned`           | See upstream repo (research release, ICLR 2025) |
| LoCoMo      | GitHub `snap-research/locomo`                 | CC-BY-NC-4.0 |
| ConvoMem    | HF `Salesforce/ConvoMem`                      | CC-BY-NC-4.0 |

CC-BY-NC datasets must never be committed to this repository or
redistributed with MUXI artifacts.

## Methodology notes

- **Indexing granularity:** one memory item per conversation turn,
  rendered as `[session date] role: content`. Session-level rankings
  are derived from the turn ranking (a session's rank is its best
  turn's rank).
- **Isolation:** each case runs under its own `user_id`; working
  memory is cleared between cases (its FIFO capacity is global).
- **Determinism:** retrieval is deterministic (exact FAISS/sqlite-vec
  search, `recency_bias=0`, seeded splits); QA runs at temperature 0.
  Reports are written with sorted keys so runs diff cleanly.
- **Truncation:** turns longer than `--max-embed-chars` (default
  6000) are clipped before embedding; the count is reported under
  `usage.truncated_turns`.
- **ConvoMem evidence:** located by exact text match of
  `message_evidences` inside the item's conversations, so scoring is
  conversation-level R@K plus turn-level for the matched messages.

## Results

`results/` holds committed fixture-run reports (one per benchmark and
mode) so the harness output format is pinned and regressions in the
retrieval path show up as diffs. Full-dataset reports are timestamped
and can be committed alongside published numbers.

## Layout

```
bench/memory/
├── datasets.py            # Normalized model + LongMemEval/LoCoMo/ConvoMem loaders
├── scoring.py             # R@K, coverage@K, MRR, RRF, aggregation
├── split.py               # Seeded dev/holdout split (PRD: 50 dev)
├── report.py              # JSON report + human summary + cost estimation
├── adapter.py             # Real-formation adapter (ingest/search/QA)
├── runner.py              # Shared run loop + CLI
├── longmemeval_runner.py  # Entry point (K=5)
├── locomo_runner.py       # Entry point (K=10)
├── convomem_runner.py     # Entry point (K=5)
├── download_datasets.py   # Full-dataset fetch instructions/downloads
├── formation/             # Benchmark formation template (cheap-model config)
├── fixtures/              # Committed synthetic samples (CI-safe)
└── results/               # Committed fixture-run reports
```

Unit tests: `tests/unit/bench_memory/` (loaders, metrics, split,
report, adapter logic — `uv run python -m pytest tests/unit/bench_memory/`).
