"""
Watch jobs (remote async tools).

Some MCP-reachable work outlives a turn: image/video generation, long
renders, batch jobs. The service submits fine (a normal sync tool call
returning ``{job_id, status: processing}``) but nothing ever collects it.
The built-in ``watch_job`` tool closes the loop: the agent registers a
watch, a deterministic poll loop calls the service's status tool at the
formation-configured cadence until a mechanical ``done_when`` selector
matches, and the result re-enters the conversation fenced as untrusted
content.

MUXI never classifies tools as async (PRD D1): async-ness is a property
of the RESPONSE, recognized contextually by the agent. Submit and poll
are ordinary sync tool calls; webhooks stay triggers (documented
patterns, not code).
"""

from .config import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_CONSECUTIVE_FAILURES,
    DEFAULT_TIMEOUT_SECONDS,
    WatchConfig,
    WatchConfigError,
    parse_watch_config,
)
from .models import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_ORPHANED,
    STATUS_TIMED_OUT,
    STATUS_WATCHING,
    TERMINAL_STATUSES,
    WatchJobRecord,
)
from .service import WatchJob, WatchService

__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_MAX_CONCURRENT",
    "DEFAULT_MAX_CONSECUTIVE_FAILURES",
    "DEFAULT_TIMEOUT_SECONDS",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_ORPHANED",
    "STATUS_TIMED_OUT",
    "STATUS_WATCHING",
    "TERMINAL_STATUSES",
    "WatchConfig",
    "WatchConfigError",
    "WatchJob",
    "WatchJobRecord",
    "WatchService",
    "parse_watch_config",
]
