"""
Watch-job configuration (the ``mcp.watch`` sub-block).

Cadence and deadline are formation configuration, NOT agent arguments
(remote-async-tools PRD, owner ruling 2026-07-11): polls are zero-token
deterministic tool calls, so a uniform formation-set interval is cheap
even when suboptimal for a given job, and numeric knobs are exactly what
LLMs pick badly.

Default ON whenever the formation declares MCP servers -- the tool
grants no new capability (it can only call MCP tools the caller could
already call, under the caller's own GBAC context). There is no
``enabled:`` key; the sole escape hatch is ``mcp: { watch: false }``
(tool-catalog hygiene / strict no-background-work compliance postures).
Closed key set, fail-fast validation at formation load.
"""

from dataclasses import dataclass
from typing import Any, Optional

_ALLOWED_WATCH_KEYS = {"interval", "timeout", "max_concurrent", "max_consecutive_failures"}

DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_TIMEOUT_SECONDS = 7200
DEFAULT_MAX_CONCURRENT = 10
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3


class WatchConfigError(ValueError):
    """Raised for any invalid ``mcp.watch`` configuration (fail fast at load)."""


@dataclass
class WatchConfig:
    """Parsed ``mcp.watch`` block (or the defaults, when the block is absent)."""

    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_concurrent: int = DEFAULT_MAX_CONCURRENT  # active watches per user
    max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES


def _positive_number(value: Any, *, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WatchConfigError(f"mcp.watch.{key} must be a number of seconds, got: {value!r}")
    if value <= 0:
        raise WatchConfigError(f"mcp.watch.{key} must be positive, got: {value!r}")
    return float(value)


def _positive_int(value: Any, *, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WatchConfigError(f"mcp.watch.{key} must be an integer >= 1, got: {value!r}")
    if value < 1:
        raise WatchConfigError(f"mcp.watch.{key} must be an integer >= 1, got: {value!r}")
    return value


def parse_watch_config(mcp_raw: Any) -> Optional[WatchConfig]:
    """
    Parse the ``watch:`` sub-block of a formation's ``mcp:`` block.

    Returns None when the feature is off: no ``mcp:`` block, no declared
    ``mcp.servers`` (there is nothing to watch), or the explicit escape
    hatch ``watch: false``. Absent ``watch:`` (with servers declared)
    returns the defaults -- the feature is ON by default.

    Raises WatchConfigError on any structural problem -- a formation-load
    error, never a watch-time surprise.
    """
    if mcp_raw is None:
        return None
    if not isinstance(mcp_raw, dict):
        # The mcp block's own shape is validated elsewhere; nothing to do.
        return None

    # "The formation has MCP servers" means DECLARED servers -- the raw
    # servers list before built-in MCP injection.
    servers = mcp_raw.get("servers")
    has_servers = isinstance(servers, list) and len(servers) > 0

    raw = mcp_raw.get("watch")
    if raw is False:
        return None
    if raw is None or raw is True:
        return WatchConfig() if has_servers else None
    if not isinstance(raw, dict):
        raise WatchConfigError(f"mcp.watch must be a mapping or false, got: {type(raw).__name__}")

    unknown = sorted(set(raw) - _ALLOWED_WATCH_KEYS)
    if unknown:
        raise WatchConfigError(
            f"mcp.watch has unknown key(s) {unknown}; "
            f"supported keys are {sorted(_ALLOWED_WATCH_KEYS)}"
        )

    config = WatchConfig(
        interval_seconds=(
            _positive_number(raw["interval"], key="interval")
            if "interval" in raw
            else DEFAULT_INTERVAL_SECONDS
        ),
        timeout_seconds=(
            _positive_number(raw["timeout"], key="timeout")
            if "timeout" in raw
            else DEFAULT_TIMEOUT_SECONDS
        ),
        max_concurrent=(
            _positive_int(raw["max_concurrent"], key="max_concurrent")
            if "max_concurrent" in raw
            else DEFAULT_MAX_CONCURRENT
        ),
        max_consecutive_failures=(
            _positive_int(raw["max_consecutive_failures"], key="max_consecutive_failures")
            if "max_consecutive_failures" in raw
            else DEFAULT_MAX_CONSECUTIVE_FAILURES
        ),
    )
    if not has_servers:
        # A watch block without servers is dead config -- fail fast so the
        # author learns at load, not when the tool never appears.
        raise WatchConfigError(
            "mcp.watch is configured but mcp.servers declares no servers; "
            "watch_job only exists when the formation has MCP tools to watch"
        )
    return config


__all__ = [
    "WatchConfig",
    "WatchConfigError",
    "parse_watch_config",
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_CONCURRENT",
    "DEFAULT_MAX_CONSECUTIVE_FAILURES",
]
