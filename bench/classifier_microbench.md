# Local Classification — Phase 2 Microbench

Generated `2026-04-28T19:20:50+0100`
Model: `local/Xenova/multilingual-e5-small`
Runs per eval set: `3`
Warmup: `12473 ms` (one-time, amortized over process lifetime)

## TL;DR

* Mean per-call latency, `classify_binary`:  **60.5 ms**  (~12x faster than the ~750 ms cloud-LLM baseline).
* Mean per-call latency, `pairwise_similarity`:  **57.7 ms**  (~13x faster).
* Worst-case per-request wall-time saving on a request that exercises all 13 replaced gates: **~9.0 s**.

Cloud-LLM baseline is the typical median for `mt<=1000` `gpt-4o-mini` calls observed in Phase 0 (`bench/local_classification_baseline.json`). Override with `--cloud-baseline-ms` if you measure something different.

## Per-intent latency (ms)

| Intent | n | min | median | p95 | max | mean | stdev |
|---|---:|---:|---:|---:|---:|---:|---:|
| `actionable` | 30 | 22.0 | 55.3 | 75.4 | 89.2 | 55.2 | 16.3 |
| `workflow_eligible` | 30 | 40.5 | 62.5 | 107.1 | 117.3 | 67.5 | 20.7 |
| `simple_question` | 30 | 36.0 | 64.4 | 109.0 | 166.7 | 70.9 | 25.3 |
| `clarification_context_switch` | 30 | 23.4 | 51.0 | 91.9 | 127.8 | 58.1 | 24.0 |
| `clarification_stop` | 30 | 19.2 | 49.0 | 64.1 | 70.8 | 45.6 | 14.8 |
| `clarification_needed` | 30 | 20.7 | 55.8 | 114.1 | 133.3 | 63.9 | 26.9 |
| `clarification_needs_more` | 30 | 44.4 | 78.8 | 135.9 | 204.7 | 87.2 | 32.0 |
| `credential_cancellation` | 30 | 19.5 | 48.1 | 65.5 | 69.7 | 48.6 | 11.9 |
| `credential_help_request` | 30 | 41.4 | 54.4 | 84.3 | 89.7 | 58.6 | 12.2 |
| `credential_request` | 30 | 24.7 | 51.9 | 126.9 | 157.4 | 62.7 | 31.7 |
| `recall_question` | 30 | 21.1 | 48.5 | 63.1 | 79.1 | 47.2 | 13.1 |

## Pairwise similarity latency (ms)

| Op | n | min | median | p95 | max | mean | stdev |
|---|---:|---:|---:|---:|---:|---:|---:|
| `pairwise_similarity` | 30 | 25.3 | 53.1 | 93.1 | 105.6 | 57.7 | 21.6 |

## Phase 2 wall-time impact extrapolation

* Phase 1 + Phase 2 Group A: **9 binary gates** fully replaced (3 credential + 6 pre-planning).
* Phase 2 Group A scheduler + Group D fusion: **2 pairwise gates** replaced (cosine similarity replaces an LLM scoring call).
* Phase 2 Group B: **2 LLM calls short-circuited** when classifier says no clarification needed (fast-path skips).

* Per-call cloud-LLM baseline: ~750 ms (Phase 0 measurement).
* Per-call classifier (mean): ~60.5 ms (`classify_binary`), ~57.7 ms (`pairwise_similarity`).
* Per-call wall-time saved: ~689 ms (binary), ~692 ms (pairwise).
* Worst-case per-request saving on a path that hits all 13 gates: ~9.0 s.

Real workloads typically hit a subset of gates per request: the heavy PDF prompt hits ~5 in Phase 0 (4 parallel + 1 sequential), the light-prompt micro-suite hits 0-3. Multiply per-request gate count by per-call saving to get the wall-time delta you should expect on a given workload.
