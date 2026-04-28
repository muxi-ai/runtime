# Local Classification — Phase 2 Comparison

Baseline: `bench/local_classification_baseline.json`  
Phase 2:  `bench/local_classification_phase2.json`  
Baseline started: `2026-04-28T13:01:53+0100`  
Phase 2 started:  `2026-04-28T21:56:29+0100`  
Runs per workload: baseline=3, phase2=3

Phase 2 changes the following gates from cloud LLM calls to local prototype-similarity / pairwise cosine:

* `credentials.is_credential_request` (Group A)
* `credentials._is_cancellation` (Group A)
* `credentials._is_help_request` (Group A)
* `scheduler._is_significant_prompt_change` (Group A)
* `multimodal.fusion_engine` semantic similarity (Group D)
* `clarification._analyze_request` fast-path skip (Group B)
* `clarification._check_need_more` fast-path skip (Group B)

The clarification fast-paths only short-circuit when the local classifier is confident; the LLM still runs to generate the clarification question on the positive branch. Group A and Group D are full replacements with no LLM fallback.

## Heavy workload

| Metric | Baseline (Phase 0) | Phase 2 | Delta |
|---|---:|---:|---:|
| min wall | 26.057s | 40.653s | ↑56.0% |
| **median wall** | 60.353s | 50.709s | ↓16.0% |
| max wall | 64.770s | 77.976s | ↑20.4% |
| total wall (all runs) | 151.180s | 169.338s | ↑12.0% |

### LLM call buckets (totals across all runs)

| Bucket | Baseline | Phase 2 | Delta |
|---|---:|---:|---:|
| classification | 3 | 0 | ↓ 3 |
| synthesis | 8 | 9 | ↑ 1 |
| planning | 2 | 1 | ↓ 1 |
| unknown | 1 | 2 | ↑ 1 |

### Per-prompt p50 wall and classification calls

| Prompt | p50 baseline | p50 Phase 2 | Wall delta | Classify calls baseline → Phase 2 |
|---|---:|---:|---:|---:|
| `heavy_pdf` | 60.353s | 50.709s | ↓16.0% | 1.00 → 0.00 |
