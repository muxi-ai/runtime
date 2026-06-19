"""
Core types and helpers for entity-based redaction.

The regex secret scrubber (``utils/security.py``) remains the always-on first
layer. Entity detectors (e.g. the optional Presidio-backed one) are a second,
opt-in layer that returns character ``Span``s which are masked with consistent,
indexed tokens like ``[PERSON_1]``.
"""

import threading
from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable

# Minimum confidence for a detected span to be treated as PII. Shared by the
# masking path and the memory sensitivity gate so both layers agree on what
# "contains PII" means.
DEFAULT_ENTITY_THRESHOLD = 0.5


@dataclass(frozen=True)
class Span:
    """A detected sensitive region within a text."""

    start: int
    end: int
    label: str
    score: float


@runtime_checkable
class EntityDetector(Protocol):
    """Detects format-free PII (names, addresses, orgs, ...) in text."""

    def detect(self, text: str, language: str = "en") -> List[Span]: ...


def _merge_spans(spans: List[Span], threshold: float) -> List[Span]:
    """Drop low-confidence spans and resolve overlaps (longest span wins)."""
    kept = [s for s in spans if s.score >= threshold and s.end > s.start]
    # Sort by start, then longest first, then highest score, so the first span
    # covering a region is the preferred one and any overlapping spans are dropped.
    kept.sort(key=lambda s: (s.start, -(s.end - s.start), -s.score))
    result: List[Span] = []
    for span in kept:
        if result and span.start < result[-1].end:
            continue
        result.append(span)
    return result


def mask_spans(text: str, spans: List[Span], threshold: float = DEFAULT_ENTITY_THRESHOLD) -> str:
    """
    Replace detected spans with consistent, label-aware indexed tokens.

    Repeated mentions of the same value (case-insensitive) within a single call
    reuse the same token (e.g. both "Jane Doe" mentions become ``[PERSON_1]``).
    """
    merged = _merge_spans(spans, threshold)
    if not merged:
        return text

    counters: dict = {}
    value_tokens: dict = {}
    out: List[str] = []
    last = 0
    for span in merged:
        out.append(text[last : span.start])
        value = text[span.start : span.end]
        key = (span.label, value.casefold().strip())
        token = value_tokens.get(key)
        if token is None:
            idx = counters.get(span.label, 0) + 1
            counters[span.label] = idx
            token = f"[{span.label}_{idx}]"
            value_tokens[key] = token
        out.append(token)
        last = span.end
    out.append(text[last:])
    return "".join(out)


# --- Process-level detector registry ---------------------------------------
# The active entity detector (if any) is registered once during formation load
# and consulted by the redaction path. None means regex-only (default).

_entity_detector: Optional[EntityDetector] = None
_registry_lock = threading.Lock()


def set_entity_detector(detector: Optional[EntityDetector]) -> None:
    """Register (or clear) the process-wide entity detector."""
    global _entity_detector
    with _registry_lock:
        _entity_detector = detector


def get_entity_detector() -> Optional[EntityDetector]:
    """Return the registered entity detector, or None when redaction is regex-only."""
    with _registry_lock:
        return _entity_detector
