"""Cost-efficiency math for the Tier 4 benchmark (pure, deterministic).

The Tier 4 runner (:mod:`bench.memory.cost_runner`) measures raw
quantities — per-query latencies, token counts, correct answers,
storage bytes — and this module turns them into the PRD's published
metrics:

- **Tokens per accurate recall** — memory-system tokens consumed per
  correctly answered question (retrieval context injected + answer
  overhead), the MemPalace-comparable efficiency number.
- **Cost per 1,000 queries** — measured per-query token averages
  priced against the updatable table in ``bench/memory/pricing.json``.
- **Usage scenarios** — monthly cost per user at light/moderate/heavy
  query volumes (10/50/200 queries/day), the enterprise-pricing
  comparison against Mem0 ($19-249/mo) and Zep ($25/mo+).
- **Latency percentiles** — p50/p95/p99 with linear interpolation
  (same definition as ``numpy.percentile(..., method="linear")``).

Prices come from ``pricing.json`` so the table is updatable without
touching code; every report echoes the prices used.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Sequence

from .report import MODEL_PRICES_USD_PER_MTOK, estimate_cost_usd

# PRD usage scenarios: queries per day per user.
USAGE_SCENARIOS = {"light": 10, "moderate": 50, "heavy": 200}
DAYS_PER_MONTH = 30

LATENCY_PERCENTILES = (50.0, 95.0, 99.0)


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile (``numpy`` "linear" method).

    Raises ValueError on an empty sequence or a percentile outside
    [0, 100].
    """
    if not values:
        raise ValueError("percentile is undefined for an empty sequence")
    if not 0.0 <= pct <= 100.0:
        raise ValueError(f"percentile must be in [0, 100], got {pct}")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    fraction = rank - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def latency_summary(seconds: Sequence[float]) -> Optional[Dict[str, float]]:
    """p50/p95/p99/mean/min/max in milliseconds, or None without samples."""
    if not seconds:
        return None
    millis = [s * 1000.0 for s in seconds]
    summary = {
        f"p{int(p) if float(p).is_integer() else p}_ms": round(percentile(millis, p), 2)
        for p in LATENCY_PERCENTILES
    }
    summary["mean_ms"] = round(sum(millis) / len(millis), 2)
    summary["min_ms"] = round(min(millis), 2)
    summary["max_ms"] = round(max(millis), 2)
    summary["samples"] = len(millis)
    return summary


def tokens_per_accurate_recall(total_tokens: int, correct_answers: int) -> Optional[float]:
    """Memory-system tokens spent per correctly answered question.

    None when nothing was answered correctly (the ratio is undefined,
    not infinite — a report should show the gap, not a fake number).
    """
    if total_tokens < 0 or correct_answers < 0:
        raise ValueError("token and answer counts must be non-negative")
    if correct_answers == 0:
        return None
    return total_tokens / correct_answers


def cost_per_query_usd(tokens_by_model_per_query: Dict[str, Sequence[float]]) -> Optional[float]:
    """Priced cost of one query from its per-model average token usage.

    ``tokens_by_model_per_query`` maps a model slug to the per-query
    average ``[total, in, out, ...]`` fields (fractions allowed).
    Returns None when any priced usage is on an unknown model.
    """
    breakdown = {
        model: [int(round(field)) for field in fields]
        for model, fields in tokens_by_model_per_query.items()
    }
    cost = estimate_cost_usd(breakdown)
    if cost["unpriced_models"]:
        return None
    return float(cost["estimated_usd"] or 0.0)


def cost_projection(
    per_query_usd: Optional[float],
    scenarios: Optional[Dict[str, int]] = None,
) -> Dict[str, object]:
    """Project measured per-query cost to the PRD's usage scenarios."""
    scenarios = scenarios or USAGE_SCENARIOS
    block: Dict[str, object] = {
        "per_query_usd": round(per_query_usd, 8) if per_query_usd is not None else None,
        "per_1000_queries_usd": (
            round(per_query_usd * 1000, 4) if per_query_usd is not None else None
        ),
        "scenarios": {},
    }
    for name, per_day in sorted(scenarios.items()):
        monthly_queries = per_day * DAYS_PER_MONTH
        block["scenarios"][name] = {
            "queries_per_day": per_day,
            "queries_per_month": monthly_queries,
            "monthly_usd": (
                round(per_query_usd * monthly_queries, 4) if per_query_usd is not None else None
            ),
        }
    return block


def footprint_summary(
    db_bytes: int,
    working_memory_items: int,
    embedding_dimension: int,
    ingested_turns: int,
) -> Dict[str, object]:
    """Storage footprint block: measured DB size + working-memory estimate.

    The FAISS buffer holds float32 vectors (4 bytes per dimension) plus
    the verbatim texts; the vector portion dominates and is the stable,
    machine-independent part, so that is what the estimate covers.
    """
    if min(db_bytes, working_memory_items, embedding_dimension, ingested_turns) < 0:
        raise ValueError("footprint inputs must be non-negative")
    working_bytes = working_memory_items * embedding_dimension * 4
    per_turn = (db_bytes + working_bytes) / ingested_turns if ingested_turns else None
    return {
        "persistent_db_bytes": db_bytes,
        "working_memory_items": working_memory_items,
        "working_memory_vector_bytes": working_bytes,
        "embedding_dimension": embedding_dimension,
        "ingested_turns": ingested_turns,
        "bytes_per_ingested_turn": round(per_turn, 1) if per_turn is not None else None,
    }


def pricing_snapshot() -> Dict[str, object]:
    """Echo the pricing table into reports (updatable via pricing.json)."""
    return {
        "source": "bench/memory/pricing.json",
        "usd_per_mtok": {model: dict(v) for model, v in sorted(MODEL_PRICES_USD_PER_MTOK.items())},
    }
