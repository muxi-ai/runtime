# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Decay - Query-Time Confidence Weighting
# Description:  Exponential half-life decay for memory events and projections
# Role:         Pure decay math + validated settings (Memory Substrate 2c)
# Usage:        DecaySettings built in formation init, applied at query time
# Author:       Muxi Framework Team
#
# Memory Event Substrate Phase 2c (PRD "Decay Model"). Decay is applied at
# QUERY time only -- stored confidences are never rewritten, so decay
# changes take effect immediately and retroactively:
#
# - ``static`` events/facts never fade.
# - ``decaying`` events/facts lose confidence exponentially:
#   effective = confidence * 0.5 ** (age_days / half_life_days).
#   (True half-life semantics: at age == half_life the confidence has
#   halved. The PRD sketches exp(-age/half_life); the parameter is named
#   half_life, so the mathematically honest form is used.)
# - ``volatile`` events expire entirely at ``expires_at`` (defaulted to
#   occurred_at + volatile_default_ttl_hours at write time); after expiry
#   their effective confidence is 0.0 and the maintenance sweep
#   soft-deletes them so rebuilds drop their projections.
#
# Projection rows do not carry a decay declaration -- which knowledge
# graph relationship types decay (and how fast) is formation policy,
# configured under ``memory.decay.half_lives`` (type -> days). MUXI ships
# the mechanism; the default is an empty map, so nothing decays unless
# the formation says so.
# =============================================================================

from datetime import datetime
from typing import Any, Dict, Optional

from ....utils.datetime_utils import utc_now_naive
from .models import DECAY_DECAYING, DECAY_VOLATILE

# PRD defaults (Configuration Reference -> memory.decay).
DEFAULT_HALF_LIFE_DAYS = 180.0
DEFAULT_VOLATILE_TTL_HOURS = 24.0

_SECONDS_PER_DAY = 86400.0


class DecaySettings:
    """Validated ``memory.decay`` configuration (fail-fast on bad values)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Parse and validate the ``memory.decay`` formation config section.

        Raises:
            ValueError: On non-positive half-lives or TTLs.
        """
        config = config or {}
        self.enabled = bool(config.get("enabled", True))
        self.default_half_life_days = _positive_number(
            config.get("default_half_life_days", DEFAULT_HALF_LIFE_DAYS),
            "memory.decay.default_half_life_days",
        )
        self.volatile_ttl_hours = _positive_number(
            config.get("volatile_default_ttl_hours", DEFAULT_VOLATILE_TTL_HOURS),
            "memory.decay.volatile_default_ttl_hours",
        )
        half_lives = config.get("half_lives") or {}
        if not isinstance(half_lives, dict):
            raise ValueError("memory.decay.half_lives must be a mapping of type -> days")
        self.half_lives: Dict[str, float] = {
            str(key).strip().lower(): _positive_number(value, f"memory.decay.half_lives.{key}")
            for key, value in half_lives.items()
        }

    def half_life_for(self, fact_type: Optional[str]) -> Optional[float]:
        """Half-life in days for a projection fact type, or None (static)."""
        if not self.enabled or not fact_type:
            return None
        return self.half_lives.get(str(fact_type).strip().lower())


def decayed_confidence(confidence: float, age_days: float, half_life_days: float) -> float:
    """Exponential half-life decay: halves every ``half_life_days``."""
    if age_days <= 0:
        return confidence
    return confidence * 0.5 ** (age_days / half_life_days)


def effective_event_confidence(
    event: Dict[str, Any],
    decay: Optional[DecaySettings] = None,
    now: Optional[datetime] = None,
) -> float:
    """
    Query-time effective confidence for one memory event dict.

    static -> stored source_confidence; decaying -> half-life weighted by
    age since occurred_at (default half-life when settings are absent);
    volatile -> 0.0 once expired. Disabled decay settings return the
    stored confidence unchanged.
    """
    confidence = float(event.get("source_confidence") or 0.0)
    if decay is not None and not decay.enabled:
        return confidence

    now = now or utc_now_naive()
    rate = event.get("decay_rate")

    if rate == DECAY_VOLATILE:
        expires_at = _parse(event.get("expires_at"))
        if expires_at is not None and expires_at <= now:
            return 0.0
        return confidence

    if rate == DECAY_DECAYING:
        occurred_at = _parse(event.get("occurred_at"))
        if occurred_at is None:
            return confidence
        half_life = decay.default_half_life_days if decay else DEFAULT_HALF_LIFE_DAYS
        age_days = max(0.0, (now - occurred_at).total_seconds() / _SECONDS_PER_DAY)
        return decayed_confidence(confidence, age_days, half_life)

    return confidence


def effective_fact_confidence(
    fact: Dict[str, Any],
    decay: Optional[DecaySettings],
    now: Optional[datetime] = None,
) -> float:
    """
    Query-time effective confidence for one projection row dict.

    ``fact`` is a kg_relationships (or kg_entities) row dict with
    ``type``, ``confidence``, and ``updated_at``. Types without a
    configured half-life are static. Reinforcement resets the age for
    free: every contributing upsert refreshes ``updated_at``.
    """
    confidence = float(fact.get("confidence") or 0.0)
    half_life = decay.half_life_for(fact.get("type")) if decay else None
    if half_life is None:
        return confidence
    updated_at = _parse(fact.get("updated_at")) or _parse(fact.get("created_at"))
    if updated_at is None:
        return confidence
    now = now or utc_now_naive()
    age_days = max(0.0, (now - updated_at).total_seconds() / _SECONDS_PER_DAY)
    return decayed_confidence(confidence, age_days, half_life)


def _positive_number(value: Any, label: str) -> float:
    """Coerce a config value to a positive float, failing fast otherwise."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive number, got {value!r}")
    if number <= 0:
        raise ValueError(f"{label} must be a positive number, got {value!r}")
    return number


def _parse(value: Any) -> Optional[datetime]:
    """Parse an ISO timestamp (or pass through a datetime), else None."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
