# Memory Benchmarking Harness

Runs the memory benchmarks against a REAL MUXI formation — no mocks.
Implements the memory benchmarking PRD
(`engineering/prds/memory-benchmarking.md`):

- **Tier 1** — standard academic benchmarks (LongMemEval, LoCoMo,
  ConvoMem): directly comparable scores against Mem0/Mastra/Zep/
  MemPalace.
- **Tier 2** — structured recall: MUXI's own dataset for the
  categories no published system benchmarks (KG relationship recall,
  temporal validity, narrative recall, cross-agent knowledge,
  contradiction detection). See "Tier 2" below.
- **Tier 3** — multi-session longitudinal: 30-90 day corpora proving
  buffer-eviction compensation, cross-agent propagation, multi-user
  isolation, and contradiction detection over time. See "Tier 3"
  below.
- **Tier 4** — cost efficiency: tokens-per-accurate-recall, cost per
  1,000 queries, retrieval latency percentiles under load, memory
  footprint. See "Tier 4" below.

## Tier 1: what it measures

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
a $0 retrieval run into a multi-dollar one). The KG is exercised as
the subject under test in Tier 2's `structured` mode instead (see
below).

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

## Tier 2: structured recall

The categories that require the Knowledge Graph + Captain's Log —
no public dataset tests them, so MUXI generates its own
(`structured_corpus.py`, seeded and fully deterministic, no LLM):

| Category | Tests |
|----------|-------|
| `kg_relationship` | Entity-relationship recall (who recommended X for Y; emails, codes) |
| `temporal_validity` | What was true at a point in time (roles before/after changes) |
| `narrative_recall` | Day-level narrative (decisions/projects of a date) |
| `cross_agent` | Knowledge produced by one agent, queried through another |
| `contradiction_detection` | Conflicting facts that must be surfaced, not merged |

```bash
# Committed fixture (3 sequences, 30 questions; CI-safe)
uv run python -m bench.memory.structured_recall_runner --fixture --qa
uv run python -m bench.memory.structured_recall_runner --fixture --mode structured --qa

# Full dataset (50 sequences, 500 questions — PRD scale)
uv run python -m bench.memory.structured_corpus --preset full \
    --output ~/datasets/membench/structured_recall_full.json
uv run python -m bench.memory.structured_recall_runner \
    --dataset ~/datasets/membench/structured_recall_full.json --mode structured --qa
```

Modes: the Tier 1 vector modes (`working`/`persistent`/`combined`)
run unchanged as baselines, plus `structured` — Knowledge Graph +
Captain's Log retrieval. In `structured` mode the ground-truth
manifest is ingested through the real service write paths
(`apply_extraction`, `upsert_entry`), which isolates *structured
recall* (can the KG/log query surface answer this?) from *extraction
quality* (can the LLM build the right graph from raw text?). The
contradiction audit compares the storage layer's conflict/supersede
flags against the injected ground truth (precision/recall).

Two Tier 2-specific metric blocks appear in every report:

- **Exact-string recall** — questions whose answers are verbatim
  tokens (emails, invoice/ticket codes) carry `exact_strings`; the
  runner reports whether they appear in the top-K retrieved context.
  This is the decision input for memory-revamp Phase 6 (hybrid/BM25
  search): semantic embeddings are weak at exact-token matching, and
  misses are listed by question id in the summary.
- **Contradiction detection** — precision/recall of the KG's
  contradiction flags (structured mode only).

### Publishing the dataset to HuggingFace

The dataset is MUXI's original contribution and is published under
MIT. Rendering is automated; the upload itself must run under the
dataset owner's HF account:

```bash
uv run python -m bench.memory.structured_corpus --preset full \
    --output /tmp/structured_recall_full.json
uv run python -m bench.memory.hf_publish \
    --dataset /tmp/structured_recall_full.json --output /tmp/hf-structured-recall
# owner only:
hf auth login
hf upload muxi-ai/structured-recall /tmp/hf-structured-recall --repo-type dataset
```

## Tier 4: cost efficiency

Uses the structured-recall corpus as a reproducible workload:

```bash
# Retrieval-only (no API calls): latency percentiles + footprint
uv run python -m bench.memory.cost_runner --fixture

# Measured tokens-per-accurate-recall + priced cost projections
uv run python -m bench.memory.cost_runner --fixture --qa

# Heavier load pattern
uv run python -m bench.memory.cost_runner --fixture --queries 1000 --concurrency 16
```

Reports include: ingest throughput, retrieval latency p50/p95/p99
under bounded concurrency, estimated context tokens per query,
tokens-per-accurate-recall (answer-call tokens / correct answers;
judge overhead excluded), cost per 1,000 queries, monthly cost
projections for the PRD's usage scenarios (10/50/200 queries/day),
and storage footprint per ingested turn.

Latency note: with local ONNX embeddings the query-embedding compute
runs on-box and inside the measured path, so absolute latencies are
hardware-bound; compare runs on the same machine.

Pricing lives in `pricing.json` (USD per 1M tokens) — update it as
providers change list prices; every report echoes the table it used.

## Tier 3: multi-session longitudinal

Simulates 30-90 days of usage across users and agents. The corpus
comes from the "MemBench Generator" (`longitudinal_corpus.py` —
seeded, fully deterministic, no LLM), one sub-corpus per PRD scenario:

| Scenario | Proves | PRD target |
|----------|--------|-----------|
| `buffer_cycle` (A) | KG + Captain's Log answer day-1 questions at day-30, after the source turns were FIFO-evicted from the buffer | evicted-fact R@5 >= 85%, zero lost decisions |
| `cross_agent` (B) | Knowledge produced in one agent's sessions is answerable via another agent | R@5 >= 80%, zero artifact orphans |
| `isolation` (C) | User A's memory never surfaces in user B's retrieval | 0 leaks (pass/fail) |
| `contradiction` (D) | Conflicting facts across sessions are flagged (conflicted) or superseded, not merged | precision >= 90%, recall >= 80% |

```bash
# Committed fixture (CI-safe; retrieval-only runs are $0)
uv run python -m bench.memory.longitudinal_runner --fixture
uv run python -m bench.memory.longitudinal_runner --fixture --scenario buffer_cycle --qa

# Full corpus (PRD scale: 30-day corpora, 100 isolation users,
# 10,000 isolation retrieval operations)
uv run python -m bench.memory.longitudinal_corpus --preset full \
    --output ~/datasets/membench/longitudinal_full.json
uv run python -m bench.memory.longitudinal_runner \
    --dataset ~/datasets/membench/longitudinal_full.json
```

How each scenario runs (all against the real services, no mocks):

- **A — buffer cycle.** Raw turns are replayed into the real working
  memory under a small budget (`--buffer-max-mb`, default 0.4MB), and
  the buffer's own FIFO cleanup runs once per ingested session
  (benchmark time is compressed; production runs the same pass on a
  wall-clock interval). That is exactly the path the pre-compaction
  flush (memory-revamp Phase 3) guards: the runner counts flush
  hand-offs, and `--flush-digest` additionally lets the silent-turn
  digest make its real LLM calls (default off: deterministic, $0).
  The persisted layers get the ground-truth manifest (Tier 2 style —
  structured recall isolated from extraction quality), questions run
  against both layers, and the report shows the compensation story:
  working-baseline R@5 on evicted questions (expected ~0) vs
  structured R@5, plus a `recent_recall` control group and the
  zero-lost-decisions audit. `evidence_evicted_fraction` must be 1.0
  for the scenario to prove anything — below that, raise the corpus
  size or lower the budget.
- **B — cross-agent.** Facts and artifacts enter the KG/log from each
  agent's sessions; every question's evidence lives in a different
  agent's session than the one nominally asking (`question_meta` in
  the ground truth records the pair). The zero-orphan audit checks
  every artifact is reachable in the KG (entity + `produced` edge).
- **C — isolation.** Every user's corpus is ingested side by side
  (working + persistent + KG + log; nothing is cleared between
  users) and follows identical fact templates, differing only in
  values — so a scoping bug would make another user's near-identical
  turn the nearest neighbor. Retrieval operations (vector search, KG
  reads, log reads, cycled to `--isolation-ops`) are audited for
  foreign `CANARY-*` tokens and foreign session ids. Pass/fail.
- **D — contradiction over time.** The manifest is replayed
  per-session, in corpus order, through the live `store_extraction`
  path with per-fact confidences — the storage layer's contradiction
  detection fires exactly as in production (confidence delta above
  0.3 supersedes; otherwise both facts are flagged conflicted), and
  the event substrate records `fact.contradicted` audit events. The
  audit measures precision/recall against the injected pairs plus
  detection-kind accuracy, tallies the substrate events, then
  rebuilds the knowledge-graph projection from the event log
  (service layer, same path as the rebuild endpoint) and repeats the
  audit — `rebuild.consistent_with_live` proves replay determinism.
  Precision distractors (duplicate re-assertions, non-exclusive
  predicate changes) are injected and must NOT be flagged.

One process per scenario: `--scenario all` (the default) spawns a
subprocess per scenario because the runtime's database manager is a
process-level singleton — two formations in one process would share
the first run's SQLite path. Reports land one-per-scenario under
`results/` (`longitudinal_fixture_<scenario>.json`).

The full LLM-extraction replay (raw turns through
`process_conversation_turn`, measuring extraction quality end-to-end
rather than structured recall) remains out of scope here: one LLM
call per turn turns a $0 deterministic run into a multi-dollar
nondeterministic one. The per-session `store_extraction` replay in
Scenario D is the same write path with the extraction step supplied
by the manifest.

## Datasets and licensing

The committed files under `fixtures/` are small **synthetic** samples
that follow each dataset's published schema — no third-party data is
committed (`structured_recall_sample.json` and
`longitudinal_sample.json` are MUXI's own generated datasets,
regenerable with `structured_corpus.py --preset fixture` and
`longitudinal_corpus.py --preset fixture`).
The full third-party datasets are for local benchmarking only:

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
├── datasets.py                  # Normalized model + Tier 1 loaders
├── scoring.py                   # R@K, coverage@K, MRR, RRF, aggregation
├── split.py                     # Seeded dev/holdout split (PRD: 50 dev)
├── report.py                    # JSON report + human summary + cost estimation
├── adapter.py                   # Real-formation adapter (ingest/search/QA)
├── runner.py                    # Tier 1 shared run loop + CLI
├── longmemeval_runner.py        # Tier 1 entry point (K=5)
├── locomo_runner.py             # Tier 1 entry point (K=10)
├── convomem_runner.py           # Tier 1 entry point (K=5)
├── download_datasets.py         # Full-dataset fetch instructions/downloads
├── structured_corpus.py         # Tier 2 corpus + Q&A generator (seeded, no LLM)
├── structured_dataset.py        # Tier 2 dataset loader (+ ground-truth manifest)
├── structured_adapter.py        # Tier 2 adapter (KG + Captain's Log mode)
├── structured_scoring.py        # Exact-string recall + contradiction metrics
├── structured_recall_runner.py  # Tier 2 entry point (K=5, 4 modes)
├── longitudinal_corpus.py       # Tier 3 "MemBench Generator" (4 scenarios, seeded)
├── longitudinal_dataset.py      # Tier 3 dataset loader (+ scenario manifests)
├── longitudinal_adapter.py      # Tier 3 adapter (buffer cycling, audits, rebuild)
├── longitudinal_scoring.py      # Tier 3 scenario aggregates (targets, leaks)
├── longitudinal_runner.py       # Tier 3 entry point (one report per scenario)
├── cost_model.py                # Tier 4 math (percentiles, projections)
├── cost_runner.py               # Tier 4 entry point (latency/tokens/footprint)
├── pricing.json                 # Updatable per-model price table (USD/MTok)
├── hf_publish.py                # HuggingFace dataset rendering (no upload)
├── formation/                   # Benchmark formation template (cheap-model config)
├── fixtures/                    # Committed synthetic samples (CI-safe)
└── results/                     # Committed fixture-run reports
```

Unit tests: `tests/unit/bench_memory/` (loaders, metrics, split,
report, adapter logic, corpus generator determinism, longitudinal
scenario aggregates, cost-model math —
`uv run python -m pytest tests/unit/bench_memory/`).
