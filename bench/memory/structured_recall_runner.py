#!/usr/bin/env python3
"""Structured-recall benchmark runner (Tier 2).

Runs the MUXI structured-recall dataset (five categories: KG
relationship recall, temporal validity, Captain's-Log narrative
recall, cross-agent knowledge, contradiction detection) against a
real MUXI formation. Two families of modes:

- ``working`` / ``persistent`` / ``combined`` — the Tier 1 vector
  retrieval baselines, unchanged, so structured retrieval has an
  apples-to-apples comparison.
- ``structured`` — Knowledge Graph + Captain's Log retrieval over the
  ground-truth manifest (no LLM extraction; see
  ``structured_adapter.py`` for the Tier 3 seam), plus the KG
  contradiction-detection audit (precision/recall).

Every run also measures **exact-string recall** (emails, ticket
codes, invoice ids present verbatim in retrieved context) — the
decision input for memory-revamp Phase 6 (hybrid/BM25 search). Missed
exact-string questions are listed explicitly in the summary.

Usage
-----
::

    # Committed fixture sample (CI-safe, no downloads)
    uv run python -m bench.memory.structured_recall_runner --fixture
    uv run python -m bench.memory.structured_recall_runner --fixture --mode structured

    # Full generated dataset
    uv run python -m bench.memory.structured_corpus --preset full \
        --output ~/datasets/membench/structured_recall_full.json
    uv run python -m bench.memory.structured_recall_runner \
        --dataset ~/datasets/membench/structured_recall_full.json --mode structured --qa
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

if __package__ in (None, ""):  # direct script invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.memory.adapter import DEFAULT_FORMATION_YAML  # noqa: E402
from bench.memory.report import build_report, render_summary, write_report  # noqa: E402
from bench.memory.runner import (  # noqa: E402
    FIXTURES_DIR,
    MAX_CONSECUTIVE_CASE_FAILURES,
    REPO_ROOT,
    RESULTS_DIR,
    _limit_dataset,
)
from bench.memory.split import DEFAULT_DEV_SIZE, DEFAULT_SEED, select_split  # noqa: E402
from bench.memory.structured_adapter import (  # noqa: E402
    MODES,
    STRUCTURED_MODE,
    StructuredMemoryAdapter,
)
from bench.memory.structured_dataset import (  # noqa: E402
    BENCHMARK_NAME,
    StructuredGroundTruth,
    load_structured_recall,
)
from bench.memory.structured_scoring import (  # noqa: E402
    ContradictionCaseResult,
    StructuredQuestionResult,
    aggregate_structured_results,
    exact_string_rank,
    render_structured_summary_extras,
)

DEFAULT_K = 5
FIXTURE_FILENAME = "structured_recall_sample.json"


def fixture_path() -> Path:
    return FIXTURES_DIR / FIXTURE_FILENAME


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Tier 2 structured-recall benchmark against a real MUXI "
            "formation. Defaults to the committed fixture sample; generate a "
            "full dataset with bench.memory.structured_corpus for publishable "
            "numbers."
        )
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Path to a structured-recall dataset JSON (default: committed fixture).",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Force the committed fixture sample.",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="combined",
        help=(
            "Retrieval mode: working/persistent/combined (vector baselines) or "
            "structured (Knowledge Graph + Captain's Log)."
        ),
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="Recall@K cutoff.")
    parser.add_argument(
        "--fetch-limit",
        type=int,
        default=None,
        help="Results fetched per query (default: max(25, 5*k)).",
    )
    parser.add_argument(
        "--qa",
        action="store_true",
        help="Also measure end-to-end QA accuracy (answer + LLM judge; costs tokens).",
    )
    parser.add_argument(
        "--qa-context",
        type=int,
        default=10,
        help="Retrieved excerpts injected into the QA answer prompt.",
    )
    parser.add_argument(
        "--split",
        choices=("dev", "holdout", "all"),
        default="all",
        help="Question split to run (seeded dev split as in Tier 1).",
    )
    parser.add_argument("--dev-size", type=int, default=DEFAULT_DEV_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Split shuffle seed.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N questions (after split selection); for smoke runs.",
    )
    parser.add_argument("--formation", default=str(DEFAULT_FORMATION_YAML))
    parser.add_argument("--run-dir", default=None)
    parser.add_argument(
        "--keep-run-dir",
        action="store_true",
        help="Keep the temp run dir (also honored via MUXI_BENCH_KEEP_RUN_DIR=1).",
    )
    parser.add_argument("--secrets-dir", default=None)
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Report JSON path (default: bench/memory/results/"
            f"{BENCHMARK_NAME}_<mode>_<split>.json for fixture runs, timestamped otherwise)."
        ),
    )
    return parser


def default_output_path(mode: str, split: str, used_fixture: bool) -> Path:
    if used_fixture:
        return RESULTS_DIR / f"{BENCHMARK_NAME}_fixture_{mode}.json"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return RESULTS_DIR / f"{BENCHMARK_NAME}_{mode}_{split}_{stamp}.json"


async def run_benchmark(args: argparse.Namespace) -> int:
    """Execute one structured-recall run end-to-end; returns the exit code."""
    dataset_path = Path(args.dataset) if (args.dataset and not args.fixture) else fixture_path()
    used_fixture = dataset_path == fixture_path()
    dataset, ground_truth = load_structured_recall(dataset_path)
    dataset = select_split(dataset, args.split, dev_size=args.dev_size, seed=args.seed)
    dataset = _limit_dataset(dataset, args.limit)
    if dataset.question_count == 0:
        print("No questions selected (check --split / --limit).", file=sys.stderr)
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
        f"{len(dataset.cases)} cases (split={args.split}, mode={args.mode}, "
        f"fixture={used_fixture})"
    )

    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    results: List[StructuredQuestionResult] = []
    contradiction_cases: List[ContradictionCaseResult] = []
    partial = False
    report_failed = False
    abort_reason: Optional[str] = None
    cases_completed = 0
    cases_failed = 0
    consecutive_failures = 0
    usage: Dict = {}
    config: Dict = {}
    metrics: Dict = {}

    # Same failure envelope as the Tier 1 runner: the report is built and
    # written in the finally path, so EVERY exit — clean finish, early
    # abort, crash, KeyboardInterrupt — leaves a report with whatever
    # completed (marked ``partial`` when cut short).
    try:
        await adapter.start()
        for case_index, case in enumerate(dataset.cases, start=1):
            adapter.clear_case()
            user_id = f"bench-{BENCHMARK_NAME}-{case.case_id}"
            truth = ground_truth.get(case.case_id) or StructuredGroundTruth(
                case_id=case.case_id, scenario="unknown"
            )

            # Per-case ingestion failure isolation (Tier 1 pattern).
            try:
                if args.mode == STRUCTURED_MODE:
                    await adapter.ingest_ground_truth(user_id, truth)
                else:
                    for session in case.sessions:
                        await adapter.ingest_session(user_id, session)
            except Exception as exc:
                cases_failed += 1
                consecutive_failures += 1
                error = f"case ingestion failed: {type(exc).__name__}: {exc}"
                for question in case.questions:
                    results.append(
                        StructuredQuestionResult(
                            question_id=question.question_id,
                            question_type=question.question_type,
                            is_abstention=question.is_abstention,
                            evidence_session_ids=list(question.evidence_session_ids),
                            evidence_turn_ids=list(question.evidence_turn_ids),
                            category=question.question_type,
                            exact_strings=list(question.exact_strings),
                            error=error,
                        )
                    )
                print(
                    f"[membench] case {case_index}/{len(dataset.cases)} FAILED "
                    f"({case.case_id}): {error}",
                    file=sys.stderr,
                )
                if consecutive_failures >= MAX_CONSECUTIVE_CASE_FAILURES:
                    partial = True
                    abort_reason = (
                        f"aborted after {consecutive_failures} consecutive case "
                        f"ingestion failures (systematic environment failure); "
                        f"last error: {error}"
                    )
                    break
                continue

            for question in case.questions:
                q_started = time.monotonic()
                result = StructuredQuestionResult(
                    question_id=question.question_id,
                    question_type=question.question_type,
                    is_abstention=question.is_abstention,
                    evidence_session_ids=list(question.evidence_session_ids),
                    evidence_turn_ids=list(question.evidence_turn_ids),
                    category=question.question_type,
                    exact_strings=list(question.exact_strings),
                )
                try:
                    items = await adapter.search_question(user_id, question, fetch_limit)
                    result.retrieved_session_ids = adapter.ranked_session_ids(items)
                    result.retrieved_turn_ids = adapter.ranked_turn_ids(items)
                    if question.exact_strings:
                        result.exact_string_rank = exact_string_rank(
                            [item.text for item in items], question.exact_strings
                        )
                    if args.qa:
                        predicted = await adapter.answer_question(
                            question, items, context_limit=args.qa_context
                        )
                        result.qa_answer = predicted
                        result.qa_correct = await adapter.judge_answer(question, predicted)
                except Exception as exc:  # keep the run alive; errors are scored
                    result.error = f"{type(exc).__name__}: {exc}"
                result.elapsed_seconds = round(time.monotonic() - q_started, 3)
                results.append(result)

            if args.mode == STRUCTURED_MODE:
                try:
                    contradiction_cases.append(await adapter.audit_contradictions(user_id, truth))
                except Exception as exc:
                    print(
                        f"[membench] contradiction audit failed ({case.case_id}): "
                        f"{type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )

            cases_completed += 1
            consecutive_failures = 0
            print(
                f"[membench] case {case_index}/{len(dataset.cases)} done "
                f"({case.case_id}: {len(case.sessions)} sessions, "
                f"{len(case.questions)} questions)"
            )
    finally:
        in_flight = sys.exc_info()[1]
        if in_flight is not None and abort_reason is None:
            partial = True
            abort_reason = f"{type(in_flight).__name__}: {in_flight}"

        try:
            usage = adapter.usage_snapshot()
            config = adapter.config_snapshot()
        except Exception:
            pass
        await adapter.stop()

        try:
            metrics = aggregate_structured_results(results, args.k, contradiction_cases)
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
                    "split": args.split,
                    "seed": args.seed,
                },
                config={**config, "fetch_limit": fetch_limit, "qa": args.qa},
                metrics=metrics,
                results=results,
                usage=usage,
                started_at=started_at,
                wall_seconds=time.monotonic() - started,
                partial=partial,
                abort_reason=abort_reason,
                case_stats={
                    "completed": cases_completed,
                    "failed": cases_failed,
                    "skipped": len(dataset.cases) - cases_completed - cases_failed,
                },
                repo_root=REPO_ROOT,
            )
            output = (
                Path(args.output)
                if args.output
                else default_output_path(args.mode, args.split, used_fixture)
            )
            write_report(report, output)
            print(render_summary(report))
            extras = render_structured_summary_extras(metrics, args.k)
            if extras:
                print(extras)
            print(f"Report written to {output}")
        except Exception as report_exc:
            report_failed = True
            print(f"[membench] failed to write report: {report_exc}", file=sys.stderr)

    return 1 if (partial or report_failed or metrics.get("questions_errored")) else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    sys.exit(main())
