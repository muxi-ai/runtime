#!/usr/bin/env python3
"""
Compare Phase 0 (baseline) and Phase 2 (post-localization) bench runs.

Reads two JSON reports produced by ``run_baseline.py`` and writes a
markdown summary to ``bench/local_classification_phase2.md``.

The interesting deltas to surface are:

1. Classification-bucket call counts per workload — Phase 2 should
   bring these to zero for the gates we replaced (3 credentials +
   1 scheduler + 1 fusion-quality + 2 clarification fast-paths).
2. Wall-time delta on light + heavy workloads. Light is where the
   wins concentrate: clear-execute requests now skip the
   ``_analyze_request`` LLM call entirely.
3. Per-prompt p50 wall-time table so regressions in any single
   prompt are visible.

Usage
-----
::

    python bench/compare_phase2.py \\
        --baseline bench/local_classification_baseline.json \\
        --phase2  bench/local_classification_phase2.json \\
        --output  bench/local_classification_phase2.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple


def _per_label_p50(results: List[Dict[str, Any]]) -> Dict[str, float]:
    by_label: Dict[str, List[float]] = {}
    for r in results:
        if r.get("http_status") not in (200, 201):
            continue
        by_label.setdefault(r["label"], []).append(r["wall_seconds"])
    return {label: round(median(walls), 3) for label, walls in by_label.items()}


def _per_label_classify_counts(results: List[Dict[str, Any]]) -> Dict[str, float]:
    by_label: Dict[str, List[int]] = {}
    for r in results:
        ev = r.get("classification_events") or {}
        cls = int(ev.get("classification", 0))
        by_label.setdefault(r["label"], []).append(cls)
    return {label: round(sum(cs) / len(cs), 2) for label, cs in by_label.items()}


def _summary_block(report: Dict[str, Any], workload: str) -> Optional[Dict[str, Any]]:
    if workload not in report:
        return None
    section = report[workload]
    return {
        "summary": section.get("summary") or {},
        "classify_totals": section.get("classification_event_totals") or {},
        "results": section.get("results") or [],
    }


def _format_delta(old: float, new: float) -> str:
    if old <= 0:
        return f"{new:.3f}s"
    pct = (new - old) / old * 100.0
    arrow = "↓" if pct < 0 else "↑"
    return f"{new:.3f}s  ({arrow}{abs(pct):.1f}% vs {old:.3f}s)"


def _format_count_delta(old: float, new: float) -> str:
    arrow = "↓" if new < old else ("↑" if new > old else "=")
    return f"{new:.2f} ({arrow} from {old:.2f})"


def _markdown_section(title: str, b0: Dict[str, Any], b2: Dict[str, Any]) -> str:
    lines: List[str] = [f"## {title}\n"]

    s0 = b0.get("summary") or {}
    s2 = b2.get("summary") or {}

    if s0 and s2:
        lines.append("| Metric | Baseline (Phase 0) | Phase 2 | Delta |")
        lines.append("|---|---:|---:|---:|")
        for key, label in [
            ("min_s", "min wall"),
            ("median_s", "**median wall**"),
            ("max_s", "max wall"),
            ("total_s", "total wall (all runs)"),
        ]:
            v0 = s0.get(key)
            v2 = s2.get(key)
            if v0 is None or v2 is None:
                continue
            delta_pct = (v2 - v0) / v0 * 100.0 if v0 else 0.0
            arrow = "↓" if delta_pct < 0 else ("↑" if delta_pct > 0 else "=")
            lines.append(
                f"| {label} | {v0:.3f}s | {v2:.3f}s | {arrow}{abs(delta_pct):.1f}% |"
            )
        lines.append("")

    c0 = b0.get("classify_totals") or {}
    c2 = b2.get("classify_totals") or {}

    if c0 or c2:
        lines.append("### LLM call buckets (totals across all runs)")
        lines.append("")
        lines.append("| Bucket | Baseline | Phase 2 | Delta |")
        lines.append("|---|---:|---:|---:|")
        for key in ("classification", "synthesis", "planning", "unknown"):
            v0 = int(c0.get(key, 0))
            v2 = int(c2.get(key, 0))
            arrow = "↓" if v2 < v0 else ("↑" if v2 > v0 else "=")
            lines.append(f"| {key} | {v0} | {v2} | {arrow} {abs(v2 - v0)} |")
        lines.append("")

    p50_0 = _per_label_p50(b0.get("results") or [])
    p50_2 = _per_label_p50(b2.get("results") or [])
    cls_0 = _per_label_classify_counts(b0.get("results") or [])
    cls_2 = _per_label_classify_counts(b2.get("results") or [])

    if p50_0 and p50_2:
        lines.append("### Per-prompt p50 wall and classification calls")
        lines.append("")
        lines.append(
            "| Prompt | p50 baseline | p50 Phase 2 | Wall delta | "
            "Classify calls baseline → Phase 2 |"
        )
        lines.append("|---|---:|---:|---:|---:|")
        all_labels = sorted(set(p50_0) | set(p50_2))
        for label in all_labels:
            v0 = p50_0.get(label)
            v2 = p50_2.get(label)
            c0v = cls_0.get(label, 0.0)
            c2v = cls_2.get(label, 0.0)
            if v0 is None or v2 is None:
                continue
            delta_pct = (v2 - v0) / v0 * 100.0 if v0 else 0.0
            arrow = "↓" if delta_pct < 0 else ("↑" if delta_pct > 0 else "=")
            lines.append(
                f"| `{label}` | {v0:.3f}s | {v2:.3f}s | "
                f"{arrow}{abs(delta_pct):.1f}% | {c0v:.2f} → {c2v:.2f} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 0 vs Phase 2 comparison report.")
    p.add_argument("--baseline", default="bench/local_classification_baseline.json")
    p.add_argument("--phase2", default="bench/local_classification_phase2.json")
    p.add_argument("--output", default="bench/local_classification_phase2.md")
    args = p.parse_args()

    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    p2 = json.loads(Path(args.phase2).read_text(encoding="utf-8"))

    out: List[str] = [
        "# Local Classification — Phase 2 Comparison",
        "",
        f"Baseline: `{args.baseline}`  ",
        f"Phase 2:  `{args.phase2}`  ",
        f"Baseline started: `{base.get('started_at')}`  ",
        f"Phase 2 started:  `{p2.get('started_at')}`  ",
        f"Runs per workload: baseline={base.get('runs')}, phase2={p2.get('runs')}",
        "",
        "Phase 2 changes the following gates from cloud LLM calls to "
        "local prototype-similarity / pairwise cosine:",
        "",
        "* `credentials.is_credential_request` (Group A)",
        "* `credentials._is_cancellation` (Group A)",
        "* `credentials._is_help_request` (Group A)",
        "* `scheduler._is_significant_prompt_change` (Group A)",
        "* `multimodal.fusion_engine` semantic similarity (Group D)",
        "* `clarification._analyze_request` fast-path skip (Group B)",
        "* `clarification._check_need_more` fast-path skip (Group B)",
        "",
        "The clarification fast-paths only short-circuit when the local "
        "classifier is confident; the LLM still runs to generate the "
        "clarification question on the positive branch. Group A and "
        "Group D are full replacements with no LLM fallback.",
        "",
    ]

    for workload in ("heavy", "light"):
        b0 = _summary_block(base, workload)
        b2 = _summary_block(p2, workload)
        if b0 is None or b2 is None:
            continue
        out.append(_markdown_section(f"{workload.title()} workload", b0, b2))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote comparison report to {out_path}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
