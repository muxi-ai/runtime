"""Retrieval and QA scoring for the memory benchmarks.

Metrics
-------
- ``hit_at_k``       — 1 if ANY evidence id appears in the top-K
  retrieved ids. This is the standard "Recall@K" reported by
  LongMemEval-style leaderboards (fraction of questions whose
  evidence is retrieved), and the headline number in reports.
- ``coverage_at_k``  — fraction of evidence ids present in the top-K.
  Stricter than hit@K for multi-evidence questions.
- ``mrr``            — reciprocal rank of the first evidence id.

Abstention questions (no evidence exists by design, e.g. LongMemEval
``_abs`` ids and LoCoMo adversarial questions) are excluded from
retrieval aggregates and counted separately; retrieval metrics are
undefined for them.

All functions are pure and deterministic: same inputs, same outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence


def ranked_unique(ids: Iterable[str]) -> List[str]:
    """Deduplicate ``ids`` preserving first-seen (rank) order."""
    seen = set()
    ordered: List[str] = []
    for item_id in ids:
        if item_id not in seen:
            seen.add(item_id)
            ordered.append(item_id)
    return ordered


def hit_at_k(retrieved_ids: Sequence[str], evidence_ids: Sequence[str], k: int) -> bool:
    """True if any evidence id appears in the top-``k`` retrieved ids.

    ``retrieved_ids`` must already be ranked best-first; duplicates are
    collapsed to their best rank before applying the cutoff.
    """
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")
    if not evidence_ids:
        raise ValueError("hit_at_k is undefined without evidence ids (abstention question?)")
    top_k = set(ranked_unique(retrieved_ids)[:k])
    return any(evidence_id in top_k for evidence_id in evidence_ids)


def coverage_at_k(retrieved_ids: Sequence[str], evidence_ids: Sequence[str], k: int) -> float:
    """Fraction of evidence ids present in the top-``k`` retrieved ids."""
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")
    if not evidence_ids:
        raise ValueError("coverage_at_k is undefined without evidence ids")
    top_k = set(ranked_unique(retrieved_ids)[:k])
    unique_evidence = set(evidence_ids)
    return len(unique_evidence & top_k) / len(unique_evidence)


def mrr(retrieved_ids: Sequence[str], evidence_ids: Sequence[str]) -> float:
    """Reciprocal rank of the first evidence id (0.0 if none retrieved)."""
    if not evidence_ids:
        raise ValueError("mrr is undefined without evidence ids")
    evidence = set(evidence_ids)
    for rank, item_id in enumerate(ranked_unique(retrieved_ids), start=1):
        if item_id in evidence:
            return 1.0 / rank
    return 0.0


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], rrf_k: int = 60) -> List[str]:
    """Merge ranked id lists with Reciprocal Rank Fusion.

    Used for the "combined" retrieval mode: working-memory scores
    (cosine + recency blend) and persistent-memory scores (SQLite
    distance-derived) live on different scales, so score-based merging
    would silently favor one backend. RRF is scale-free: each list
    contributes ``1 / (rrf_k + rank)`` per id.

    Ties are broken by first-seen order across ``rankings`` (stable,
    deterministic).
    """
    if rrf_k <= 0:
        raise ValueError(f"rrf_k must be positive, got {rrf_k}")
    scores: Dict[str, float] = {}
    first_seen: Dict[str, int] = {}
    counter = 0
    for ranking in rankings:
        for rank, item_id in enumerate(ranked_unique(ranking), start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rrf_k + rank)
            if item_id not in first_seen:
                first_seen[item_id] = counter
                counter += 1
    return sorted(scores, key=lambda item_id: (-scores[item_id], first_seen[item_id]))


@dataclass
class QuestionResult:
    """Everything measured for a single benchmark question."""

    question_id: str
    question_type: str
    is_abstention: bool
    evidence_session_ids: List[str] = field(default_factory=list)
    evidence_turn_ids: List[str] = field(default_factory=list)
    retrieved_session_ids: List[str] = field(default_factory=list)
    retrieved_turn_ids: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    qa_answer: Optional[str] = None
    qa_correct: Optional[bool] = None
    error: Optional[str] = None

    def session_metrics(self, k: int) -> Optional[Dict[str, float]]:
        """Session-level retrieval metrics, or None for abstention/error."""
        if self.is_abstention or self.error or not self.evidence_session_ids:
            return None
        return {
            f"hit@{k}": float(hit_at_k(self.retrieved_session_ids, self.evidence_session_ids, k)),
            f"coverage@{k}": coverage_at_k(
                self.retrieved_session_ids, self.evidence_session_ids, k
            ),
            "mrr": mrr(self.retrieved_session_ids, self.evidence_session_ids),
        }

    def turn_metrics(self, k: int) -> Optional[Dict[str, float]]:
        """Turn-level retrieval metrics, or None when turn evidence is absent."""
        if self.is_abstention or self.error or not self.evidence_turn_ids:
            return None
        return {
            f"hit@{k}": float(hit_at_k(self.retrieved_turn_ids, self.evidence_turn_ids, k)),
            f"coverage@{k}": coverage_at_k(self.retrieved_turn_ids, self.evidence_turn_ids, k),
            "mrr": mrr(self.retrieved_turn_ids, self.evidence_turn_ids),
        }


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _aggregate_level(
    results: Sequence[QuestionResult], k: int, level: str
) -> Optional[Dict[str, object]]:
    """Aggregate one retrieval level ("session" or "turn") across results."""
    metric_fn = (
        QuestionResult.session_metrics if level == "session" else QuestionResult.turn_metrics
    )
    scored = [(result, metric_fn(result, k)) for result in results]
    scored = [(result, metrics) for result, metrics in scored if metrics is not None]
    if not scored:
        return None

    def summarize(pairs) -> Dict[str, object]:
        return {
            "questions": len(pairs),
            f"recall@{k}": _mean([m[f"hit@{k}"] for _, m in pairs]),
            f"coverage@{k}": _mean([m[f"coverage@{k}"] for _, m in pairs]),
            "mrr": _mean([m["mrr"] for _, m in pairs]),
        }

    by_type: Dict[str, List] = {}
    for result, metrics in scored:
        by_type.setdefault(result.question_type, []).append((result, metrics))

    return {
        "overall": summarize(scored),
        "by_question_type": {
            question_type: summarize(pairs) for question_type, pairs in sorted(by_type.items())
        },
    }


def aggregate_results(results: Sequence[QuestionResult], k: int) -> Dict[str, object]:
    """Aggregate per-question results into the report's ``metrics`` block.

    Returns session-level and turn-level retrieval aggregates (overall
    and per question type), QA accuracy when QA was run, and counts of
    abstention/errored questions excluded from retrieval aggregates.
    """
    errors = [result for result in results if result.error]
    abstentions = [result for result in results if result.is_abstention and not result.error]

    qa_scored = [result for result in results if result.qa_correct is not None]
    qa_block = None
    if qa_scored:
        by_type: Dict[str, List[QuestionResult]] = {}
        for result in qa_scored:
            by_type.setdefault(result.question_type, []).append(result)
        qa_block = {
            "overall": {
                "questions": len(qa_scored),
                "accuracy": _mean([float(result.qa_correct) for result in qa_scored]),
            },
            "by_question_type": {
                question_type: {
                    "questions": len(type_results),
                    "accuracy": _mean([float(result.qa_correct) for result in type_results]),
                }
                for question_type, type_results in sorted(by_type.items())
            },
        }

    return {
        "k": k,
        "questions_total": len(results),
        "questions_scored": len(results) - len(abstentions) - len(errors),
        "questions_abstention": len(abstentions),
        "questions_errored": len(errors),
        "retrieval": {
            "session_level": _aggregate_level(results, k, "session"),
            "turn_level": _aggregate_level(results, k, "turn"),
        },
        "qa": qa_block,
    }
