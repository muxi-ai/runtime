# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Ingestion Tier Heuristics - T1 -> T2 -> T3 Escalation
# Description:  Deterministic escalation decisions for the extraction stage
# Role:         Decides how much LLM an ingested item earns (PRD tier table)
# Usage:        Used by MemoryIngestionService per kept item, budget-capped
# Author:       Muxi Framework Team
#
# Memory Ingestion maturation, PRD "Processing Pipeline" stage 3:
#
#   Tier 0 (free):      regex + heuristics       -> content_signals()
#   Tier 1 (cheap):     small local processing    -> classify + verbatim store
#   Tier 2 (moderate):  mid-size model            -> LLM extraction pass
#   Tier 3 (expensive): frontier model            -> flagged high-signal items
#
# "Most items never leave Tier 1. Frontier LLM use is deliberate, not
# default." The decision is a PURE function of the classification result,
# the Tier-0 signals, and validated settings -- no LLM is consulted to
# decide whether to consult an LLM. Escalation criteria, in order:
#
#   1. Per-source pin (sources.<source>.tier) -- the developer's dial wins.
#   2. Explicit priority flag (metadata.priority: high) -> Tier 3.
#   3. Synthesis-worthy category (personal/work; unknown fails open) or an
#      ambiguous classification (margin below tiers.ambiguity_margin)
#      -> Tier 2.
#   4. High-signal Tier-2 items (Tier-0 signal score at/above
#      tiers.t3_signal_score: commitments, dates, money, identity
#      mentions) -> Tier 3.
#   5. Everything else rests at Tier 1.
#
# Budgets (tiers.budget.t{2,3}_items_per_job) cap escalations per
# processing job; a capped item is demoted to the best affordable tier and
# the demotion is part of the recorded reason -- never a dropped item.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .classification import CATEGORY_PERSONAL, CATEGORY_UNKNOWN, CATEGORY_WORK
from .config import TIER_FRONTIER, TIER_LOCAL, TIER_STANDARD, TierSettings

# Categories whose content is synthesis-worthy by default (PRD: "mid-size
# model for synthesis-worthy items"). Unknown is included so a broken
# classifier degrades extraction quality upward, never downward.
SYNTHESIS_WORTHY_CATEGORIES = frozenset({CATEGORY_PERSONAL, CATEGORY_WORK, CATEGORY_UNKNOWN})

# ---------------------------------------------------------------------------
# Tier 0: regex + heuristics (free signal extraction)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z][\w-]{2,}\b")
_MONEY_RE = re.compile(
    r"(?:[$€£]\s?\d[\d,]*(?:\.\d+)?)|(?:\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP)\b)"
)
_DATE_RE = re.compile(
    r"(?:\b\d{4}-\d{2}-\d{2}\b)"
    r"|(?:\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b)"
    r"|(?:\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b)"
    r"|(?:\bnext\s+(?:week|month|quarter)\b)"
    r"|(?:\bend\s+of\s+Q[1-4]\b)",
    re.IGNORECASE,
)
_COMMITMENT_RE = re.compile(
    r"\b(?:deadline|due(?:\s+(?:on|by|date))?|agreed(?:\s+to)?|commit(?:ment|ted|s)?"
    r"|promised?|action\s+items?|deliverables?|contract|signed?\s+off"
    r"|must\s+(?:ship|deliver|finish|complete)"
    r"|will\s+(?:send|deliver|ship|finish|complete)|by\s+(?:eod|eow|end\s+of\s+day))\b",
    re.IGNORECASE,
)
# Capitalized bigrams ("Ryan Leveille") as a cheap proper-name proxy.
_NAME_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b")

# Per-signal contribution caps so one signal class cannot dominate the score.
_SIGNAL_CAPS = {"identities": 3, "dates": 2, "money": 2, "commitments": 3}


def content_signals(text: str) -> Dict[str, int]:
    """Tier-0 signal counts for one content string (pure regex, no LLM).

    ``identities`` counts identity mentions (emails, @handles, proper
    names) -- the entity-density proxy; the rest map one-to-one onto the
    PRD's high-signal markers (commitments, dates, money).
    """
    if not text:
        return {"identities": 0, "dates": 0, "money": 0, "commitments": 0}
    return {
        "identities": len(_EMAIL_RE.findall(text))
        + len(_HANDLE_RE.findall(text))
        + len(_NAME_RE.findall(text)),
        "dates": len(_DATE_RE.findall(text)),
        "money": len(_MONEY_RE.findall(text)),
        "commitments": len(_COMMITMENT_RE.findall(text)),
    }


def signal_score(signals: Dict[str, int]) -> int:
    """Aggregate signal score with per-signal caps (deterministic)."""
    return sum(min(signals.get(name, 0), cap) for name, cap in _SIGNAL_CAPS.items())


# ---------------------------------------------------------------------------
# Escalation decision (pure function of triage + signals + settings)
# ---------------------------------------------------------------------------


def decide_tier(
    category: str,
    margin: float,
    signals: Dict[str, int],
    settings: TierSettings,
    source_tier: Optional[int] = None,
    priority: Optional[str] = None,
) -> Tuple[int, str]:
    """
    Decide the extraction tier for one kept item.

    Args:
        category: The triage category from the local classifier.
        margin: The winning category's classification margin.
        signals: Tier-0 signal counts (content_signals()).
        settings: Validated TierSettings.
        source_tier: Optional per-source pin (sources.<source>.tier).
        priority: The item's ``metadata.priority`` value, if any.

    Returns:
        (tier, reason) -- reason is a stable, machine-parsable string
        recorded on the escalation event and the item report.
    """
    if not settings.enabled:
        # Heuristics off: the shipped Phase 3a behavior (every kept item
        # runs the standard extraction pass).
        return TIER_STANDARD, "tiers_disabled"

    if source_tier is not None:
        return source_tier, f"source_pin:{source_tier}"

    if isinstance(priority, str) and priority.strip().lower() == "high":
        return TIER_FRONTIER, "priority_flag"

    if category in SYNTHESIS_WORTHY_CATEGORIES:
        tier, reason = TIER_STANDARD, f"category:{category}"
    elif margin < settings.ambiguity_margin:
        tier, reason = TIER_STANDARD, f"ambiguous_classification:margin={margin:.4f}"
    else:
        return TIER_LOCAL, f"low_signal_category:{category}"

    score = signal_score(signals)
    if score >= settings.t3_signal_score:
        rendered = ",".join(f"{k}={v}" for k, v in sorted(signals.items()) if v)
        return TIER_FRONTIER, f"high_signal:score={score}({rendered})"
    return tier, reason


@dataclass
class TierBudget:
    """Per-job escalation budget (PRD "Cost Management": tiered budgets).

    One instance per processing job. ``admit`` consumes budget for the
    requested tier and demotes to the best affordable tier when the cap
    is reached -- items are never dropped for budget reasons.
    """

    t2_remaining: int
    t3_remaining: int

    @classmethod
    def from_settings(cls, settings: TierSettings) -> "TierBudget":
        return cls(
            t2_remaining=settings.t2_items_per_job,
            t3_remaining=settings.t3_items_per_job,
        )

    def admit(self, tier: int) -> Tuple[int, bool]:
        """Admit an item at ``tier``; returns (granted tier, capped?)."""
        if tier == TIER_FRONTIER:
            if self.t3_remaining > 0:
                self.t3_remaining -= 1
                return TIER_FRONTIER, False
            tier = TIER_STANDARD  # demote and fall through to the T2 budget
            capped = True
        else:
            capped = False
        if tier == TIER_STANDARD:
            if self.t2_remaining > 0:
                self.t2_remaining -= 1
                return TIER_STANDARD, capped
            return TIER_LOCAL, True
        return TIER_LOCAL, capped
