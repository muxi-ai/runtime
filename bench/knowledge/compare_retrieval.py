#!/usr/bin/env python3
"""Knowledge retrieval comparison benchmark (reasoning-RAG PRD Phase 5).

Runs the same fixture questions against a REAL MUXI formation - no mocks -
once per retrieval mode:

    vector       flat chunk similarity (the pre-reasoning pipeline)
    tree         Method A: pure LLM tree navigation
    tree-vector  Method B: per-node chunk-embedding value scoring
    hybrid       parallel A+B + sufficiency evaluator

For every question the harness checks whether the expected substrings
appear in the top-k retrieved contents (hit@k), and reports per-mode hit
rate, mean/median query latency, and the run's token usage (from the
request-context tally, same mechanism as bench/memory).

Usage:
    cd bench && uv run python -m knowledge.compare_retrieval [--modes vector,tree]
        [--top-k 5] [--secrets-dir PATH] [--out PATH]

Secrets: reuses the e2e pair (.key is gitignored - copy it from your main
checkout; secrets.enc is committed under e2e/assets).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

BENCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCH_DIR.parent.parent
DEFAULT_SECRETS_DIR = REPO_ROOT / "e2e" / "assets"
DEFAULT_FORMATION_YAML = BENCH_DIR / "formation" / "formation.yaml"
FIXTURE_DOC = BENCH_DIR / "fixtures" / "colony-handbook.md"
FIXTURE_QUESTIONS = BENCH_DIR / "fixtures" / "questions.json"

MODES = ("vector", "tree", "tree-vector", "hybrid")

sys.path.insert(0, str(REPO_ROOT / "src"))


def _prepare_run_dir(mode: str, secrets_dir: Path) -> Path:
    """Render the benchmark formation + fixture corpus into a temp dir."""
    run_dir = Path(tempfile.mkdtemp(prefix=f"muxi-knowbench-{mode}-"))
    knowledge_dir = run_dir / "knowledge"
    knowledge_dir.mkdir(parents=True)
    shutil.copy2(FIXTURE_DOC, knowledge_dir / FIXTURE_DOC.name)

    with open(DEFAULT_FORMATION_YAML, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    # Rewrite the source's retrieval mode for this run.
    for agent in config.get("agents", []):
        if not isinstance(agent, dict):
            continue
        for source in agent.get("knowledge", {}).get("sources", []):
            source["retrieval"] = mode

    # Run-local conversation event log.
    for stream in config.get("logging", {}).get("conversation", {}).get("streams", []):
        if stream.get("transport") == "file":
            stream["destination"] = str(run_dir / "knowbench-events.jsonl")

    with open(run_dir / "formation.yaml", "w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    # Secrets: same symlink strategy as the e2e suite / bench/memory.
    for name in (".key", "secrets.enc"):
        source_path = secrets_dir / name
        target = run_dir / name
        if source_path.exists() and not (target.exists() or target.is_symlink()):
            try:
                target.symlink_to(source_path)
            except OSError:
                shutil.copy2(source_path, target)
    return run_dir


async def _run_mode(
    mode: str, questions: List[Dict[str, Any]], top_k: int, secrets_dir: Path
) -> Dict[str, Any]:
    """Load a formation with ``mode`` retrieval and score every question."""
    from muxi.runtime.datatypes.observability import RequestContext
    from muxi.runtime.formation import Formation
    from muxi.runtime.services.observability.context import set_request_context

    run_dir = _prepare_run_dir(mode, secrets_dir)
    formation = Formation()
    ingest_start = time.time()
    await formation.load(str(run_dir / "formation.yaml"))
    overlord = await formation.start_overlord()
    ingest_seconds = time.time() - ingest_start

    token_context = RequestContext(id=f"knowbench-{uuid.uuid4().hex[:12]}")
    set_request_context(token_context)

    per_question: List[Dict[str, Any]] = []
    try:
        agent = overlord.agents["knowbench-agent"]
        handler = agent.knowledge_handler
        if handler is None:
            raise RuntimeError("knowledge handler not initialized")

        for question in questions:
            started = time.time()
            results = await handler.search(question["query"], top_k=top_k)
            latency = time.time() - started
            combined = " ".join(r.get("content", "") for r in results)
            hit = all(expected in combined for expected in question["expected"])
            per_question.append(
                {
                    "id": question["id"],
                    "hit": hit,
                    "latency_s": round(latency, 3),
                    "results": len(results),
                    "methods": sorted(
                        {r["metadata"].get("retrieval_method", "vector") for r in results}
                    ),
                }
            )
            marker = "HIT " if hit else "MISS"
            print(f"  [{marker}] {question['id']:<16} {latency:6.2f}s  {question['query']}")
    finally:
        await formation.stop_overlord()
        shutil.rmtree(run_dir, ignore_errors=True)

    latencies = [q["latency_s"] for q in per_question]
    usage = token_context.tokens
    return {
        "mode": mode,
        "hit_rate": round(sum(q["hit"] for q in per_question) / len(per_question), 3),
        "hits": sum(q["hit"] for q in per_question),
        "questions": len(per_question),
        "latency_mean_s": round(statistics.mean(latencies), 3),
        "latency_median_s": round(statistics.median(latencies), 3),
        "ingest_seconds": round(ingest_seconds, 2),
        "tokens": {
            "total": usage.total[0],
            "in": usage.total[1],
            "out": usage.total[2],
        },
        "per_question": per_question,
    }


def _render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Knowledge Retrieval Comparison",
        "",
        f"Corpus: `{FIXTURE_DOC.name}` | top_k: {report['top_k']} | "
        f"questions: {report['question_count']}",
        "",
        "| Mode | Hit rate | Mean latency | Median latency | Ingest | Tokens (in/out) |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["modes"]:
        lines.append(
            f"| {row['mode']} | {row['hits']}/{row['questions']} "
            f"({row['hit_rate']:.0%}) | {row['latency_mean_s']}s "
            f"| {row['latency_median_s']}s | {row['ingest_seconds']}s "
            f"| {row['tokens']['in']}/{row['tokens']['out']} |"
        )
    lines.append("")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modes", default=",".join(MODES), help="comma-separated mode list")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--secrets-dir", type=Path, default=DEFAULT_SECRETS_DIR)
    parser.add_argument("--out", type=Path, default=BENCH_DIR / "compare_retrieval.json")
    args = parser.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        parser.error(f"unknown mode(s): {unknown} (expected subset of {MODES})")

    with open(FIXTURE_QUESTIONS, "r", encoding="utf-8") as handle:
        questions = json.load(handle)

    rows: List[Dict[str, Any]] = []
    for mode in modes:
        print(f"\n=== mode: {mode} ===")
        rows.append(await _run_mode(mode, questions, args.top_k, args.secrets_dir))

    report = {
        "benchmark": "knowledge_retrieval_comparison",
        "top_k": args.top_k,
        "question_count": len(questions),
        "modes": rows,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    markdown = _render_markdown(report)
    md_path = args.out.with_suffix(".md")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(markdown)

    print("\n" + markdown)
    print(f"Report: {args.out}\n        {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
