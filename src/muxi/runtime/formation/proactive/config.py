"""
Parsing and validation for the formation-level ``proactive:`` block.

The block is entirely optional. When absent, ``parse_proactive_config``
returns ``None`` and the runtime behaves exactly as before. When present,
parsing fails fast with a descriptive ``ValueError`` on any structural
problem (the formation validator reuses this parser so the validator and
the runtime can never disagree about what a valid block looks like).

Schema:

    proactive:
      channels:
        telegram:
          transformer: telegram-notify   # transformers/telegram-notify.yaml
        slack:
          transformer: slack            # bundled template (payload only)...
          url: "${{ secrets.SLACK_BRIDGE_URL }}"  # ...so the channel supplies the URL
      default_channel: telegram          # optional: channel name or "webhook"
      heartbeat:                         # optional
        enabled: true                    # default true when block present
        interval: "30m"                  # 45s / 30m / 2h, optional "every " prefix
        target: "last"                   # last | preferred | webhook | <channel>
        active_hours:                    # optional: absent means always active
          start: "09:00"
          end: "18:00"
          timezone: "UTC"                # IANA name, or "user" for per-user tz
          weekends: true                 # false suppresses Saturday/Sunday
        instruction: "..."               # optional extra prompt content
        sop: my-heartbeat                # optional SOP name for the base prompt
                                         # (absent: bundled default heartbeat SOP)
"""

import re
from dataclasses import dataclass, field
from datetime import time as dt_time
from typing import Any, Dict, Optional

import pytz

# Channel names share the trigger/transformer charset (they are config keys
# and appear in template contexts, never resolved as filesystem paths).
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

_INTERVAL_PATTERN = re.compile(r"^(?:every\s+)?(\d+)\s*(s|m|h)$", re.IGNORECASE)

_TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

# Reserved routing targets that are not concrete channel names
WEBHOOK_TARGET = "webhook"
LAST_TARGET = "last"
PREFERRED_TARGET = "preferred"
RESERVED_TARGETS = {WEBHOOK_TARGET, LAST_TARGET, PREFERRED_TARGET}

_ALLOWED_PROACTIVE_KEYS = {"channels", "default_channel", "heartbeat"}
_ALLOWED_CHANNEL_KEYS = {"transformer", "url"}

# ${{ ... }} placeholder marker: channel URLs may be templates (e.g. a
# secret-backed Slack incoming-webhook URL) instead of literal http(s) URLs.
_PLACEHOLDER_MARKER = "${{"
_ALLOWED_HEARTBEAT_KEYS = {"enabled", "interval", "target", "active_hours", "instruction", "sop"}
_ALLOWED_ACTIVE_HOURS_KEYS = {"start", "end", "timezone", "weekends"}

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30 * 60  # "30m"


@dataclass
class ChannelConfig:
    """A notification channel backed by a trigger transformer.

    ``url`` optionally supplies/overrides the delivery destination: it wins
    over the transformer's own ``endpoint.url``, and is required (at load
    time) when the transformer defines none (e.g. the bundled payload-only
    channel templates).
    """

    name: str
    transformer: str
    url: Optional[str] = None


@dataclass
class ActiveHoursConfig:
    """Active-hours gate for the heartbeat."""

    start: dt_time
    end: dt_time
    timezone: str = "UTC"  # IANA timezone name or "user"
    weekends: bool = True


@dataclass
class HeartbeatConfig:
    """Heartbeat configuration (periodic proactive check-ins)."""

    enabled: bool = True
    interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    target: str = LAST_TARGET
    active_hours: Optional[ActiveHoursConfig] = None
    instruction: Optional[str] = None
    sop: Optional[str] = None


@dataclass
class ProactiveConfig:
    """Parsed and validated ``proactive:`` formation block."""

    channels: Dict[str, ChannelConfig] = field(default_factory=dict)
    default_channel: Optional[str] = None
    heartbeat: Optional[HeartbeatConfig] = None


def parse_interval(raw: Any) -> int:
    """
    Parse a heartbeat interval expression into seconds.

    Accepts ``45s``, ``30m``, ``2h`` with an optional ``every`` prefix
    (e.g. ``every 30m``). Fails fast on anything else.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            "'proactive.heartbeat.interval' must be a duration string like '30m', '2h', or '45s'"
        )
    match = _INTERVAL_PATTERN.match(raw.strip())
    if not match:
        raise ValueError(
            f"invalid 'proactive.heartbeat.interval' {raw!r}: use '<N>s', '<N>m', or '<N>h' "
            "(optionally prefixed with 'every ')"
        )
    value = int(match.group(1))
    if value <= 0:
        raise ValueError("'proactive.heartbeat.interval' must be a positive duration")
    unit = match.group(2).lower()
    return value * {"s": 1, "m": 60, "h": 3600}[unit]


def _parse_time(raw: Any, where: str) -> dt_time:
    """Parse an HH:MM string into a time object, failing fast."""
    if not isinstance(raw, str) or not _TIME_PATTERN.match(raw.strip()):
        raise ValueError(f"'{where}' must be a 24-hour 'HH:MM' string, got {raw!r}")
    hour, minute = raw.strip().split(":")
    return dt_time(int(hour), int(minute))


def _parse_active_hours(raw: Any) -> ActiveHoursConfig:
    """Parse and validate the ``active_hours`` section."""
    if not isinstance(raw, dict):
        raise ValueError("'proactive.heartbeat.active_hours' must be a mapping")
    unknown = set(raw.keys()) - _ALLOWED_ACTIVE_HOURS_KEYS
    if unknown:
        raise ValueError(
            f"unknown 'proactive.heartbeat.active_hours' key(s): {sorted(unknown)}. "
            f"Allowed keys: {sorted(_ALLOWED_ACTIVE_HOURS_KEYS)}"
        )
    if "start" not in raw or "end" not in raw:
        raise ValueError("'proactive.heartbeat.active_hours' requires both 'start' and 'end'")

    start = _parse_time(raw["start"], "proactive.heartbeat.active_hours.start")
    end = _parse_time(raw["end"], "proactive.heartbeat.active_hours.end")

    timezone = raw.get("timezone", "UTC")
    if not isinstance(timezone, str) or not timezone.strip():
        raise ValueError("'proactive.heartbeat.active_hours.timezone' must be a non-empty string")
    timezone = timezone.strip()
    if timezone != "user":
        try:
            pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(
                f"unknown timezone {timezone!r} in 'proactive.heartbeat.active_hours.timezone' "
                "(use an IANA name like 'Europe/London', or 'user' for per-user timezones)"
            )

    weekends = raw.get("weekends", True)
    if not isinstance(weekends, bool):
        raise ValueError("'proactive.heartbeat.active_hours.weekends' must be a boolean")

    return ActiveHoursConfig(start=start, end=end, timezone=timezone, weekends=weekends)


def _parse_heartbeat(raw: Any, channels: Dict[str, ChannelConfig]) -> HeartbeatConfig:
    """Parse and validate the ``heartbeat`` section."""
    if not isinstance(raw, dict):
        raise ValueError("'proactive.heartbeat' must be a mapping")
    unknown = set(raw.keys()) - _ALLOWED_HEARTBEAT_KEYS
    if unknown:
        raise ValueError(
            f"unknown 'proactive.heartbeat' key(s): {sorted(unknown)}. "
            f"Allowed keys: {sorted(_ALLOWED_HEARTBEAT_KEYS)}"
        )

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("'proactive.heartbeat.enabled' must be a boolean")

    interval_seconds = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    if raw.get("interval") is not None:
        interval_seconds = parse_interval(raw["interval"])

    target = raw.get("target", LAST_TARGET)
    if not isinstance(target, str) or not target.strip():
        raise ValueError("'proactive.heartbeat.target' must be a non-empty string")
    target = target.strip()
    if target not in RESERVED_TARGETS and target not in channels:
        raise ValueError(
            f"'proactive.heartbeat.target' {target!r} is not a declared channel. "
            f"Use one of {sorted(RESERVED_TARGETS)} or a channel from 'proactive.channels': "
            f"{sorted(channels)}"
        )

    active_hours = None
    if raw.get("active_hours") is not None:
        active_hours = _parse_active_hours(raw["active_hours"])

    instruction = raw.get("instruction")
    if instruction is not None and (not isinstance(instruction, str) or not instruction.strip()):
        raise ValueError("'proactive.heartbeat.instruction' must be a non-empty string")

    sop = raw.get("sop")
    if sop is not None:
        if not isinstance(sop, str) or not _NAME_PATTERN.match(sop):
            raise ValueError(
                "'proactive.heartbeat.sop' must be an SOP name containing only letters, "
                "numbers, hyphens, and underscores"
            )

    return HeartbeatConfig(
        enabled=enabled,
        interval_seconds=interval_seconds,
        target=target,
        active_hours=active_hours,
        instruction=instruction.strip() if isinstance(instruction, str) else None,
        sop=sop,
    )


def parse_proactive_config(raw: Any) -> Optional[ProactiveConfig]:
    """
    Parse the formation-level ``proactive:`` block.

    Args:
        raw: The raw ``proactive`` value from the formation config (or None)

    Returns:
        ProactiveConfig, or None when the block is absent (inert)

    Raises:
        ValueError: On any structural problem, with a descriptive message
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("'proactive' must be a mapping")

    unknown = set(raw.keys()) - _ALLOWED_PROACTIVE_KEYS
    if unknown:
        raise ValueError(
            f"unknown 'proactive' key(s): {sorted(unknown)}. "
            f"Allowed keys: {sorted(_ALLOWED_PROACTIVE_KEYS)}"
        )

    channels: Dict[str, ChannelConfig] = {}
    raw_channels = raw.get("channels") or {}
    if not isinstance(raw_channels, dict):
        raise ValueError("'proactive.channels' must be a mapping of channel name -> config")
    for name, channel_raw in raw_channels.items():
        if not isinstance(name, str) or not _NAME_PATTERN.match(name):
            raise ValueError(
                f"invalid channel name {name!r}: must contain only letters, numbers, "
                "hyphens, and underscores"
            )
        if name in RESERVED_TARGETS:
            raise ValueError(
                f"channel name {name!r} is reserved for routing "
                f"(reserved names: {sorted(RESERVED_TARGETS)})"
            )
        if not isinstance(channel_raw, dict):
            raise ValueError(f"'proactive.channels.{name}' must be a mapping")
        unknown_channel = set(channel_raw.keys()) - _ALLOWED_CHANNEL_KEYS
        if unknown_channel:
            raise ValueError(
                f"unknown 'proactive.channels.{name}' key(s): {sorted(unknown_channel)}. "
                f"Allowed keys: {sorted(_ALLOWED_CHANNEL_KEYS)}"
            )
        transformer = channel_raw.get("transformer")
        if not isinstance(transformer, str) or not _NAME_PATTERN.match(transformer):
            raise ValueError(
                f"'proactive.channels.{name}.transformer' is required and must be a "
                "transformer name containing only letters, numbers, hyphens, and underscores"
            )
        url = channel_raw.get("url")
        if url is not None:
            if not isinstance(url, str) or not url.strip():
                raise ValueError(f"'proactive.channels.{name}.url' must be a non-empty string")
            url = url.strip()
            if _PLACEHOLDER_MARKER not in url and not url.startswith(("http://", "https://")):
                raise ValueError(
                    f"'proactive.channels.{name}.url' must be an http(s) URL or a "
                    "template containing ${{ ... }} placeholders"
                )
        channels[name] = ChannelConfig(name=name, transformer=transformer, url=url)

    default_channel = raw.get("default_channel")
    if default_channel is not None:
        if not isinstance(default_channel, str) or not default_channel.strip():
            raise ValueError("'proactive.default_channel' must be a non-empty string")
        default_channel = default_channel.strip()
        if default_channel != WEBHOOK_TARGET and default_channel not in channels:
            raise ValueError(
                f"'proactive.default_channel' {default_channel!r} is not a declared channel. "
                f"Use 'webhook' or a channel from 'proactive.channels': {sorted(channels)}"
            )

    heartbeat = None
    if raw.get("heartbeat") is not None:
        heartbeat = _parse_heartbeat(raw["heartbeat"], channels)

    return ProactiveConfig(
        channels=channels,
        default_channel=default_channel,
        heartbeat=heartbeat,
    )
