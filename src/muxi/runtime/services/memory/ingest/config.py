# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Ingestion Settings - Fail-Fast Configuration Parsing
# Description:  Validated settings for tiers, entity resolution, and synthesis
# Role:         Single source of truth for the memory.ingestion config shape
# Usage:        parse_ingestion_config() from MemoryIngestionService and the
#               formation validator (both parse the same way, by construction)
# Author:       Muxi Framework Team
#
# Memory Ingestion maturation (tier heuristics + entity resolution +
# synthesis cadences). One parser, shared by the runtime service and the
# formation config validator, so the two can never disagree about what a
# valid ``memory.ingestion`` block looks like. Every error message carries
# the full config path (fail-fast policy).
#
#   memory:
#     ingestion:
#       max_in_flight_per_user: 4        # pre-existing (lenient fallback)
#       sources:
#         gmail:
#           filter: strict|lenient|off   # pre-existing noise gate
#           tier: 1|2|3                  # optional per-source tier pin
#       tiers:                           # escalation heuristics (T1->T2->T3)
#         enabled: true
#         ambiguity_margin: 0.05         # classify margin below -> escalate T2
#         t3_signal_score: 5             # T0 signal score at/above -> T3
#         models:
#           t2: "openai/gpt-4o-mini"     # optional; default extraction model
#           t3: "anthropic/claude-..."   # optional; falls back to t2 model
#         budget:
#           t2_items_per_job: 100        # LLM-extraction cap per processing job
#           t3_items_per_job: 10         # frontier cap per processing job
#       entity_resolution:
#         enabled: true
#         auto_merge_threshold: 0.85     # score at/above -> auto-merge
#         flag_threshold: 0.5            # score at/above (below merge) -> flag
#         entity_types: [person]
#         max_entities: 200              # per-user scan bound per pass
#       synthesis:
#         enabled: true
#         hot:       { enabled: true, interval_seconds: 300 }
#         warm:      { enabled: true, interval_seconds: 3600 }
#         cold:      { enabled: true, interval_seconds: 86400 }
#         cold_cold: { enabled: true, interval_seconds: 604800 }
#         patterns:
#           enabled: true
#           min_events: 20               # schedule pattern needs this many events
#           top_k: 3                     # items per rendered pattern fact
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# Tier vocabulary (PRD "Processing Pipeline" stage 3). Tier 0 (regex +
# heuristics) is not a resting tier: it computes the escalation signals.
TIER_LOCAL = 1  # small local processing only (classify + verbatim store)
TIER_STANDARD = 2  # mid-size LLM extraction (the default extraction model)
TIER_FRONTIER = 3  # frontier LLM extraction, flagged high-signal items only
TIERS = (TIER_LOCAL, TIER_STANDARD, TIER_FRONTIER)

DEFAULT_AMBIGUITY_MARGIN = 0.05
DEFAULT_T3_SIGNAL_SCORE = 5
DEFAULT_T2_ITEMS_PER_JOB = 100
DEFAULT_T3_ITEMS_PER_JOB = 10

DEFAULT_AUTO_MERGE_THRESHOLD = 0.85
DEFAULT_FLAG_THRESHOLD = 0.5
DEFAULT_RESOLUTION_ENTITY_TYPES = ("person",)
DEFAULT_RESOLUTION_MAX_ENTITIES = 200

# PRD "Synthesis Scheduling" cadence table.
DEFAULT_CADENCE_INTERVALS = {
    "hot": 300.0,  # 5 minutes
    "warm": 3600.0,  # hourly
    "cold": 86400.0,  # nightly
    "cold_cold": 604800.0,  # weekly full re-synthesis
}

DEFAULT_PATTERN_MIN_EVENTS = 20
DEFAULT_PATTERN_TOP_K = 3


@dataclass(frozen=True)
class TierSettings:
    """Validated ``memory.ingestion.tiers`` (escalation heuristics)."""

    enabled: bool = True
    ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN
    t3_signal_score: int = DEFAULT_T3_SIGNAL_SCORE
    t2_model: Optional[str] = None
    t3_model: Optional[str] = None
    t2_items_per_job: int = DEFAULT_T2_ITEMS_PER_JOB
    t3_items_per_job: int = DEFAULT_T3_ITEMS_PER_JOB


@dataclass(frozen=True)
class ResolutionSettings:
    """Validated ``memory.ingestion.entity_resolution``."""

    enabled: bool = True
    auto_merge_threshold: float = DEFAULT_AUTO_MERGE_THRESHOLD
    flag_threshold: float = DEFAULT_FLAG_THRESHOLD
    entity_types: Tuple[str, ...] = DEFAULT_RESOLUTION_ENTITY_TYPES
    max_entities: int = DEFAULT_RESOLUTION_MAX_ENTITIES


@dataclass(frozen=True)
class CadenceSettings:
    """One synthesis cadence: individually disableable, interval in seconds."""

    enabled: bool = True
    interval_seconds: float = 0.0


@dataclass(frozen=True)
class PatternSettings:
    """Validated ``memory.ingestion.synthesis.patterns`` (v1 mechanisms)."""

    enabled: bool = True
    min_events: int = DEFAULT_PATTERN_MIN_EVENTS
    top_k: int = DEFAULT_PATTERN_TOP_K


@dataclass(frozen=True)
class SynthesisSettings:
    """Validated ``memory.ingestion.synthesis`` (cadence table)."""

    enabled: bool = True
    hot: CadenceSettings = field(
        default_factory=lambda: CadenceSettings(True, DEFAULT_CADENCE_INTERVALS["hot"])
    )
    warm: CadenceSettings = field(
        default_factory=lambda: CadenceSettings(True, DEFAULT_CADENCE_INTERVALS["warm"])
    )
    cold: CadenceSettings = field(
        default_factory=lambda: CadenceSettings(True, DEFAULT_CADENCE_INTERVALS["cold"])
    )
    cold_cold: CadenceSettings = field(
        default_factory=lambda: CadenceSettings(True, DEFAULT_CADENCE_INTERVALS["cold_cold"])
    )
    patterns: PatternSettings = field(default_factory=PatternSettings)

    def cadence(self, name: str) -> CadenceSettings:
        """The settings for one cadence name (hot/warm/cold/cold_cold)."""
        return getattr(self, name)


@dataclass(frozen=True)
class IngestionSettings:
    """The validated ``memory.ingestion`` maturation sections.

    The pre-existing keys (``sources`` filter levels and
    ``max_in_flight_per_user``) keep their shipped lenient-fallback
    semantics in MemoryIngestionService; this object owns the strict
    (fail-fast) sections plus the per-source tier pins.
    """

    tiers: TierSettings = field(default_factory=TierSettings)
    entity_resolution: ResolutionSettings = field(default_factory=ResolutionSettings)
    synthesis: SynthesisSettings = field(default_factory=SynthesisSettings)
    source_tiers: Dict[str, int] = field(default_factory=dict)


def parse_ingestion_config(config: Any) -> IngestionSettings:
    """
    Parse and validate a ``memory.ingestion`` config block.

    Args:
        config: The raw config section (None means "not configured";
            defaults apply).

    Returns:
        IngestionSettings with every maturation section validated.

    Raises:
        ValueError: On any invalid value, with the full config path in
            the message (fail-fast policy; the formation validator
            surfaces the same message at load time).
    """
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("memory.ingestion must be a dictionary")

    return IngestionSettings(
        tiers=_parse_tiers(config.get("tiers")),
        entity_resolution=_parse_resolution(config.get("entity_resolution")),
        synthesis=_parse_synthesis(config.get("synthesis")),
        source_tiers=_parse_source_tiers(config.get("sources")),
    )


def _parse_tiers(section: Any) -> TierSettings:
    section = _section(section, "memory.ingestion.tiers")
    models = _section(section.get("models"), "memory.ingestion.tiers.models")
    budget = _section(section.get("budget"), "memory.ingestion.tiers.budget")
    return TierSettings(
        enabled=_boolean(section.get("enabled", True), "memory.ingestion.tiers.enabled"),
        ambiguity_margin=_number_in_range(
            section.get("ambiguity_margin", DEFAULT_AMBIGUITY_MARGIN),
            "memory.ingestion.tiers.ambiguity_margin",
            low=0.0,
            high=1.0,
        ),
        t3_signal_score=_positive_int(
            section.get("t3_signal_score", DEFAULT_T3_SIGNAL_SCORE),
            "memory.ingestion.tiers.t3_signal_score",
        ),
        t2_model=_optional_model(models.get("t2"), "memory.ingestion.tiers.models.t2"),
        t3_model=_optional_model(models.get("t3"), "memory.ingestion.tiers.models.t3"),
        t2_items_per_job=_positive_int(
            budget.get("t2_items_per_job", DEFAULT_T2_ITEMS_PER_JOB),
            "memory.ingestion.tiers.budget.t2_items_per_job",
        ),
        t3_items_per_job=_positive_int(
            budget.get("t3_items_per_job", DEFAULT_T3_ITEMS_PER_JOB),
            "memory.ingestion.tiers.budget.t3_items_per_job",
        ),
    )


def _parse_resolution(section: Any) -> ResolutionSettings:
    section = _section(section, "memory.ingestion.entity_resolution")
    auto_merge = _number_in_range(
        section.get("auto_merge_threshold", DEFAULT_AUTO_MERGE_THRESHOLD),
        "memory.ingestion.entity_resolution.auto_merge_threshold",
        low=0.0,
        high=1.0,
    )
    flag = _number_in_range(
        section.get("flag_threshold", DEFAULT_FLAG_THRESHOLD),
        "memory.ingestion.entity_resolution.flag_threshold",
        low=0.0,
        high=1.0,
    )
    if flag > auto_merge:
        raise ValueError(
            "memory.ingestion.entity_resolution.flag_threshold must not exceed "
            "auto_merge_threshold"
        )
    entity_types = section.get("entity_types", list(DEFAULT_RESOLUTION_ENTITY_TYPES))
    if not isinstance(entity_types, list) or not entity_types:
        raise ValueError("memory.ingestion.entity_resolution.entity_types must be a non-empty list")
    normalized = []
    for value in entity_types:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "memory.ingestion.entity_resolution.entity_types entries must be "
                "non-empty strings"
            )
        normalized.append(value.strip().lower())
    return ResolutionSettings(
        enabled=_boolean(
            section.get("enabled", True), "memory.ingestion.entity_resolution.enabled"
        ),
        auto_merge_threshold=auto_merge,
        flag_threshold=flag,
        entity_types=tuple(normalized),
        max_entities=_positive_int(
            section.get("max_entities", DEFAULT_RESOLUTION_MAX_ENTITIES),
            "memory.ingestion.entity_resolution.max_entities",
        ),
    )


def _parse_synthesis(section: Any) -> SynthesisSettings:
    section = _section(section, "memory.ingestion.synthesis")
    cadences = {}
    for name, default_interval in DEFAULT_CADENCE_INTERVALS.items():
        cadence_section = _section(section.get(name), f"memory.ingestion.synthesis.{name}")
        cadences[name] = CadenceSettings(
            enabled=_boolean(
                cadence_section.get("enabled", True),
                f"memory.ingestion.synthesis.{name}.enabled",
            ),
            interval_seconds=_positive_number(
                cadence_section.get("interval_seconds", default_interval),
                f"memory.ingestion.synthesis.{name}.interval_seconds",
            ),
        )
    patterns_section = _section(section.get("patterns"), "memory.ingestion.synthesis.patterns")
    patterns = PatternSettings(
        enabled=_boolean(
            patterns_section.get("enabled", True),
            "memory.ingestion.synthesis.patterns.enabled",
        ),
        min_events=_positive_int(
            patterns_section.get("min_events", DEFAULT_PATTERN_MIN_EVENTS),
            "memory.ingestion.synthesis.patterns.min_events",
        ),
        top_k=_positive_int(
            patterns_section.get("top_k", DEFAULT_PATTERN_TOP_K),
            "memory.ingestion.synthesis.patterns.top_k",
        ),
    )
    return SynthesisSettings(
        enabled=_boolean(section.get("enabled", True), "memory.ingestion.synthesis.enabled"),
        hot=cadences["hot"],
        warm=cadences["warm"],
        cold=cadences["cold"],
        cold_cold=cadences["cold_cold"],
        patterns=patterns,
    )


def _parse_source_tiers(sources: Any) -> Dict[str, int]:
    """Per-source tier pins (``sources.<source>.tier``), validated strictly.

    The pre-existing ``filter`` key keeps its lenient fallback in the
    service; only the new ``tier`` key is validated here.
    """
    if sources is None:
        return {}
    if not isinstance(sources, dict):
        raise ValueError("memory.ingestion.sources must be a dictionary")
    pins: Dict[str, int] = {}
    for source, source_config in sources.items():
        if not isinstance(source_config, dict):
            continue  # shipped lenient posture for per-source blocks
        if "tier" not in source_config:
            continue
        tier = source_config["tier"]
        if isinstance(tier, bool) or not isinstance(tier, int) or tier not in TIERS:
            raise ValueError(
                f"memory.ingestion.sources.{source}.tier must be one of {list(TIERS)}, "
                f"got {tier!r}"
            )
        pins[str(source)] = tier
    return pins


# ---------------------------------------------------------------------------
# Primitive validators (full-path error messages)
# ---------------------------------------------------------------------------


def _section(value: Any, label: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a dictionary")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean, got {value!r}")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer, got {value!r}")
    return value


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{label} must be a positive number, got {value!r}")
    return float(value)


def _number_in_range(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number between {low} and {high}, got {value!r}")
    number = float(value)
    if number < low or number > high:
        raise ValueError(f"{label} must be between {low} and {high}, got {value!r}")
    return number


def _optional_model(value: Any, label: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty model string when provided")
    return value.strip()
