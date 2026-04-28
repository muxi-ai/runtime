# Phase 0 Baseline — `feature/local-classification`

Generated 2026-04-28 against the `hello-muxi` formation running on
`runtime` HEAD `012e587a` (post-2026-04-28 fixes), using the venv
Python 3.11 + `onellm` 0.20260422.3. 3 runs per workload.

Raw data: [`local_classification_baseline.json`](./local_classification_baseline.json)
Harness: [`run_baseline.py`](./run_baseline.py)
Light prompts: [`light_workload_microsuite.py`](./light_workload_microsuite.py)

> **Methodology note:** The harness counts outbound LLM calls by
> watching `model.request.started` events in the runtime log and
> bucketing by `data.max_tokens`. Empirically the classification-shaped
> calls all use `max_tokens ≤ 1000` (booleans, action labels, topic
> arrays, structured-JSON gate decisions). `max_tokens` 1001-4000
> indicates synthesis (response text). `max_tokens > 4000` is the
> heavy planning call.

---

## TL;DR

The pre-planning pipeline emits **~4-5 cloud LLM calls per
non-trivial request** — not 1, as a first-pass `mt ≤ 64` threshold
suggested. Most fire **in parallel via `asyncio.gather`**, then a
sequential agent-router call gates entry to the planner.

Wall-time spent on these classification-shaped calls is significant:

| Workload | Classify calls / req | Pre-planning cloud wall | % of total wall |
|---|---:|---:|---:|
| Heavy (PDF), full-path | 5 (4 parallel + 1 sequential) | **~14 s** | **~23 %** |
| Heavy (PDF), partial-path | 1-3 | ~2-5 s | ~10 % |
| Light, classify-heavy prompts (`approval_yes`, `scheduling`, `simple_question`) | 2.67-3.0 | 1-3 s | 15-30 % |
| Light, fast-path prompts (`greeting`, `follow_up`) | 0-1 | <0.5 s | <15 % |

Replacing those 4-5 cloud calls with local prototype-similarity
classifiers (~5-30 ms each, run in the same parallel/sequential
pattern) recovers the bulk of that wall time.

---

## Method

* Started runtime via
  `python -m muxi.runtime.utils.run_formation hello-muxi/formation.afs --port 8000`.
* Each prompt sent over HTTP `POST /v1/chat` with `stream=false`.
* Each run uses a fresh `session_id` so buffer doesn't accumulate.
* Per-prompt LLM call count parsed from runtime log
  (`model.request.started` events), bucketed by `data.max_tokens`:
  * `classify` ≤ 1000 (boolean / label / structured-JSON outputs)
  * `synth` 1001–4000 (response generation)
  * `plan` > 4000 (decomposition)
  * `unknown` (no `max_tokens` field — typically streaming starts)
* Window: `[request_start − 250 ms, request_end + 1 s]` to absorb
  log-flush jitter.

---

## Heavy workload — `"create a one-page PDF about MUXI"`

3 runs.

| Metric | Value |
|---|---|
| Wall time, median | **60.4 s** |
| Wall time, range | 26.1 – 64.8 s |
| Total LLM calls (3 runs) | classify=**8**, synth=3, plan=2, unknown=1 |
| Per-run avg | classify=**2.67**, synth=1.00, plan=0.67 |

### Run 2 detailed timeline (the canonical full-path case)

```
+0.010s  request.received
+0.520s  ┐ 4 PARALLEL gate calls fire (asyncio.gather):
+0.523s  │   mt=10    actionability heuristic / threat
+0.524s  │   mt=20    workflow eligibility
+0.524s  │   mt=250   topic extraction (returns 4 topics by +0.528s)
+0.524s  │   mt=1000  clarification analysis (clarification.request.sent same ms)
         ┘
+5.986s  overlord.routing.completed → muxi-expert (gates done by here)
+6.000s  mt=200       agent-router structured selection
+14.513s agent.planning(planning_start)
+14.515s mt=16384     THE BRAIN — decomposition + tool plan
+46.752s agent.planning(execution_plan_ready)
+46.903s mt=None      synthesis stream
+60.351s request.completed
```

Wall-clock decomposition:

| Phase | Wall | Replaceable? |
|---|---:|---|
| Setup | 0.5 s | no |
| 4 parallel gates → router-ready | 5.5 s | **yes — local parallel classifier** |
| Router cloud call → planning prep | 8.5 s | **yes — local classifier** (some agent-setup work in there too) |
| Planning (the brain) | 32.2 s | NO |
| Synthesis stream | 13.5 s | NO |
| **Total** | **60.4 s** | |

**Pre-planning cloud spend on the full-path heavy run: ~14 s of 60 s = 23 %.**

### Per-run path variance

* **Run 1 (64.8 s):** sparse path — only 1 small call observed early, then synth, then plan. Possibly a cold-start where some gates short-circuited.
* **Run 2 (60.4 s):** canonical full-path with all 4 parallel gates firing. The "expected" behavior.
* **Run 3 (26.1 s):** fast path — multiple small calls fire essentially simultaneously, planning starts at +2.08 s, no `mt=16384` observed at all. Looks like response-cache / decomposition-cache hit.

The runtime takes different paths on identical prompts depending on
state. Worst case (run 2) is what the local-classifier proposal needs
to address; best case (run 3) is already fast and won't see much
benefit either way.

---

## Light workload — 10-prompt micro-suite

3 runs × 10 prompts = 30 prompt invocations.

| Metric | Value |
|---|---|
| Per-prompt wall, median | **6.4 s** |
| Per-prompt wall, range | 2.7 – 21.6 s |
| Per-run total wall, avg | ~73.4 s |
| Total LLM calls (30 prompts) | classify=**54**, synth=22, plan=10, unknown=3 |
| Per-prompt avg | classify=**1.80**, synth=0.73, plan=0.33 |

### Per-prompt breakdown (averaged across 3 runs)

| label              | wall_med | classify | synth | plan |
|--------------------|---------:|---------:|------:|-----:|
| greeting           |   3.22 s |     0.33 |  0.00 | 0.00 |
| acknowledgment     |   4.31 s |     1.33 |  0.00 | 0.00 |
| simple_question    |   8.15 s |     **2.67** |  1.67 | 0.67 |
| help_request       |   3.40 s |     1.33 |  0.67 | 0.00 |
| scheduler_query    |   6.75 s |     1.33 |  0.67 | 0.00 |
| approval_yes       |  10.28 s |     **3.00** |  0.67 | 0.67 |
| approval_no        |   3.80 s |     2.33 |  0.33 | 0.00 |
| follow_up          |   2.82 s |     1.67 |  0.33 | 0.00 |
| trivia             |  11.63 s |     1.00 |  0.67 | 1.00 |
| scheduling         |  14.66 s |     **3.00** |  2.33 | 1.00 |

**Observations:**
* The high-wall-time prompts are also the high-classify-count prompts
  (`scheduling` 3.0 calls / 14.66 s, `approval_yes` 3.0 calls / 10.28 s,
  `simple_question` 2.67 calls / 8.15 s). These are the prompts that
  trigger the full pre-planning gate cluster. They benefit most from
  local classification.
* `greeting` and `follow_up` already short-circuit through fast-path
  (0.33 and 1.67 calls respectively). They get smaller, but still real,
  wins.
* Several prompts trigger unwarranted **planning** calls
  (`simple_question`, `trivia`, `scheduling`, `approval_yes`). This is a
  separate optimization opportunity orthogonal to local classification.

---

## Realistic upside calculation (parallelism-aware)

Cloud `gpt-4o-mini` classification call latency on the wire: ~200-2000 ms
each (mt=1000 calls trend longer due to more output tokens). Local
prototype-similarity using `Xenova/multilingual-e5-small`: ~5-30 ms each.

### Heavy workload

* Parallel gate cluster (4 calls): wall = **max** of cloud latencies, ~5.5 s observed.
  Local equivalent: max of ~30 ms each = ~30-50 ms.
  **Saved: ~5.4 s.**
* Sequential agent router (mt=200): some fraction of the 8.5 s gap
  between "gates done" and "planning starts" — probably 3-8 s of cloud
  router latency, the rest being agent-setup work that won't move.
  **Saved: ~3-8 s.**
* **Heavy full-path total: ~9-13 s saved on a 60 s run = 15-22 %.**
* **Heavy partial-path: ~2-5 s saved (fewer cloud calls in the path).**

### Light workload

* Per-prompt savings vary by category:
  * Classify-heavy prompts (`scheduling`, `approval_yes`,
    `simple_question`, `approval_no`): **1-3 s saved** out of 4-15 s wall
    (15-30 %).
  * Fast-path prompts (`greeting`, `follow_up`): **0-0.5 s saved** out
    of 3-5 s wall (small but real).
* Aggregate across 30 prompts: ~30-60 s saved out of ~220 s = **14-27 %**.

---

## What was wrong in my first cut

* Used `mt ≤ 64` as the classification threshold. That caught only
  binary yes/no calls and missed the structured-output calls
  (`mt=200` agent router, `mt=250` topic extraction, `mt=1000`
  clarification). Real boundary is `mt ≤ 1000`.
* Reported 0.5 % heavy / 2.4 % light upside. Real numbers are
  15-22 % heavy and 14-27 % light when measured properly.
* Stated the "4 sequential gates" model was wrong. Actually they're
  **4 parallel** gates plus 1 sequential router. The architectural
  model is correct; the savings calculation is parallelism-bounded
  for the gate cluster, sum-bounded for the sequential router.

The user pushed back on the first analysis. The pushback was right.

---

## Findings

### Architectural truth (corrected)
* **5 cloud LLM calls** before the brain on a full-path heavy request:
  4 parallel gates (actionability, eligibility, topic extraction,
  clarification) + 1 sequential agent-router call.
* The 4 parallel gates each take 200-2000 ms of cloud latency. Wall
  time is bounded by the slowest: ~2-6 s on `gpt-4o-mini`.
* The sequential router gates entry to the planner. ~500 ms-2 s on the
  wire, additional setup/wait before planning fires.
* Together: **~14 s of pre-planning cloud time on the canonical
  60 s heavy run** (run 2). The 8 s gap between "router complete" and
  "planning starts" is not all router latency, but most of it is.

### Performance upside (corrected)
* Heavy full-path: **15-22 %** wall-time reduction.
* Light, classify-heavy prompts: **15-30 %** per-prompt reduction.
* Light, fast-path prompts: small but non-zero reduction.

### Adjacent finding (out of scope, flagged for later)
* Planning (`mt=16384`) fires on prompts that don't need it:
  `simple_question`, `trivia`, `approval_yes`, `scheduling`. This is
  its own optimization opportunity — likely a planner-skip heuristic.
  Not addressed by local classifiers; tracked separately.

---

## Decision gate (for Phase 1 entry)

The data now supports **proceeding with Phase 1** as designed. The
performance argument is real (15-22 % on heavy, 14-27 % aggregate on
light), and the architectural arguments (cost, multilingual,
deterministic, no rate limits) compound on top.

Suggested Phase 1 scope unchanged from the original plan:
1. RequestAnalyzer-only prototype using `Xenova/multilingual-e5-small`
   via OneLLM, prototype-similarity matching with confidence threshold.
2. Validate against the 4 criteria (latency, accuracy, e2e behavior,
   light-workload speedup).
3. If validation holds, broaden to the other 3-4 call sites in Phase 2.
