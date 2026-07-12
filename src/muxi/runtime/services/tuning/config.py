"""
Tuning configuration (the top-level ``tuning:`` block).

The entire new AFS surface of the Self-Improving Formation PRD. All
defaults on: an absent block means the tuner is on with defaults, one
loop pass a day. ``tuning.active: false`` is the off switch (no digest,
no tuner; the always-on event spool stays within its cap and is
otherwise inert). The spool itself has no key -- it is internal runtime
behavior, not configuration.

Closed key set, fail-fast validation at formation load, booleans
rejected where numbers are expected.
"""

from dataclasses import dataclass
from typing import Any

_ALLOWED_TUNING_KEYS = {"active", "interval_hours", "auto_apply"}

DEFAULT_INTERVAL_HOURS = 24.0


class TuningConfigError(ValueError):
    """Raised for any invalid ``tuning:`` configuration (fail fast at load)."""


@dataclass
class TuningConfig:
    """Parsed ``tuning:`` block (or the defaults, when the block is absent)."""

    active: bool = True
    interval_hours: float = DEFAULT_INTERVAL_HOURS
    # Phase 1 stores the flag; the tuner step (Phase 2) acts on it.
    auto_apply: bool = True


def _boolean(value: Any, *, key: str) -> bool:
    if not isinstance(value, bool):
        raise TuningConfigError(f"tuning.{key} must be a boolean, got: {value!r}")
    return value


def _positive_number(value: Any, *, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TuningConfigError(f"tuning.{key} must be a number of hours, got: {value!r}")
    if value <= 0:
        raise TuningConfigError(f"tuning.{key} must be positive, got: {value!r}")
    return float(value)


def parse_tuning_config(raw: Any) -> TuningConfig:
    """
    Parse the top-level ``tuning:`` block of a formation config.

    Absent block (None) returns the defaults -- every formation
    self-improves out of the box. ``tuning: false`` is accepted as
    shorthand for ``tuning: {active: false}``.

    Raises TuningConfigError on any structural problem -- a
    formation-load error, never a tuning-time surprise.
    """
    if raw is None:
        return TuningConfig()
    if raw is False:
        return TuningConfig(active=False)
    if raw is True:
        return TuningConfig()
    if not isinstance(raw, dict):
        raise TuningConfigError(f"tuning must be a mapping or a boolean, got: {type(raw).__name__}")

    unknown = sorted(set(raw) - _ALLOWED_TUNING_KEYS)
    if unknown:
        raise TuningConfigError(
            f"tuning has unknown key(s) {unknown}; "
            f"supported keys are {sorted(_ALLOWED_TUNING_KEYS)}"
        )

    return TuningConfig(
        active=_boolean(raw["active"], key="active") if "active" in raw else True,
        interval_hours=(
            _positive_number(raw["interval_hours"], key="interval_hours")
            if "interval_hours" in raw
            else DEFAULT_INTERVAL_HOURS
        ),
        auto_apply=(_boolean(raw["auto_apply"], key="auto_apply") if "auto_apply" in raw else True),
    )


__all__ = [
    "TuningConfig",
    "TuningConfigError",
    "parse_tuning_config",
    "DEFAULT_INTERVAL_HOURS",
]
