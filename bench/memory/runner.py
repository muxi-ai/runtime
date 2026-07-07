"""Shared run loop and CLI for the Tier 1 memory benchmark runners.

The dataset-specific entry points (``longmemeval_runner.py``,
``locomo_runner.py``, ``convomem_runner.py``) only pick the loader and
defaults; everything else — ingestion, retrieval, scoring, QA, report
writing — lives here so the three benchmarks stay comparable.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from .adapter import DEFAULT_FORMATION_YAML, MODES, MuxiMemoryAdapter
from .datasets import BenchmarkDataset, load_dataset
from .report import build_report, render_summary, write_report
from .scoring import QuestionResult, aggregate_results
from .split import DEFAULT_DEV_SIZE, DEFAULT_SEED, select_split

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

DATA_DIR_ENV = "MUXI_BENCH_DATA_DIR"

DATASET_FILENAMES = {
    "longmemeval": "longmemeval_s_cleaned.json",
    "locomo": "locomo10.json",
    "convomem": "convomem.json",
}

FIXTURE_FILENAMES = {
    "longmemeval": "longmemeval_sample.json",
    "locomo": "locomo_sample.json",
    "convomem": "convomem_sample.json",
}


def default_dataset_path(benchmark: str) -> Optional[Path]:
    """Resolve the full dataset from ``$MUXI_BENCH_DATA_DIR`` if present."""
    data_dir = os.environ.get(DATA_DIR_ENV)
    if not data_dir:
        return None
    candidate = Path(data_dir) / DATASET_FILENAMES[benchmark]
    return candidate if candidate.exists() else None


def fixture_path(benchmark: str) -> Path:
    return FIXTURES_DIR / FIXTURE_FILENAMES[benchmark]


def build_arg_parser(benchmark: str, default_k: int) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Run the {benchmark} memory benchmark against a real MUXI formation. "
            "Defaults to the committed fixture sample; point --dataset (or "
            f"${DATA_DIR_ENV}) at the full dataset for publishable numbers."
        )
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help=(
            "Path to the dataset JSON. Defaults to "
            f"${DATA_DIR_ENV}/{DATASET_FILENAMES[benchmark]} when set, "
            "otherwise the committed fixture sample."
        ),
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Force the committed fixture sample even when a full dataset is available.",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="combined",
        help="Retrieval mode: working (FAISS), persistent (SQLite), or combined (RRF).",
    )
    parser.add_argument("--k", type=int, default=default_k, help="Recall@K cutoff.")
    parser.add_argument(
        "--fetch-limit",
        type=int,
        default=None,
        help="Turn-level results fetched per query (default: max(25, 5*k)).",
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
        help="Question split to run (seeded 50-question dev split per the PRD).",
    )
    parser.add_argument("--dev-size", type=int, default=DEFAULT_DEV_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Split shuffle seed.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N questions (after split selection); for smoke runs.",
    )
    parser.add_argument(
        "--formation",
        default=str(DEFAULT_FORMATION_YAML),
        help="Benchmark formation YAML (SQLite + local embeddings by default).",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Run directory for the rendered formation + SQLite DB (default: temp dir).",
    )
    parser.add_argument(
        "--secrets-dir",
        default=None,
        help="Directory holding .key/secrets.enc (default: <repo>/e2e/assets).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Report JSON path (default: bench/memory/results/"
            f"{benchmark}_<mode>_<split>.json for fixture runs, timestamped otherwise)."
        ),
    )
    return parser


def _limit_dataset(dataset: BenchmarkDataset, limit: Optional[int]) -> BenchmarkDataset:
    if limit is None:
        return dataset
    kept = []
    remaining = limit
    for case in dataset.cases:
        if remaining <= 0:
            break
        questions = case.questions[:remaining]
        remaining -= len(questions)
        kept.append(type(case)(case_id=case.case_id, sessions=case.sessions, questions=questions))
    return BenchmarkDataset(name=dataset.name, cases=tuple(kept))


def resolve_dataset(benchmark: str, args: argparse.Namespace) -> tuple:
    """Return ``(dataset, dataset_path, used_fixture)`` per CLI selection."""
    if args.fixture or args.dataset is None:
        path = Path(args.dataset) if args.dataset else None
        if args.fixture or path is None:
            full = None if args.fixture else default_dataset_path(benchmark)
            path = full or fixture_path(benchmark)
    else:
        path = Path(args.dataset)
    used_fixture = path == fixture_path(benchmark)
    dataset = load_dataset(benchmark, path)
    return dataset, path, used_fixture


def default_output_path(benchmark: str, mode: str, split: str, used_fixture: bool) -> Path:
    if used_fixture:
        return RESULTS_DIR / f"{benchmark}_fixture_{mode}.json"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return RESULTS_DIR / f"{benchmark}_{mode}_{split}_{stamp}.json"


async def run_benchmark(benchmark: str, args: argparse.Namespace) -> int:
    """Execute one benchmark run end-to-end. Returns the process exit code."""
    dataset, dataset_path, used_fixture = resolve_dataset(benchmark, args)
    dataset = select_split(dataset, args.split, dev_size=args.dev_size, seed=args.seed)
    dataset = _limit_dataset(dataset, args.limit)
    if dataset.question_count == 0:
        print("No questions selected (check --split / --limit).", file=sys.stderr)
        return 1

    fetch_limit = args.fetch_limit or max(25, 5 * args.k)
    adapter = MuxiMemoryAdapter(
        mode=args.mode,
        formation_yaml=Path(args.formation),
        run_dir=Path(args.run_dir) if args.run_dir else None,
        secrets_dir=Path(args.secrets_dir) if args.secrets_dir else None,
    )

    print(
        f"[membench] {benchmark}: {dataset.question_count} questions / "
        f"{len(dataset.cases)} cases (split={args.split}, mode={args.mode}, "
        f"fixture={used_fixture})"
    )

    started = time.monotonic()
    results: List[QuestionResult] = []
    await adapter.start()
    try:
        for case_index, case in enumerate(dataset.cases, start=1):
            adapter.clear_case()
            user_id = f"bench-{benchmark}-{case.case_id}"
            for session in case.sessions:
                await adapter.ingest_session(user_id, session)

            for question in case.questions:
                q_started = time.monotonic()
                result = QuestionResult(
                    question_id=question.question_id,
                    question_type=question.question_type,
                    is_abstention=question.is_abstention,
                    evidence_session_ids=list(question.evidence_session_ids),
                    evidence_turn_ids=list(question.evidence_turn_ids),
                )
                try:
                    items = await adapter.search(user_id, question.question, fetch_limit)
                    result.retrieved_session_ids = adapter.ranked_session_ids(items)
                    result.retrieved_turn_ids = adapter.ranked_turn_ids(items)
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

            print(
                f"[membench] case {case_index}/{len(dataset.cases)} done "
                f"({case.case_id}: {len(case.sessions)} sessions, "
                f"{len(case.questions)} questions)"
            )

        usage = adapter.usage_snapshot()
        config = adapter.config_snapshot()
    finally:
        await adapter.stop()

    metrics = aggregate_results(results, args.k)
    report = build_report(
        benchmark=benchmark,
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
        wall_seconds=time.monotonic() - started,
        repo_root=REPO_ROOT,
    )

    output = (
        Path(args.output)
        if args.output
        else default_output_path(benchmark, args.mode, args.split, used_fixture)
    )
    write_report(report, output)
    print(render_summary(report))
    print(f"Report written to {output}")

    return 1 if metrics["questions_errored"] else 0


def main(benchmark: str, default_k: int, argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser(benchmark, default_k)
    args = parser.parse_args(argv)
    return asyncio.run(run_benchmark(benchmark, args))
