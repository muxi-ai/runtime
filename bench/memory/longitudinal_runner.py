#!/usr/bin/env python3
"""Longitudinal benchmark runner (Tier 3).

Runs the four PRD Tier 3 scenarios against a real MUXI formation
(memory-benchmarking PRD, "Multi-Session Longitudinal"):

- ``buffer_cycle`` (A) — sessions replayed into the real working-memory
  buffer under a small memory budget so the FIFO cleanup evicts the
  early days (exercising the pre-compaction flush hand-off); questions
  about day 1-5 facts are then answered from the persisted layers
  (KG + Captain's Log manifest ingestion, Tier 2 style) with a
  working-memory baseline alongside, plus the zero-lost-decisions
  audit.
- ``cross_agent`` (B) — knowledge produced in one agent's sessions is
  queried "via" other agents; zero-artifact-orphans audit.
- ``isolation`` (C) — every user's memory ingested side by side
  (working + persistent + KG + log); retrieval operations are then
  audited for cross-user canary/session leaks. Pass/fail.
- ``contradiction`` (D) — the manifest replayed per-session through
  the live ``store_extraction`` path with per-fact confidences; the
  KG's conflict/supersede flags are audited against the injected
  pairs (precision / recall / detection-kind accuracy), the memory
  event substrate's ``fact.contradicted`` events are tallied, and the
  audit is repeated after a knowledge-graph projection rebuild from
  the event log (replay consistency).

Every scenario is failure-isolated and writes its own report; the
process exits nonzero when any scenario was partial or errored.
Each scenario boots its own formation, and ``--scenario all`` runs
one subprocess per scenario: the runtime's database manager is a
process-level singleton, so two formations in one process would
silently share the first run's (already removed) SQLite path.

Usage
-----
::

    # Committed fixture corpus (CI-safe, no downloads, retrieval-only = $0)
    uv run python -m bench.memory.longitudinal_runner --fixture

    # One scenario, with end-to-end QA accuracy
    uv run python -m bench.memory.longitudinal_runner --fixture \
        --scenario buffer_cycle --qa

    # Full corpus (PRD scale)
    uv run python -m bench.memory.longitudinal_corpus --preset full \
        --output ~/datasets/membench/longitudinal_full.json
    uv run python -m bench.memory.longitudinal_runner \
        --dataset ~/datasets/membench/longitudinal_full.json
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
from bench.memory.datasets import BenchmarkCase, Question  # noqa: E402
from bench.memory.longitudinal_adapter import LongitudinalMemoryAdapter  # noqa: E402
from bench.memory.longitudinal_corpus import (  # noqa: E402
    SCENARIO_BUFFER_CYCLE,
    SCENARIO_CONTRADICTION,
    SCENARIO_CROSS_AGENT,
    SCENARIO_ISOLATION,
    SCENARIOS,
)
from bench.memory.longitudinal_dataset import (  # noqa: E402
    BENCHMARK_NAME,
    LongitudinalScenario,
    load_longitudinal,
)
from bench.memory.longitudinal_scoring import (  # noqa: E402
    LAYER_STRUCTURED,
    LAYER_WORKING,
    IsolationOpResult,
    LongitudinalQuestionResult,
    aggregate_buffer_cycle,
    aggregate_contradiction,
    aggregate_cross_agent,
    aggregate_isolation,
    find_leaks,
    render_longitudinal_extras,
)
from bench.memory.report import build_report, render_summary, write_report  # noqa: E402
from bench.memory.runner import FIXTURES_DIR, REPO_ROOT, RESULTS_DIR  # noqa: E402
from bench.memory.structured_adapter import STRUCTURED_MODE  # noqa: E402
from bench.memory.structured_scoring import exact_string_rank  # noqa: E402

DEFAULT_K = 5
FIXTURE_FILENAME = "longitudinal_sample.json"

# Scenario A default working-memory budget: small enough that the
# fixture corpus (a few hundred turns at ~3 KB/item with 768-dim
# embeddings) cycles the buffer several times.
DEFAULT_BUFFER_MAX_MB = 0.4

ISOLATION_OP_KINDS = ("vector_search", "graph", "log")


def fixture_path() -> Path:
    return FIXTURES_DIR / FIXTURE_FILENAME


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Tier 3 longitudinal benchmark (four PRD scenarios) "
            "against a real MUXI formation. Defaults to the committed "
            "fixture corpus; generate a full dataset with "
            "bench.memory.longitudinal_corpus for publishable numbers."
        )
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Path to a longitudinal dataset JSON (default: committed fixture).",
    )
    parser.add_argument(
        "--fixture", action="store_true", help="Force the committed fixture sample."
    )
    parser.add_argument(
        "--scenario",
        choices=("all",) + SCENARIOS,
        default="all",
        help="Scenario to run (default: all four).",
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
        help=(
            "Also measure end-to-end QA accuracy on scenarios A/B "
            "(answer + LLM judge; costs tokens)."
        ),
    )
    parser.add_argument(
        "--qa-context",
        type=int,
        default=10,
        help="Retrieved excerpts injected into the QA answer prompt.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N questions per case (smoke runs).",
    )
    parser.add_argument(
        "--buffer-max-mb",
        type=float,
        default=DEFAULT_BUFFER_MAX_MB,
        help=(
            "Scenario A working-memory budget in MB; must be small enough "
            "that the corpus cycles the buffer (checked via the "
            "evidence_evicted_fraction metric)."
        ),
    )
    parser.add_argument(
        "--flush-digest",
        action="store_true",
        help=(
            "Let the pre-compaction flush run its real silent-turn LLM "
            "digest during Scenario A (costs tokens, nondeterministic; "
            "default counts trigger/hand-off mechanics only)."
        ),
    )
    parser.add_argument(
        "--isolation-ops",
        type=int,
        default=None,
        help=(
            "Scenario C retrieval-operation count (default: the dataset's "
            "target_ops — 10,000 at PRD full scale)."
        ),
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
            "Report JSON path (single-scenario runs only; default: "
            f"bench/memory/results/{BENCHMARK_NAME}_fixture_<scenario>.json "
            "for fixture runs, timestamped otherwise)."
        ),
    )
    return parser


def default_output_path(scenario: str, used_fixture: bool) -> Path:
    if used_fixture:
        return RESULTS_DIR / f"{BENCHMARK_NAME}_fixture_{scenario}.json"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return RESULTS_DIR / f"{BENCHMARK_NAME}_{scenario}_{stamp}.json"


def _case_questions(case: BenchmarkCase, limit: Optional[int]) -> Tuple[Question, ...]:
    return case.questions[:limit] if limit is not None else case.questions


def _new_result(
    question: Question, layer: str, evidence_evicted: Optional[bool] = None
) -> LongitudinalQuestionResult:
    return LongitudinalQuestionResult(
        question_id=(
            f"{question.question_id}#{layer}" if layer != LAYER_STRUCTURED else question.question_id
        ),
        question_type=question.question_type,
        is_abstention=question.is_abstention,
        evidence_session_ids=list(question.evidence_session_ids),
        evidence_turn_ids=list(question.evidence_turn_ids),
        category=question.question_type,
        exact_strings=list(question.exact_strings),
        layer=layer,
        evidence_evicted=evidence_evicted,
    )


async def _score_retrieval(
    adapter: LongitudinalMemoryAdapter,
    result: LongitudinalQuestionResult,
    question: Question,
    items,
    qa: bool,
    qa_context: int,
) -> None:
    result.retrieved_session_ids = adapter.ranked_session_ids(items)
    result.retrieved_turn_ids = adapter.ranked_turn_ids(items)
    if question.exact_strings:
        result.exact_string_rank = exact_string_rank(
            [item.text for item in items], question.exact_strings
        )
    if qa:
        predicted = await adapter.answer_question(question, items, context_limit=qa_context)
        result.qa_answer = predicted
        result.qa_correct = await adapter.judge_answer(question, predicted)


# ---------------------------------------------------------------------------
# Scenario A: buffer cycle compensation
# ---------------------------------------------------------------------------


async def _scenario_buffer_cycle(
    adapter: LongitudinalMemoryAdapter,
    scenario: LongitudinalScenario,
    args: argparse.Namespace,
    fetch_limit: int,
) -> Tuple[Dict[str, Any], List[LongitudinalQuestionResult]]:
    results: List[LongitudinalQuestionResult] = []
    decision_items = []
    for case in scenario.dataset.cases:
        adapter.clear_case()
        user_id = f"bench-{BENCHMARK_NAME}-{case.case_id}"
        truth = scenario.ground_truth[case.case_id]

        # Persisted layers get the ground-truth manifest (Tier 2 style:
        # isolates structured recall from extraction quality); the
        # buffer gets the raw turns, session by session, under the
        # cycling budget.
        await adapter.ingest_ground_truth(user_id, truth)
        for session in case.sessions:
            await adapter.ingest_session_buffer(user_id, session)
        resident = adapter.buffer_resident_turn_ids()

        for question in _case_questions(case, args.limit):
            evidence_evicted = (
                all(turn_id not in resident for turn_id in question.evidence_turn_ids)
                if question.evidence_turn_ids
                else None
            )

            structured = _new_result(question, LAYER_STRUCTURED, evidence_evicted)
            started = time.monotonic()
            try:
                items = await adapter.search_question(user_id, question, fetch_limit)
                await _score_retrieval(
                    adapter, structured, question, items, args.qa, args.qa_context
                )
            except Exception as exc:
                structured.error = f"{type(exc).__name__}: {exc}"
            structured.elapsed_seconds = round(time.monotonic() - started, 3)
            results.append(structured)

            working = _new_result(question, LAYER_WORKING, evidence_evicted)
            started = time.monotonic()
            try:
                items = await adapter.search_working(user_id, question.question, fetch_limit)
                await _score_retrieval(adapter, working, question, items, False, args.qa_context)
            except Exception as exc:
                working.error = f"{type(exc).__name__}: {exc}"
            working.elapsed_seconds = round(time.monotonic() - started, 3)
            results.append(working)

        decision_items.extend(await adapter.audit_decisions(user_id, truth))

    metrics = aggregate_buffer_cycle(
        results, args.k, adapter.eviction_stats(), adapter.flush_stats(), decision_items
    )
    return metrics, results


# ---------------------------------------------------------------------------
# Scenario B: cross-agent knowledge propagation
# ---------------------------------------------------------------------------


async def _scenario_cross_agent(
    adapter: LongitudinalMemoryAdapter,
    scenario: LongitudinalScenario,
    args: argparse.Namespace,
    fetch_limit: int,
) -> Tuple[Dict[str, Any], List[LongitudinalQuestionResult]]:
    results: List[LongitudinalQuestionResult] = []
    artifact_items = []
    for case in scenario.dataset.cases:
        adapter.clear_case()
        user_id = f"bench-{BENCHMARK_NAME}-{case.case_id}"
        truth = scenario.ground_truth[case.case_id]
        await adapter.ingest_ground_truth(user_id, truth)

        for question in _case_questions(case, args.limit):
            result = _new_result(question, LAYER_STRUCTURED)
            started = time.monotonic()
            try:
                items = await adapter.search_question(user_id, question, fetch_limit)
                await _score_retrieval(adapter, result, question, items, args.qa, args.qa_context)
            except Exception as exc:
                result.error = f"{type(exc).__name__}: {exc}"
            result.elapsed_seconds = round(time.monotonic() - started, 3)
            results.append(result)

        artifact_items.extend(await adapter.audit_artifacts(user_id, truth))

    metrics = aggregate_cross_agent(results, args.k, artifact_items)
    return metrics, results


# ---------------------------------------------------------------------------
# Scenario C: multi-user isolation
# ---------------------------------------------------------------------------


async def _scenario_isolation(
    adapter: LongitudinalMemoryAdapter,
    scenario: LongitudinalScenario,
    args: argparse.Namespace,
    fetch_limit: int,
) -> Tuple[Dict[str, Any], List]:
    cases = scenario.dataset.cases
    canary_owners: Dict[str, str] = {}
    user_ids: Dict[str, str] = {}

    # Every user's memory is ingested side by side — working,
    # persistent, KG, and log all populated; no clearing between
    # users. Isolation must come from the runtime's own scoping.
    for case in cases:
        user_id = f"bench-{BENCHMARK_NAME}-{case.case_id}"
        user_ids[case.case_id] = user_id
        truth = scenario.ground_truth[case.case_id]
        for session in case.sessions:
            await adapter.ingest_session(user_id, session)
        await adapter.ingest_ground_truth(user_id, truth)
        for canary in truth.canaries:
            canary_owners[canary] = case.case_id

    target_ops = args.isolation_ops or int(scenario.config.get("target_ops", 0)) or 100
    ops: List[IsolationOpResult] = []
    for op_index in range(target_ops):
        case = cases[op_index % len(cases)]
        user_id = user_ids[case.case_id]
        questions = case.questions
        question = questions[(op_index // len(cases)) % len(questions)]
        op_kind = ISOLATION_OP_KINDS[op_index % len(ISOLATION_OP_KINDS)]
        op = IsolationOpResult(case_id=case.case_id, op_kind=op_kind, query=question.question)
        try:
            if op_kind == "vector_search":
                texts, session_ids = await adapter.isolation_vector_op(
                    user_id, question.question, fetch_limit
                )
            elif op_kind == "graph":
                texts, session_ids = await adapter.isolation_graph_op(user_id)
            else:
                texts, session_ids = await adapter.isolation_log_op(user_id)
            op.leaks = find_leaks(texts, session_ids, case.case_id, canary_owners)
        except Exception as exc:
            op.error = f"{type(exc).__name__}: {exc}"
        ops.append(op)
        if (op_index + 1) % 500 == 0:
            print(f"[membench]   isolation ops: {op_index + 1}/{target_ops}")

    metrics = aggregate_isolation(ops, users=len(cases), target_ops=target_ops)
    return metrics, []


# ---------------------------------------------------------------------------
# Scenario D: contradiction detection over time
# ---------------------------------------------------------------------------


async def _scenario_contradiction(
    adapter: LongitudinalMemoryAdapter,
    scenario: LongitudinalScenario,
    args: argparse.Namespace,
    fetch_limit: int,
) -> Tuple[Dict[str, Any], List]:
    del fetch_limit  # audit-only scenario
    all_live_pairs = []
    all_live_fps: List[Tuple[str, str, str, str]] = []
    all_rebuild_pairs = []
    all_rebuild_fps: List[Tuple[str, str, str, str]] = []
    events_total = 0
    events_available = False
    rebuild_available = False
    rebuild_report: Dict[str, Any] = {}
    batches_total = 0

    for case in scenario.dataset.cases:
        adapter.clear_case()
        user_id = f"bench-{BENCHMARK_NAME}-{case.case_id}"
        truth = scenario.ground_truth[case.case_id]

        batches_total += await adapter.ingest_extraction_sessions(user_id, truth)
        live_pairs, live_fps = await adapter.audit_contradiction_pairs(user_id, truth)
        all_live_pairs.extend(live_pairs)
        all_live_fps.extend(live_fps)

        detected_total = sum(pair.detected for pair in live_pairs) + len(live_fps)
        events = await adapter.contradiction_event_stats(user_id, detected_total)
        events_available = events_available or bool(events.get("available"))
        events_total += int(events.get("events", 0))

        rebuild = await adapter.rebuild_knowledge_graph(user_id)
        if rebuild.get("available"):
            rebuild_available = True
            rebuild_report = {
                key: rebuild_report.get(key, 0) + int(rebuild.get(key, 0))
                for key in ("events", "applied", "failed")
            }
            rebuild_pairs, rebuild_fps = await adapter.audit_contradiction_pairs(user_id, truth)
            all_rebuild_pairs.extend(rebuild_pairs)
            all_rebuild_fps.extend(rebuild_fps)

    live_detected_total = sum(pair.detected for pair in all_live_pairs) + len(all_live_fps)
    metrics = aggregate_contradiction(
        all_live_pairs,
        all_live_fps,
        events={
            "available": events_available,
            "events": events_total,
            "matches_detections": (
                (events_total == live_detected_total) if events_available else None
            ),
        },
        rebuild_pairs=all_rebuild_pairs if rebuild_available else None,
        rebuild_false_positives=all_rebuild_fps,
        rebuild_report=rebuild_report if rebuild_available else None,
    )
    metrics["ingest"] = {"extraction_batches": batches_total}
    return metrics, []


SCENARIO_RUNNERS = {
    SCENARIO_BUFFER_CYCLE: _scenario_buffer_cycle,
    SCENARIO_CROSS_AGENT: _scenario_cross_agent,
    SCENARIO_ISOLATION: _scenario_isolation,
    SCENARIO_CONTRADICTION: _scenario_contradiction,
}


def render_scenario_summary(report: Dict[str, Any]) -> str:
    """Shared summary for retrieval scenarios; compact header otherwise."""
    metrics = report["metrics"]
    if metrics.get("retrieval") is not None:
        base = render_summary(report)
    else:
        lines = ["=" * 64]
        lines.append(
            f"Memory benchmark: {report['benchmark']}  "
            f"(scenario={report['mode']}, k={report['k']})"
        )
        lines.append("=" * 64)
        dataset = report["dataset"]
        lines.append(
            f"Dataset: {dataset['path']}  "
            f"(cases={dataset.get('cases', '?')}, sessions={dataset.get('sessions', '?')})"
        )
        if report.get("partial"):
            lines.append("")
            lines.append(f"PARTIAL RUN — aborted: {report['run'].get('abort_reason')}")
        lines.append(f"Wall time: {report['run']['wall_seconds']}s")
        base = "\n".join(lines)
    extras = render_longitudinal_extras(report["mode"], metrics, report["k"])
    return base + (("\n" + extras) if extras else "")


async def run_scenario(
    key: str,
    scenario: LongitudinalScenario,
    args: argparse.Namespace,
    dataset_path: Path,
    used_fixture: bool,
) -> int:
    """Execute one scenario end-to-end; returns its exit code."""
    fetch_limit = args.fetch_limit or max(25, 5 * args.k)
    adapter = LongitudinalMemoryAdapter(
        # Scenario C exercises the vector read paths of every user side
        # by side; the others exercise the persisted structured layers.
        mode="combined" if key == SCENARIO_ISOLATION else STRUCTURED_MODE,
        buffer_max_mb=args.buffer_max_mb if key == SCENARIO_BUFFER_CYCLE else None,
        flush_digest=args.flush_digest,
        formation_yaml=Path(args.formation),
        run_dir=Path(args.run_dir) if args.run_dir else None,
        secrets_dir=Path(args.secrets_dir) if args.secrets_dir else None,
        keep_run_dir=args.keep_run_dir,
    )

    print(
        f"[membench] {BENCHMARK_NAME}/{key}: {len(scenario.dataset.cases)} cases / "
        f"{scenario.dataset.question_count} questions "
        f"(fixture={used_fixture}, qa={args.qa})"
    )

    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    partial = False
    report_failed = False
    abort_reason: Optional[str] = None
    usage: Dict[str, Any] = {}
    config: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}
    results: List[Any] = []

    # Tier 1 failure envelope: the report is built and written in the
    # finally path, so every exit — clean finish, crash,
    # KeyboardInterrupt — leaves a report with whatever completed.
    try:
        await adapter.start()
        metrics, results = await SCENARIO_RUNNERS[key](adapter, scenario, args, fetch_limit)
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
            report = build_report(
                benchmark=BENCHMARK_NAME,
                mode=key,
                k=args.k,
                dataset_path=str(dataset_path),
                dataset_stats={
                    "cases": len(scenario.dataset.cases),
                    "questions": scenario.dataset.question_count,
                    "sessions": scenario.dataset.session_count,
                    "fixture": used_fixture,
                    "scenario_config": dict(scenario.config),
                },
                config={**config, "fetch_limit": fetch_limit, "qa": args.qa},
                metrics=metrics,
                results=results,
                usage=usage,
                started_at=started_at,
                wall_seconds=time.monotonic() - started,
                partial=partial,
                abort_reason=abort_reason,
                repo_root=REPO_ROOT,
            )
            output = Path(args.output) if args.output else default_output_path(key, used_fixture)
            write_report(report, output)
            print(render_scenario_summary(report))
            print(f"Report written to {output}")
        except Exception as report_exc:
            report_failed = True
            print(f"[membench] failed to write report: {report_exc}", file=sys.stderr)

    incomplete = bool(
        partial
        or report_failed
        or metrics.get("questions_errored")
        or metrics.get("operations_errored")
    )
    return 1 if incomplete else 0


def _scenario_argv(args: argparse.Namespace, key: str) -> List[str]:
    """Rebuild the CLI for one scenario's subprocess."""
    argv = ["--scenario", key, "--k", str(args.k)]
    if args.dataset:
        argv += ["--dataset", args.dataset]
    if args.fixture:
        argv += ["--fixture"]
    if args.fetch_limit is not None:
        argv += ["--fetch-limit", str(args.fetch_limit)]
    if args.qa:
        argv += ["--qa", "--qa-context", str(args.qa_context)]
    if args.limit is not None:
        argv += ["--limit", str(args.limit)]
    argv += ["--buffer-max-mb", str(args.buffer_max_mb)]
    if args.flush_digest:
        argv += ["--flush-digest"]
    if args.isolation_ops is not None:
        argv += ["--isolation-ops", str(args.isolation_ops)]
    argv += ["--formation", args.formation]
    if args.run_dir:
        # One formation per scenario: give each its own run directory.
        argv += ["--run-dir", str(Path(args.run_dir) / key)]
    if args.keep_run_dir:
        argv += ["--keep-run-dir"]
    if args.secrets_dir:
        argv += ["--secrets-dir", args.secrets_dir]
    return argv


async def _run_all_scenarios(args: argparse.Namespace) -> int:
    """Run every scenario in its own subprocess (fresh formation each).

    The runtime's database manager is a process-level singleton keyed
    to the first connection string it sees, so a second formation in
    the same process would reuse the first scenario's (already
    removed) run-local SQLite path.
    """
    exit_code = 0
    for key in SCENARIOS:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "bench.memory.longitudinal_runner",
            *_scenario_argv(args, key),
            cwd=str(REPO_ROOT),
        )
        exit_code = max(exit_code, await process.wait())
    return exit_code


async def run_benchmark(args: argparse.Namespace) -> int:
    """Run the selected scenarios; returns the process exit code."""
    if args.scenario == "all":
        return await _run_all_scenarios(args)

    dataset_path = Path(args.dataset) if (args.dataset and not args.fixture) else fixture_path()
    used_fixture = dataset_path == fixture_path()
    scenarios = load_longitudinal(dataset_path)

    key = args.scenario
    if key not in scenarios:
        print(f"Dataset has no scenario: {key}", file=sys.stderr)
        return 1
    try:
        return await run_scenario(key, scenarios[key], args, dataset_path, used_fixture)
    except Exception as exc:
        # run_scenario already wrote a partial report in its finally.
        print(f"[membench] scenario {key} failed: {exc}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    sys.exit(main())
