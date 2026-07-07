"""Report generation for the memory benchmarks.

Every run produces one structured JSON report (machine-comparable
across runs) and a human summary printed to stdout. Reports are
written with sorted keys and stable list ordering so that two runs
with identical results produce byte-identical ``results`` /
``metrics`` blocks (only the ``run`` metadata differs).
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from .scoring import QuestionResult

REPORT_SCHEMA_VERSION = "1.0"

# Published list prices (USD per 1M tokens), used ONLY for the
# estimated-cost line in reports. Estimates as of 2026-07; update as
# providers change pricing. Unknown models report ``null`` cost.
MODEL_PRICES_USD_PER_MTOK: Dict[str, Dict[str, float]] = {
    "openai/gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "openai/gpt-4o": {"in": 2.50, "out": 10.00},
    "openai/gpt-4.1-mini": {"in": 0.40, "out": 1.60},
    "openai/gpt-4.1-nano": {"in": 0.10, "out": 0.40},
    "openai/text-embedding-3-small": {"in": 0.02, "out": 0.0},
    "openai/text-embedding-3-large": {"in": 0.13, "out": 0.0},
    "anthropic/claude-3-5-haiku-20241022": {"in": 0.80, "out": 4.00},
}

# Local (ONNX) embedding models run on-box and are free.
_FREE_MODEL_PREFIX = "local/"


def estimate_cost_usd(model_breakdown: Dict[str, Sequence[int]]) -> Dict[str, Any]:
    """Estimate the run's LLM spend from a per-model token breakdown.

    ``model_breakdown`` maps a provider-prefixed model slug to the
    ``TokenUsage.FIELDS`` array (``[total, in, out, total_cached,
    in_cached, out_cached]``). Models with no price entry contribute
    ``null`` and are listed under ``unpriced_models``.
    """
    total_cost: float = 0.0
    priced_any = False
    unpriced: List[str] = []
    per_model: Dict[str, Optional[float]] = {}
    for model, fields in sorted(model_breakdown.items()):
        tokens_in = fields[1] if len(fields) > 1 else 0
        tokens_out = fields[2] if len(fields) > 2 else 0
        if model.startswith(_FREE_MODEL_PREFIX):
            per_model[model] = 0.0
            priced_any = True
            continue
        price = MODEL_PRICES_USD_PER_MTOK.get(model)
        if price is None:
            per_model[model] = None
            unpriced.append(model)
            continue
        cost = (tokens_in * price["in"] + tokens_out * price["out"]) / 1_000_000
        per_model[model] = round(cost, 6)
        total_cost += cost
        priced_any = True
    return {
        "estimated_usd": round(total_cost, 6) if priced_any or not unpriced else None,
        "per_model_usd": per_model,
        "unpriced_models": unpriced,
        "note": "List-price estimate for reporting only; local/* models are free.",
    }


def relativize(path: Union[str, Path], repo_root: Optional[Union[str, Path]]) -> str:
    """Render ``path`` relative to ``repo_root`` when it lives inside it.

    Committed reports must not leak machine-specific absolute paths;
    paths outside the repo (e.g. ``$MUXI_BENCH_DATA_DIR``) stay as-is.
    """
    path = Path(path)
    if repo_root is not None:
        try:
            return str(path.resolve().relative_to(Path(repo_root).resolve()))
        except ValueError:
            pass
    return str(path)


def _git_commit(repo_root: Union[str, Path]) -> Optional[str]:
    try:
        output = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return output.stdout.strip() or None
    except Exception:
        return None


def build_report(
    *,
    benchmark: str,
    mode: str,
    k: int,
    dataset_path: str,
    dataset_stats: Dict[str, int],
    config: Dict[str, Any],
    metrics: Dict[str, Any],
    results: Sequence[QuestionResult],
    usage: Dict[str, Any],
    wall_seconds: float,
    repo_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Assemble the structured report for one benchmark run."""
    sorted_results = sorted(results, key=lambda result: result.question_id)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "benchmark": benchmark,
        "mode": mode,
        "k": k,
        "run": {
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "wall_seconds": round(wall_seconds, 2),
            "python": platform.python_version(),
            "git_commit": _git_commit(repo_root) if repo_root else None,
        },
        "dataset": {"path": relativize(dataset_path, repo_root), **dataset_stats},
        "config": config,
        "usage": usage,
        "metrics": metrics,
        "results": [asdict(result) for result in sorted_results],
    }


def write_report(report: Dict[str, Any], path: Union[str, Path]) -> Path:
    """Write ``report`` as deterministic, sorted-key JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return path


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def render_summary(report: Dict[str, Any]) -> str:
    """Render the human-readable stdout summary for one run."""
    metrics = report["metrics"]
    k = report["k"]
    lines: List[str] = []
    lines.append("=" * 64)
    lines.append(f"Memory benchmark: {report['benchmark']}  (mode={report['mode']}, k={k})")
    lines.append("=" * 64)
    dataset = report["dataset"]
    lines.append(
        f"Dataset: {dataset['path']}  "
        f"(cases={dataset.get('cases', '?')}, questions={dataset.get('questions', '?')})"
    )
    lines.append(
        f"Scored: {metrics['questions_scored']}  "
        f"abstention: {metrics['questions_abstention']}  "
        f"errors: {metrics['questions_errored']}"
    )

    for level_name, label in (("session_level", "Session"), ("turn_level", "Turn")):
        level = metrics["retrieval"].get(level_name)
        if not level:
            continue
        overall = level["overall"]
        lines.append("")
        lines.append(
            f"{label}-level retrieval:  R@{k}={_format_pct(overall[f'recall@{k}'])}  "
            f"coverage@{k}={_format_pct(overall[f'coverage@{k}'])}  "
            f"MRR={overall['mrr']:.3f}  (n={overall['questions']})"
        )
        for question_type, stats in level["by_question_type"].items():
            lines.append(
                f"  {question_type:<28} R@{k}={_format_pct(stats[f'recall@{k}']):>7}  "
                f"n={stats['questions']}"
            )

    qa = metrics.get("qa")
    if qa:
        lines.append("")
        lines.append(
            f"QA accuracy (end-to-end): {_format_pct(qa['overall']['accuracy'])}  "
            f"(n={qa['overall']['questions']})"
        )
        for question_type, stats in qa["by_question_type"].items():
            lines.append(
                f"  {question_type:<28} acc={_format_pct(stats['accuracy']):>7}  "
                f"n={stats['questions']}"
            )

    usage = report.get("usage") or {}
    tokens = usage.get("tokens") or {}
    cost = usage.get("cost") or {}
    lines.append("")
    lines.append(
        f"LLM usage: requests={usage.get('llm_requests', 0)}  "
        f"tokens_in={tokens.get('in', 0)}  tokens_out={tokens.get('out', 0)}  "
        f"est_cost=${cost.get('estimated_usd') if cost.get('estimated_usd') is not None else 'n/a'}"
    )
    lines.append(f"Wall time: {report['run']['wall_seconds']}s")
    lines.append("=" * 64)
    return "\n".join(lines)
