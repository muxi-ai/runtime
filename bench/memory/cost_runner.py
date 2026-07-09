#!/usr/bin/env python3
"""Cost-efficiency benchmark runner (Tier 4).

Quantifies what accurate recall costs on a real MUXI formation
(memory-benchmarking PRD, Tier 4):

- **Retrieval latency** — p50/p95/p99 over a simple concurrent load
  pattern (the dataset's questions cycled up to ``--queries``, issued
  ``--concurrency`` at a time).
- **Context tokens per query** — estimated tokens injected into an
  answer prompt from the top retrieved excerpts (chars/4), the
  MemPalace-comparable "tokens per search" number. Retrieval-only
  runs cost $0 (local embeddings) and still produce this.
- **Tokens per accurate recall + cost per 1,000 queries** (with
  ``--qa``) — measured LLM tokens for answering each distinct
  question once (judge overhead excluded), divided by correct
  answers, and projected to the PRD's usage scenarios (10/50/200
  queries/day/user/month) with the pricing table in
  ``bench/memory/pricing.json``.
- **Memory footprint** — persistent DB bytes plus the working-memory
  vector estimate, per ingested turn.

The workload corpus is the Tier 2 structured-recall dataset
(committed fixture by default), so Tier 4 numbers are reproducible
without downloads.

Usage
-----
::

    # Fixture corpus, retrieval-only (no API calls)
    uv run python -m bench.memory.cost_runner --fixture

    # With QA accuracy + measured token costs
    uv run python -m bench.memory.cost_runner --fixture --qa

    # Heavier load pattern
    uv run python -m bench.memory.cost_runner --fixture --queries 1000 --concurrency 16
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __package__ in (None, ""):  # direct script invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.memory.adapter import DEFAULT_FORMATION_YAML  # noqa: E402
from bench.memory.cost_model import (  # noqa: E402
    cost_per_query_usd,
    cost_projection,
    footprint_summary,
    latency_summary,
    pricing_snapshot,
    tokens_per_accurate_recall,
)
from bench.memory.datasets import Question  # noqa: E402
from bench.memory.report import build_report, write_report  # noqa: E402
from bench.memory.runner import REPO_ROOT, RESULTS_DIR  # noqa: E402
from bench.memory.structured_adapter import MODES, StructuredMemoryAdapter  # noqa: E402
from bench.memory.structured_dataset import load_structured_recall  # noqa: E402
from bench.memory.structured_recall_runner import fixture_path  # noqa: E402

BENCHMARK_NAME = "cost_efficiency"
DEFAULT_QUERIES = 200
DEFAULT_CONCURRENCY = 8
DEFAULT_WARMUP = 5
# Rough chars-per-token for context-size estimates (OpenAI rule of thumb).
CHARS_PER_TOKEN = 4.0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Tier 4 cost-efficiency benchmark against a real MUXI "
            "formation, using the structured-recall corpus as the workload."
        )
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Structured-recall dataset JSON (default: committed fixture).",
    )
    parser.add_argument("--fixture", action="store_true", help="Force the committed fixture.")
    parser.add_argument("--mode", choices=MODES, default="combined")
    parser.add_argument(
        "--queries",
        type=int,
        default=DEFAULT_QUERIES,
        help="Total retrieval queries in the load phase (questions are cycled).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Concurrent in-flight retrievals during the load phase.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP,
        help="Warmup queries excluded from latency percentiles.",
    )
    parser.add_argument("--k", type=int, default=5, help="Excerpts counted for context tokens.")
    parser.add_argument(
        "--fetch-limit",
        type=int,
        default=None,
        help="Results fetched per query (default: max(25, 5*k)).",
    )
    parser.add_argument(
        "--qa",
        action="store_true",
        help=(
            "Answer each distinct question once (LLM + judge) to measure "
            "tokens-per-accurate-recall and priced cost per query."
        ),
    )
    parser.add_argument("--qa-context", type=int, default=10)
    parser.add_argument("--formation", default=str(DEFAULT_FORMATION_YAML))
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--keep-run-dir", action="store_true")
    parser.add_argument("--secrets-dir", default=None)
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Report JSON path (default: bench/memory/results/"
            f"{BENCHMARK_NAME}_<mode>.json for fixture runs, timestamped otherwise)."
        ),
    )
    return parser


def default_output_path(mode: str, used_fixture: bool) -> Path:
    if used_fixture:
        return RESULTS_DIR / f"{BENCHMARK_NAME}_fixture_{mode}.json"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return RESULTS_DIR / f"{BENCHMARK_NAME}_{mode}_{stamp}.json"


def _estimate_context_tokens(texts: List[str]) -> float:
    return sum(len(text) for text in texts) / CHARS_PER_TOKEN


async def _load_phase(
    adapter: StructuredMemoryAdapter,
    workload: List[Tuple[str, Question]],
    fetch_limit: int,
    concurrency: int,
    k: int,
) -> Tuple[List[float], List[float], int]:
    """Concurrent retrieval load; returns (latencies, context_tokens, errors)."""
    semaphore = asyncio.Semaphore(max(1, concurrency))
    latencies: List[float] = []
    context_tokens: List[float] = []
    errors = 0

    async def one(user_id: str, question: Question) -> None:
        nonlocal errors
        async with semaphore:
            started = time.monotonic()
            try:
                items = await adapter.search_question(user_id, question, fetch_limit)
            except Exception:
                errors += 1
                return
            latencies.append(time.monotonic() - started)
            context_tokens.append(_estimate_context_tokens([item.text for item in items[:k]]))

    await asyncio.gather(*(one(user_id, question) for user_id, question in workload))
    return latencies, context_tokens, errors


async def _qa_phase(
    adapter: StructuredMemoryAdapter,
    questions: List[Tuple[str, Question]],
    fetch_limit: int,
    qa_context: int,
) -> Dict[str, Any]:
    """Answer each distinct question once; returns the ``qa`` metrics block.

    A question enters the tallies only when the full answer + judge
    round-trip succeeds: the answer-call token delta is captured in a
    local and committed together with the question count, so a judge
    failure after a successful answer call cannot count tokens for a
    question that is never scored (which would inflate
    tokens-per-accurate-recall and skew the per-query average). Failed
    questions — answer OR judge — are excluded from BOTH numerator and
    denominator and surface under ``errors``.
    """
    qa_correct = 0
    qa_total = 0
    answer_tokens = 0
    qa_errors = 0
    for user_id, question in questions:
        try:
            items = await adapter.search_question(user_id, question, fetch_limit)
            before = adapter.usage_snapshot()["tokens"]["total"]
            predicted = await adapter.answer_question(question, items, context_limit=qa_context)
            question_tokens = adapter.usage_snapshot()["tokens"]["total"] - before
            correct = await adapter.judge_answer(question, predicted)
        except Exception:
            qa_errors += 1
            continue
        answer_tokens += question_tokens
        qa_total += 1
        qa_correct += correct
    return {
        "questions": qa_total,
        "errors": qa_errors,
        "correct": qa_correct,
        "accuracy": round(qa_correct / qa_total, 4) if qa_total else None,
        "answer_tokens": answer_tokens,
        "tokens_per_accurate_recall": (
            round(tokens_per_accurate_recall(answer_tokens, qa_correct), 1) if qa_correct else None
        ),
        "note": (
            "answer_tokens covers the answer calls of fully scored questions "
            "only (retrieval context + question + generation); judge calls are "
            "measurement overhead and excluded, and questions whose answer or "
            "judge call failed are excluded from every tally (see errors)"
        ),
    }


async def run_benchmark(args: argparse.Namespace) -> int:
    """Execute one cost-efficiency run end-to-end; returns the exit code."""
    dataset_path = Path(args.dataset) if (args.dataset and not args.fixture) else fixture_path()
    used_fixture = dataset_path == fixture_path()
    dataset, ground_truth = load_structured_recall(dataset_path)
    if dataset.question_count == 0:
        print("Dataset contains no questions.", file=sys.stderr)
        return 1

    fetch_limit = args.fetch_limit or max(25, 5 * args.k)
    adapter = StructuredMemoryAdapter(
        mode=args.mode,
        formation_yaml=Path(args.formation),
        run_dir=Path(args.run_dir) if args.run_dir else None,
        secrets_dir=Path(args.secrets_dir) if args.secrets_dir else None,
        keep_run_dir=args.keep_run_dir,
    )

    print(
        f"[membench] {BENCHMARK_NAME}: {dataset.question_count} questions / "
        f"{len(dataset.cases)} cases (mode={args.mode}, queries={args.queries}, "
        f"concurrency={args.concurrency}, qa={args.qa})"
    )

    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    partial = False
    report_failed = False
    abort_reason: Optional[str] = None
    usage: Dict[str, Any] = {}
    config: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}

    # Tier 1 failure envelope: the report is written in the finally path,
    # so every exit leaves a (possibly partial) report.
    try:
        await adapter.start()

        # -- ingest phase (all cases resident; per-case user isolation) ----
        # NOTE: unlike the recall runners, working memory is NOT cleared
        # between cases — the load phase queries all cases interleaved, so
        # every haystack must stay resident. Metadata user_id filters keep
        # per-case retrieval correct.
        ingest_started = time.monotonic()
        for case in dataset.cases:
            user_id = f"bench-{BENCHMARK_NAME}-{case.case_id}"
            if args.mode == "structured":
                truth = ground_truth[case.case_id]
                await adapter.ingest_ground_truth(user_id, truth)
            else:
                for session in case.sessions:
                    await adapter.ingest_session(user_id, session)
        ingest_seconds = time.monotonic() - ingest_started
        metrics["ingest"] = {
            "turns": adapter.ingested_turns,
            "seconds": round(ingest_seconds, 2),
            "turns_per_second": (
                round(adapter.ingested_turns / ingest_seconds, 1) if ingest_seconds else None
            ),
        }

        # -- load phase (cycled questions, bounded concurrency) ------------
        questions: List[Tuple[str, Question]] = [
            (f"bench-{BENCHMARK_NAME}-{case.case_id}", question)
            for case, question in dataset.iter_questions()
        ]
        workload = [questions[i % len(questions)] for i in range(max(0, args.queries))]
        warmup = [questions[i % len(questions)] for i in range(max(0, args.warmup))]
        if warmup:
            await _load_phase(adapter, warmup, fetch_limit, 1, args.k)

        load_started = time.monotonic()
        latencies, context_tokens, load_errors = await _load_phase(
            adapter, workload, fetch_limit, args.concurrency, args.k
        )
        load_seconds = time.monotonic() - load_started
        metrics["load"] = {
            "queries": len(workload),
            "errors": load_errors,
            "concurrency": args.concurrency,
            "warmup_queries": len(warmup),
            "seconds": round(load_seconds, 2),
            "queries_per_second": (
                round(len(latencies) / load_seconds, 1) if load_seconds else None
            ),
        }
        metrics["latency"] = {"retrieval": latency_summary(latencies)}
        metrics["context_tokens"] = {
            "k": args.k,
            "estimated_avg_per_query": (
                round(sum(context_tokens) / len(context_tokens), 1) if context_tokens else None
            ),
            "note": f"chars/{CHARS_PER_TOKEN:.0f} estimate over the top-{args.k} excerpts",
        }

        # -- QA phase (distinct questions once, sequential) ----------------
        if args.qa:
            metrics["qa"] = await _qa_phase(
                adapter, questions, fetch_limit, qa_context=args.qa_context
            )
            qa_total = metrics["qa"]["questions"]

            # Priced cost per query: answer-model tokens averaged over the
            # QA questions (retrieval itself is free with local embeddings).
            snapshot = adapter.usage_snapshot()
            per_query_breakdown = {}
            if qa_total:
                text_model = adapter.config_snapshot().get("text_model")
                for model, fields in snapshot["tokens_by_model"].items():
                    if text_model and model != text_model:
                        continue
                    per_query_breakdown[model] = [field / qa_total for field in fields]
            per_query = cost_per_query_usd(per_query_breakdown) if per_query_breakdown else None
            metrics["cost"] = cost_projection(per_query)
            metrics["cost"]["note"] = (
                "list-price projection of the measured answer-call tokens; "
                "includes judge overhead in tokens_by_model but not in per-query cost "
                "when the judge shares the text model (they are averaged together - "
                "treat as an upper bound)"
            )
        else:
            metrics["cost"] = cost_projection(0.0)
            metrics["cost"]["note"] = (
                "retrieval-only run: $0 API spend with local embeddings; "
                "run with --qa for measured tokens-per-accurate-recall"
            )

        # -- footprint (measured before teardown) ---------------------------
        db_path = adapter.run_dir / "membench.db" if adapter.run_dir else None
        db_bytes = db_path.stat().st_size if db_path and db_path.exists() else 0
        buffer = adapter.overlord.buffer_memory if adapter.overlord else None
        metrics["footprint"] = footprint_summary(
            db_bytes=db_bytes,
            working_memory_items=(buffer.index_count if buffer is not None else 0),
            embedding_dimension=(buffer.dimension if buffer is not None else 0),
            ingested_turns=adapter.ingested_turns,
        )
        metrics["pricing"] = pricing_snapshot()
    finally:
        in_flight = sys.exc_info()[1]
        if in_flight is not None:
            partial = True
            abort_reason = f"{type(in_flight).__name__}: {in_flight}"

        try:
            usage = adapter.usage_snapshot()
            config = adapter.config_snapshot()
        except Exception:
            pass
        await adapter.stop()

        try:
            report = build_report(
                benchmark=BENCHMARK_NAME,
                mode=args.mode,
                k=args.k,
                dataset_path=str(dataset_path),
                dataset_stats={
                    "cases": len(dataset.cases),
                    "questions": dataset.question_count,
                    "sessions": dataset.session_count,
                    "fixture": used_fixture,
                },
                config={
                    **config,
                    "fetch_limit": fetch_limit,
                    "qa": args.qa,
                    "queries": args.queries,
                    "concurrency": args.concurrency,
                    "warmup": args.warmup,
                },
                metrics=metrics,
                results=[],
                usage=usage,
                started_at=started_at,
                wall_seconds=time.monotonic() - started,
                partial=partial,
                abort_reason=abort_reason,
                repo_root=REPO_ROOT,
            )
            output = (
                Path(args.output) if args.output else default_output_path(args.mode, used_fixture)
            )
            write_report(report, output)
            print(render_cost_summary(report))
            print(f"Report written to {output}")
        except Exception as report_exc:
            report_failed = True
            print(f"[membench] failed to write report: {report_exc}", file=sys.stderr)

    load_errors = (metrics.get("load") or {}).get("errors", 0)
    return 1 if (partial or report_failed or load_errors) else 0


def render_cost_summary(report: Dict[str, Any]) -> str:
    """Human-readable stdout summary for a cost-efficiency run."""
    metrics = report["metrics"]
    lines: List[str] = []
    lines.append("=" * 64)
    lines.append(f"Memory benchmark: {report['benchmark']}  (mode={report['mode']})")
    lines.append("=" * 64)
    dataset = report["dataset"]
    lines.append(
        f"Dataset: {dataset['path']}  "
        f"(cases={dataset.get('cases', '?')}, questions={dataset.get('questions', '?')})"
    )
    if report.get("partial"):
        lines.append("")
        lines.append(f"PARTIAL RUN — aborted: {report['run'].get('abort_reason')}")

    ingest = metrics.get("ingest")
    if ingest:
        lines.append(
            f"Ingest: {ingest['turns']} turns in {ingest['seconds']}s "
            f"({ingest['turns_per_second']} turns/s)"
        )
    load = metrics.get("load")
    if load:
        lines.append(
            f"Load: {load['queries']} queries @ concurrency {load['concurrency']} "
            f"in {load['seconds']}s ({load['queries_per_second']} q/s, "
            f"errors={load['errors']})"
        )
    latency = (metrics.get("latency") or {}).get("retrieval")
    if latency:
        lines.append("")
        lines.append(
            f"Retrieval latency: p50={latency['p50_ms']}ms  p95={latency['p95_ms']}ms  "
            f"p99={latency['p99_ms']}ms  (mean={latency['mean_ms']}ms, "
            f"n={latency['samples']})"
        )
    context = metrics.get("context_tokens")
    if context and context.get("estimated_avg_per_query") is not None:
        lines.append(
            f"Context tokens (est., top-{context['k']}): "
            f"{context['estimated_avg_per_query']} per query"
        )
    qa = metrics.get("qa")
    if qa:
        lines.append("")
        accuracy = qa["accuracy"]
        lines.append(
            f"QA: {qa['correct']}/{qa['questions']} correct " f"({accuracy * 100:.1f}%)"
            if accuracy is not None
            else "QA: no questions scored"
        )
        lines.append(
            f"Tokens per accurate recall: {qa['tokens_per_accurate_recall']}"
            if qa["tokens_per_accurate_recall"] is not None
            else "Tokens per accurate recall: n/a (no correct answers)"
        )
    cost = metrics.get("cost")
    if cost:
        lines.append("")
        per_1000 = cost.get("per_1000_queries_usd")
        lines.append(
            f"Cost per 1,000 queries: "
            f"{'$' + format(per_1000, '.4f') if per_1000 is not None else 'n/a'}"
        )
        for name, scenario in (cost.get("scenarios") or {}).items():
            monthly = scenario.get("monthly_usd")
            lines.append(
                f"  {name:<10} {scenario['queries_per_day']:>4}/day  "
                f"monthly={'$' + format(monthly, '.4f') if monthly is not None else 'n/a'}"
            )
    footprint = metrics.get("footprint")
    if footprint:
        lines.append("")
        lines.append(
            f"Footprint: db={footprint['persistent_db_bytes']}B  "
            f"working-memory vectors={footprint['working_memory_vector_bytes']}B  "
            f"({footprint['bytes_per_ingested_turn']} B/turn over "
            f"{footprint['ingested_turns']} turns)"
        )
    usage = report.get("usage") or {}
    tokens = usage.get("tokens") or {}
    est = (usage.get("cost") or {}).get("estimated_usd")
    lines.append("")
    lines.append(
        f"LLM usage: requests={usage.get('llm_requests', 0)}  "
        f"tokens_in={tokens.get('in', 0)}  tokens_out={tokens.get('out', 0)}  "
        f"est_cost=${est if est is not None else 'n/a'}"
    )
    lines.append(f"Wall time: {report['run']['wall_seconds']}s")
    lines.append("=" * 64)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    sys.exit(main())
