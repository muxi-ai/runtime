"""
Proactive foundation: notification routing, user channel state, and heartbeat.

This package implements Phase 1 of the proactiveness PRD as infrastructure
mechanisms only:

- ``config``: fail-fast parsing of the formation-level ``proactive:`` block
- ``user_channels``: per-user channel state (preferred channel, per-channel
  addressing context, last-used channel, timezone)
- ``router``: notification routing through trigger transformers with webhook
  fallback (reuses the transformer delivery machinery)
- ``heartbeat``: periodic proactive check-ins driven by the scheduler service,
  gated by active hours

Formations without a ``proactive:`` block are completely unaffected: no
services are created and every hook is a no-op.
"""

from .config import (
    ActiveHoursConfig,
    ChannelConfig,
    HeartbeatConfig,
    ProactiveConfig,
    parse_proactive_config,
)
from .heartbeat import (
    DEFAULT_HEARTBEAT_PROMPT,
    HEARTBEAT_OK_SENTINEL,
    HEARTBEAT_SESSION_PREFIX,
    HeartbeatService,
    load_default_heartbeat_sop,
)
from .router import WEBHOOK_CHANNEL, NotificationRouter
from .user_channels import UserChannelState, UserChannelStore

__all__ = [
    "ActiveHoursConfig",
    "ChannelConfig",
    "DEFAULT_HEARTBEAT_PROMPT",
    "HEARTBEAT_OK_SENTINEL",
    "HEARTBEAT_SESSION_PREFIX",
    "HeartbeatConfig",
    "HeartbeatService",
    "NotificationRouter",
    "ProactiveConfig",
    "UserChannelState",
    "UserChannelStore",
    "WEBHOOK_CHANNEL",
    "load_default_heartbeat_sop",
    "parse_proactive_config",
]
