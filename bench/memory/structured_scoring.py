"""Scoring extensions for the Tier 2 structured-recall benchmark.

Adds two measurements on top of the Tier 1 R@K/coverage/MRR machinery:

- **Exact-string recall** — for questions whose gold answer is a
  verbatim token (email address, ticket code, invoice id), was the
  exact string present in the text of the top-K retrieved items?
  Semantic embeddings are notoriously weak at exact-token matching;
  this metric is the decision input for memory-revamp Phase 6
  (hybrid/BM25 search) and is rendered prominently in reports.
- **Contradiction detection** — precision/recall of the KG's
  conflict flags against the injected ground-truth contradictions
  (structured mode only; vector retrieval has no notion of
  contradiction).

All functions are pure and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .scoring import QuestionResult, aggregate_results


@dataclass
class StructuredQuestionResult(QuestionResult):
    """Tier 1 result plus structured-recall measurements."""

    category: str = ""
    exact_strings: List[str] = field(default_factory=list)
    # Best (1-based) rank of a retrieved item whose text contains every
    # exact string; None when the strings never appear.
    exact_string_rank: Optional[int] = None


def exact_string_rank(
    retrieved_texts: Sequence[str], exact_strings: Sequence[str]
) -> Optional[int]:
    """Best 1-based rank at which ALL exact strings have appeared.

    Case-insensitive substring match, scanning the ranked texts
    best-first and accumulating: rank r counts as a hit once every
    exact string has been seen in items 1..r. Returns None if any
    string never appears.
    """
    if not exact_strings:
        raise ValueError("exact_string_rank is undefined without exact strings")
    remaining = {s.lower() for s in exact_strings}
    for rank, text in enumerate(retrieved_texts, start=1):
        haystack = text.lower()
        remaining = {s for s in remaining if s not in haystack}
        if not remaining:
            return rank
    return None


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def aggregate_exact_strings(
    results: Sequence[StructuredQuestionResult], k: int
) -> Optional[Dict[str, object]]:
    """Aggregate exact-string recall across questions that carry them."""
    scored = [
        result
        for result in results
        if result.exact_strings and not result.error and not result.is_abstention
    ]
    if not scored:
        return None

    def summarize(items: Sequence[StructuredQuestionResult]) -> Dict[str, object]:
        hits = [
            float(result.exact_string_rank is not None and result.exact_string_rank <= k)
            for result in items
        ]
        anywhere = [float(result.exact_string_rank is not None) for result in items]
        return {
            "questions": len(items),
            f"recall@{k}": _mean(hits),
            "recall@fetch": _mean(anywhere),
            "missed_question_ids": sorted(
                result.question_id
                for result in items
                if result.exact_string_rank is None or result.exact_string_rank > k
            ),
        }

    by_category: Dict[str, List[StructuredQuestionResult]] = {}
    for result in scored:
        by_category.setdefault(result.category or result.question_type, []).append(result)

    return {
        "overall": summarize(scored),
        "by_category": {
            category: summarize(items) for category, items in sorted(by_category.items())
        },
    }


@dataclass
class ContradictionCaseResult:
    """Contradiction detection outcome for one case (structured mode)."""

    case_id: str
    expected: int = 0
    detected: int = 0
    true_positives: int = 0
    detected_pairs: List[Tuple[str, str, str, str]] = field(default_factory=list)
    expected_pairs: List[Tuple[str, str, str, str]] = field(default_factory=list)


def aggregate_contradictions(
    cases: Sequence[ContradictionCaseResult],
) -> Optional[Dict[str, object]]:
    """Precision/recall of contradiction flags across cases."""
    if not cases:
        return None
    expected = sum(case.expected for case in cases)
    detected = sum(case.detected for case in cases)
    true_positives = sum(case.true_positives for case in cases)
    return {
        "expected": expected,
        "detected": detected,
        "true_positives": true_positives,
        "precision": (true_positives / detected) if detected else None,
        "recall": (true_positives / expected) if expected else None,
        "by_case": {
            case.case_id: {
                "expected": case.expected,
                "detected": case.detected,
                "true_positives": case.true_positives,
            }
            for case in sorted(cases, key=lambda case: case.case_id)
        },
    }


def aggregate_structured_results(
    results: Sequence[StructuredQuestionResult],
    k: int,
    contradiction_cases: Sequence[ContradictionCaseResult] = (),
) -> Dict[str, object]:
    """Tier 1 aggregate plus the structured-recall metric blocks."""
    metrics = aggregate_results(results, k)
    metrics["exact_strings"] = aggregate_exact_strings(results, k)
    metrics["contradiction_detection"] = aggregate_contradictions(contradiction_cases)
    return metrics


def render_structured_summary_extras(metrics: Dict[str, object], k: int) -> str:
    """Extra stdout lines: exact-string recall (prominent) + contradictions."""
    lines: List[str] = []

    exact = metrics.get("exact_strings")
    if exact:
        overall = exact["overall"]
        lines.append("")
        lines.append("EXACT-STRING RECALL (emails/codes/ids; Phase 6 hybrid-search signal):")
        lines.append(
            f"  overall: found-in-top-{k}={_format_pct(overall[f'recall@{k}'])}  "
            f"found-at-any-fetched-rank={_format_pct(overall['recall@fetch'])}  "
            f"(n={overall['questions']})"
        )
        for category, stats in exact["by_category"].items():
            lines.append(
                f"  {category:<28} found@{k}={_format_pct(stats[f'recall@{k}']):>7}  "
                f"n={stats['questions']}"
            )
        missed = overall.get("missed_question_ids") or []
        if missed:
            lines.append(f"  MISSED (not in top-{k}): {', '.join(missed)}")

    contradictions = metrics.get("contradiction_detection")
    if contradictions:
        lines.append("")
        lines.append(
            f"Contradiction detection: precision={_format_pct(contradictions['precision'])}  "
            f"recall={_format_pct(contradictions['recall'])}  "
            f"(expected={contradictions['expected']}, detected={contradictions['detected']})"
        )

    return "\n".join(lines)


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
