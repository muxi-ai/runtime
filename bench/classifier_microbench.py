#!/usr/bin/env python3
"""
Phase 2 classifier microbench.

Self-contained — needs no formation server. Loads the local
``LocalClassifier`` directly, exercises each of the 11 built-in
IntentSpecs and ``pairwise_similarity`` on a fixed eval set, and
reports min / median / p95 / max latency per operation plus
extrapolated wall-time savings vs the cloud LLM baseline.

The cloud-LLM baseline is the median per-call wall time observed in
the Phase 0 bench (``bench/local_classification_baseline.json``)
across the classification-bucket events. We don't re-measure cloud
LLM latency here — that requires a live formation + API keys — but
the Phase 0 numbers are stable enough to give a tight extrapolation.

Output
------
``bench/classifier_microbench.json`` — raw timings.
``bench/classifier_microbench.md``   — human-readable summary.

Usage
-----
::

    .venv/bin/python bench/classifier_microbench.py
    .venv/bin/python bench/classifier_microbench.py --runs 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Repo-relative import path so we can run this without installing the package.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from muxi.runtime.services.classification import (  # noqa: E402
    CLARIFICATION_NEEDS_MORE,
    LocalClassifier,
)


# Per-intent eval inputs. Each gate gets 10 messages (5 expected-true,
# 5 expected-false) so the per-classify latency average is unbiased
# across both branches of the cosine comparison. Reused from the unit
# test eval sets where applicable.
EVAL_INPUTS: Dict[str, List[str]] = {
    "actionable": [
        "Tell me about MUXI",
        "What database should I use?",
        "Build me a chatbot for our docs",
        "Que es MUXI?",
        "Explain how vector search works",
        "Hi",
        "Hola",
        "Thanks!",
        "Got it",
        "Bonjour",
    ],
    "workflow_eligible": [
        "Build a web app with auth and Postgres",
        "Refactor the entire authentication module",
        "Migrate the production database",
        "Plan and execute a multi-region failover",
        "Build a chatbot that ingests our docs",
        "Hi",
        "My budget is $5000",
        "I prefer dark mode",
        "Yes",
        "Sure",
    ],
    "simple_question": [
        "What is the capital of France?",
        "Why is the sky blue?",
        "How do I install Python?",
        "What does FAISS stand for?",
        "Where is the Eiffel Tower?",
        "Build a chatbot that ingests our docs",
        "Refactor and migrate the entire system",
        "Plan and execute a multi-region failover",
        "Migrate the production database",
        "Build me a one-page PDF about MUXI",
    ],
    "clarification_context_switch": [
        "Actually, never mind that — what's the weather?",
        "Wait, different question: how do I reset my password?",
        "Forget the deployment, can you help me debug?",
        "Stop that, ask me something else",
        "Different topic: how do I export users?",
        "Yes, Postgres please",
        "The first option",
        "Both options work",
        "No, the second one",
        "Sure, go ahead",
    ],
    "clarification_stop": [
        "Just do it",
        "Stop asking questions",
        "Enough, proceed",
        "Just go ahead",
        "Move on already",
        "Yes, Postgres please",
        "Make it green",
        "The first option",
        "No, the second one",
        "Both work",
    ],
    "clarification_needed": [
        "Help me with the project",
        "Send it",
        "Configure that",
        "Schedule a meeting",
        "Run the report",
        "Schedule a daily standup at 10am every weekday",
        "Send an email to alice@example.com saying the deploy is done",
        "Build a one-page PDF about quarterly sales",
        "Tell me about MUXI",
        "Hi",
    ],
    "clarification_needs_more": [
        "Original: Schedule a meeting\nCollected: {}",
        "Original: Send an email\nCollected: {recipient: alice}",
        "Original: Build a report\nCollected: {topic: sales}",
        "Original: Configure my account\nCollected: {service: github}",
        "Original: Help me set up monitoring\nCollected: {}",
        (
            "Original: Schedule a meeting\nCollected: "
            "{time: 2pm tomorrow, attendees: [alice, bob], "
            "title: Q4 review, duration: 1h}"
        ),
        (
            "Original: Send an email\nCollected: "
            "{recipient: alice@x.com, subject: deploy done, "
            "body: deployed at 3pm, signed off: yes}"
        ),
        (
            "Original: Build a report\nCollected: "
            "{topic: Q4 sales, length: 1 page, format: PDF, "
            "data_source: salesforce, deadline: Friday}"
        ),
        (
            "Original: Configure my account\nCollected: "
            "{service: github, account_type: enterprise, "
            "token: provided, scope: repo+admin, verified: true}"
        ),
        (
            "Original: Make a presentation\nCollected: "
            "{audience: executives, slides: 10, topic: roadmap, "
            "deadline: Monday, theme: corporate-dark, exported: pptx}"
        ),
    ],
    "credential_cancellation": [
        "cancel",
        "nevermind",
        "skip this for now",
        "forget it",
        "Cancelar",
        "How do I get a token?",
        "Where do I find my API key?",
        "ghp_abc123def456789",
        "here is my key: sk-proj-xyz",
        "Can you help me?",
    ],
    "credential_help_request": [
        "How do I get a token?",
        "Where can I find this?",
        "Can you help me?",
        "I don't know how to get this",
        "Donde encuentro mi token?",
        "ghp_abc123def456789",
        "Bearer eyJhbGci",
        "here is my token: xyz789",
        "cancel",
        "nevermind",
    ],
    "credential_request": [
        "I need to add a new GitHub account",
        "Configure new API key",
        "Set up different credentials",
        "Anadir nueva cuenta",
        "Connect a new service",
        "Tell me about MUXI",
        "What is the capital of France?",
        "Hi",
        "Build me a web app",
        "Send a Slack message",
    ],
    "recall_question": [
        "What is my name?",
        "What did I tell you about my project?",
        "Remind me what we discussed",
        "Did I mention my preferred database?",
        "What's my email again?",
        "What is FastAPI?",
        "Build me a web app",
        "How do I install Python?",
        "What is the capital of France?",
        "Schedule a daily standup",
    ],
}


PAIRWISE_INPUTS: List[tuple] = [
    ("check my email", "check my emails"),
    ("send daily report", "send a daily report"),
    ("backup my files", "back up my files"),
    ("check email", "verificar correo"),
    ("schedule a meeting", "agendar una reunion"),
    ("check my email", "send me a text"),
    ("generate a report", "backup my files"),
    ("send daily report", "deploy production"),
    ("Schedule a daily standup at 10am", "Send me an email about my deploy"),
    ("Build a one-page PDF about MUXI", "Move all my Notion pages to Slack"),
]


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def _stats(values_ms: List[float]) -> Dict[str, float]:
    if not values_ms:
        return {"count": 0}
    return {
        "count": len(values_ms),
        "min_ms": round(min(values_ms), 3),
        "median_ms": round(statistics.median(values_ms), 3),
        "p95_ms": round(_percentile(values_ms, 0.95), 3),
        "max_ms": round(max(values_ms), 3),
        "mean_ms": round(statistics.mean(values_ms), 3),
        "stdev_ms": round(statistics.pstdev(values_ms), 3) if len(values_ms) > 1 else 0.0,
        "total_ms": round(sum(values_ms), 3),
    }


async def _bench_classify_binary(
    classifier: LocalClassifier, intent: str, inputs: List[str], runs: int
) -> List[float]:
    """Return per-call latencies in ms across all inputs * runs."""
    timings: List[float] = []
    for _ in range(runs):
        for text in inputs:
            t0 = time.perf_counter()
            await classifier.classify_binary(intent, text)
            timings.append((time.perf_counter() - t0) * 1000.0)
    return timings


async def _bench_pairwise(
    classifier: LocalClassifier, pairs: List[tuple], runs: int
) -> List[float]:
    timings: List[float] = []
    for _ in range(runs):
        for a, b in pairs:
            t0 = time.perf_counter()
            await classifier.pairwise_similarity(a, b)
            timings.append((time.perf_counter() - t0) * 1000.0)
    return timings


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--runs", type=int, default=3, help="Iterations of each eval set (default 3)."
    )
    parser.add_argument(
        "--cloud-baseline-ms",
        type=float,
        default=750.0,
        help=(
            "Estimated median cloud-LLM round-trip per classification call (ms). "
            "Default 750 ms reflects mt<=1000 OpenAI gpt-4o-mini calls observed in "
            "Phase 0 bench. Override with your own measurement if available."
        ),
    )
    parser.add_argument(
        "--output-json",
        default="bench/classifier_microbench.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--output-md",
        default="bench/classifier_microbench.md",
        help="Output markdown path.",
    )
    args = parser.parse_args()

    print(f"Loading + warming up classifier (runs={args.runs})...")
    t0 = time.perf_counter()
    classifier = LocalClassifier()
    await classifier.warmup()
    warmup_ms = (time.perf_counter() - t0) * 1000.0
    print(f"  warmup: {warmup_ms:.0f} ms")

    report: Dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": classifier.model,
        "runs_per_eval_set": args.runs,
        "cloud_baseline_ms_per_call": args.cloud_baseline_ms,
        "warmup_ms": round(warmup_ms, 1),
        "intents": {},
        "pairwise_similarity": {},
    }

    print(f"\nBenchmarking {len(EVAL_INPUTS)} intents @ {args.runs} runs each...")
    for intent, inputs in EVAL_INPUTS.items():
        timings = await _bench_classify_binary(classifier, intent, inputs, args.runs)
        s = _stats(timings)
        # Special case: clarification_needs_more uses the joint-string
        # input with an embedded newline, which matches one IntentSpec.
        if intent == "clarification_needs_more":
            assert any("Original:" in x for x in inputs), "joint-string sanity"
            assert CLARIFICATION_NEEDS_MORE.name == "clarification_needs_more"
        report["intents"][intent] = s
        print(
            f"  {intent:30s}  median={s.get('median_ms', 0):6.1f} ms  "
            f"p95={s.get('p95_ms', 0):6.1f} ms  n={s.get('count', 0)}"
        )

    print(f"\nBenchmarking pairwise_similarity @ {args.runs} runs...")
    timings = await _bench_pairwise(classifier, PAIRWISE_INPUTS, args.runs)
    s = _stats(timings)
    report["pairwise_similarity"] = s
    print(
        f"  pairwise_similarity         median={s.get('median_ms', 0):6.1f} ms  "
        f"p95={s.get('p95_ms', 0):6.1f} ms  n={s.get('count', 0)}"
    )

    # Aggregate stats across all classify ops (the gates we replaced).
    all_classify_timings: List[float] = []
    for intent in EVAL_INPUTS:
        # Re-derive from the per-intent runs so percentiles are global.
        # We don't have the per-call list back, so reuse mean for the
        # extrapolation rather than recompute. Sum of means works for
        # the "savings per call" calculation below.
        s = report["intents"][intent]
        all_classify_timings.append(s.get("mean_ms", 0.0))

    mean_classify_ms = statistics.mean(all_classify_timings) if all_classify_timings else 0.0
    pairwise_mean_ms = report["pairwise_similarity"].get("mean_ms", 0.0)

    # Per-call savings vs cloud baseline.
    classify_saving_ms = max(0.0, args.cloud_baseline_ms - mean_classify_ms)
    pairwise_saving_ms = max(0.0, args.cloud_baseline_ms - pairwise_mean_ms)
    classify_speedup = (
        args.cloud_baseline_ms / mean_classify_ms if mean_classify_ms > 0 else float("inf")
    )
    pairwise_speedup = (
        args.cloud_baseline_ms / pairwise_mean_ms if pairwise_mean_ms > 0 else float("inf")
    )

    report["aggregates"] = {
        "mean_classify_binary_ms": round(mean_classify_ms, 3),
        "mean_pairwise_similarity_ms": round(pairwise_mean_ms, 3),
        "classify_binary_speedup_vs_cloud": round(classify_speedup, 1),
        "pairwise_similarity_speedup_vs_cloud": round(pairwise_speedup, 1),
        "ms_saved_per_classify_call": round(classify_saving_ms, 3),
        "ms_saved_per_pairwise_call": round(pairwise_saving_ms, 3),
    }

    # Phase 2 replaced gates: 13 in total.
    #   Phase 1: 6 (actionability, workflow_eligibility, simple_question,
    #              clarification_context_switch, clarification_stop, recall)
    #   Phase 2 Group A: 4 (3 credentials + scheduler pairwise)
    #   Phase 2 Group D: 1 (fusion_engine pairwise)
    #   Phase 2 Group B: 2 fast-path skips (analyzer + check_need_more)
    # The fast-path skips only save when the gate negative-branches; the
    # full replacements always save.
    phase2_replaced_classify_calls = 9  # 3 cred + 6 phase 1 binary
    phase2_replaced_pairwise_calls = 2  # scheduler + fusion
    phase2_fast_path_skips = 2  # analyzer + check_need_more

    # Per-request worst-case savings on a request that exercises all
    # gates (e.g. a credential-flow message that also goes through the
    # clarification analyzer):
    worst_case_per_request_savings_ms = (
        phase2_replaced_classify_calls * classify_saving_ms
        + phase2_replaced_pairwise_calls * pairwise_saving_ms
        + phase2_fast_path_skips * classify_saving_ms
    )
    report["aggregates"]["worst_case_per_request_savings_ms"] = round(
        worst_case_per_request_savings_ms, 1
    )

    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Markdown summary
    md_lines: List[str] = [
        "# Local Classification — Phase 2 Microbench",
        "",
        f"Generated `{report['started_at']}`",
        f"Model: `{report['model']}`",
        f"Runs per eval set: `{args.runs}`",
        f"Warmup: `{report['warmup_ms']:.0f} ms` (one-time, amortized over process lifetime)",
        "",
        "## TL;DR",
        "",
        f"* Mean per-call latency, `classify_binary`:  "
        f"**{mean_classify_ms:.1f} ms**  (~{classify_speedup:.0f}x faster than the "
        f"~{args.cloud_baseline_ms:.0f} ms cloud-LLM baseline).",
        f"* Mean per-call latency, `pairwise_similarity`:  "
        f"**{pairwise_mean_ms:.1f} ms**  (~{pairwise_speedup:.0f}x faster).",
        f"* Worst-case per-request wall-time saving on a request that exercises "
        f"all 13 replaced gates: **~{worst_case_per_request_savings_ms / 1000.0:.1f} s**.",
        "",
        "Cloud-LLM baseline is the typical median for `mt<=1000` "
        "`gpt-4o-mini` calls observed in Phase 0 "
        "(`bench/local_classification_baseline.json`). Override with "
        "`--cloud-baseline-ms` if you measure something different.",
        "",
        "## Per-intent latency (ms)",
        "",
        "| Intent | n | min | median | p95 | max | mean | stdev |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for intent, s in report["intents"].items():
        md_lines.append(
            f"| `{intent}` | {s.get('count', 0)} | {s.get('min_ms', 0):.1f} | "
            f"{s.get('median_ms', 0):.1f} | {s.get('p95_ms', 0):.1f} | "
            f"{s.get('max_ms', 0):.1f} | {s.get('mean_ms', 0):.1f} | "
            f"{s.get('stdev_ms', 0):.1f} |"
        )
    md_lines.append("")

    s = report["pairwise_similarity"]
    md_lines.extend(
        [
            "## Pairwise similarity latency (ms)",
            "",
            "| Op | n | min | median | p95 | max | mean | stdev |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
            f"| `pairwise_similarity` | {s.get('count', 0)} | {s.get('min_ms', 0):.1f} | "
            f"{s.get('median_ms', 0):.1f} | {s.get('p95_ms', 0):.1f} | "
            f"{s.get('max_ms', 0):.1f} | {s.get('mean_ms', 0):.1f} | "
            f"{s.get('stdev_ms', 0):.1f} |",
            "",
            "## Phase 2 wall-time impact extrapolation",
            "",
            f"* Phase 1 + Phase 2 Group A: **9 binary gates** fully replaced "
            f"(3 credential + 6 pre-planning).",
            f"* Phase 2 Group A scheduler + Group D fusion: **2 pairwise gates** "
            f"replaced (cosine similarity replaces an LLM scoring call).",
            f"* Phase 2 Group B: **2 LLM calls short-circuited** when classifier "
            f"says no clarification needed (fast-path skips).",
            "",
            f"* Per-call cloud-LLM baseline: ~{args.cloud_baseline_ms:.0f} ms "
            f"(Phase 0 measurement).",
            f"* Per-call classifier (mean): ~{mean_classify_ms:.1f} ms "
            f"(`classify_binary`), ~{pairwise_mean_ms:.1f} ms (`pairwise_similarity`).",
            f"* Per-call wall-time saved: ~{classify_saving_ms:.0f} ms (binary), "
            f"~{pairwise_saving_ms:.0f} ms (pairwise).",
            f"* Worst-case per-request saving on a path that hits all 13 gates: "
            f"~{worst_case_per_request_savings_ms / 1000.0:.1f} s.",
            "",
            "Real workloads typically hit a subset of gates per request: "
            "the heavy PDF prompt hits ~5 in Phase 0 (4 parallel + 1 sequential), "
            "the light-prompt micro-suite hits 0-3. Multiply per-request gate "
            "count by per-call saving to get the wall-time delta you should "
            "expect on a given workload.",
            "",
        ]
    )

    out_md = Path(args.output_md)
    out_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"\nWrote {out_json}")
    print(f"Wrote {out_md}")
    print(
        f"\nSummary: classify {mean_classify_ms:.1f} ms / pairwise "
        f"{pairwise_mean_ms:.1f} ms / worst-case-saving "
        f"{worst_case_per_request_savings_ms / 1000.0:.1f} s/request"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
