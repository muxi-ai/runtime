# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Tuning Service - The Self-Improvement Loop
# Description:  Scheduled spool digest into the formation captain's log
# Role:         Owns the tuning loop (Phase 1: digest step only)
# Usage:        Created + started by the Overlord when tuning.active
# Author:       Muxi Framework Team
#
# Self-Improving Formation PRD, "The loop". One scheduled in-runtime job
# (tuning.interval_hours, CaptainsLog lifecycle idiom: started by the
# Overlord, cancelled on shutdown), Phase 1 scope: read the event spool
# since the last checkpoint, aggregate it into a compact activity report,
# digest that into today's formation-scope captain's log entry, then
# checkpoint (and delete the digested segments unless the formation's
# yaml declared its own file transport -- then the files are the dev's).
#
# Phase 2 adds the tuner step (detection, distillation, MUXI.md curation,
# pending flow, morning report) behind the same loop.
# =============================================================================

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from .. import observability
from ..observability.spool import get_event_spool
from .config import TuningConfig

# Bounds keeping the aggregated report LLM-sized regardless of spool size.
MAX_REPORT_CHARS = 8000
TOP_EVENT_TYPES = 20
MAX_SAMPLE_DESCRIPTIONS = 3
SAMPLE_DESCRIPTION_CHARS = 160
# Per-request token snapshots tracked during aggregation (last-write-wins
# per request id; capped so a huge interval cannot balloon memory).
MAX_TRACKED_REQUESTS = 5000


class TuningService:
    """Owns the tuning loop; Phase 1 runs the digest step only."""

    def __init__(
        self,
        config: TuningConfig,
        overlord,
        keep_spool_segments: bool = False,
    ):
        """
        Args:
            config: Parsed ``tuning:`` block (defaults when absent).
            overlord: The owning Overlord (captains_log + model access).
            keep_spool_segments: True when the formation's yaml declares a
                file transport -- digested segments are then kept (their
                rotation config governs; digestion never deletes).
        """
        self.config = config
        self.overlord = overlord
        self.keep_spool_segments = keep_spool_segments
        self.interval_seconds = config.interval_hours * 3600.0
        self._task: Optional[asyncio.Task] = None
        self._run_lock = asyncio.Lock()
        self.last_run: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Lifecycle (CaptainsLog idiom: overlord starts, shutdown cancels)
    # ------------------------------------------------------------------

    def start(self, model_getter) -> None:
        """Start the scheduled loop; first pass one full interval in."""
        if not self.config.active:
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(model_getter))

    async def stop(self) -> None:
        """Cancel the loop, if running."""
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, model_getter) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                await self.run_once(model_getter(), trigger="scheduled")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "error_type": type(e).__name__, "service": "tuning"},
                    description=f"Tuning loop pass failed: {e}",
                )

    # ------------------------------------------------------------------
    # One loop pass (scheduled, or POST /tuning/run)
    # ------------------------------------------------------------------

    async def run_once(self, model, trigger: str = "manual") -> Dict[str, Any]:
        """Run one digest pass; safe against overlapping invocations."""
        async with self._run_lock:
            started = time.monotonic()
            spool = get_event_spool()
            segments, token = spool.read_for_digest()

            report, known_user_ids, event_count = await asyncio.to_thread(
                _aggregate_segments, spool, segments
            )

            captains_log = getattr(self.overlord, "captains_log", None)
            if captains_log is not None:
                digest = await captains_log.digest_formation(
                    report, model, known_user_ids=known_user_ids
                )
            else:
                # No narrative layer exists to consume the spool; the
                # segments still reach their terminal outcome.
                digest = {"entries": 0, "dropped_sentences": 0, "consumed": True}

            committed = bool(digest.get("consumed"))
            if committed:
                spool.commit(token, delete=not self.keep_spool_segments)

            result = {
                "trigger": trigger,
                "events_read": event_count,
                "segments_read": len(token.segment_names),
                "entries_written": digest.get("entries", 0),
                "dropped_sentences": digest.get("dropped_sentences", 0),
                "spool_committed": committed,
                "spool_segments_kept": self.keep_spool_segments,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }
            self.last_run = result
            observability.observe(
                event_type=observability.SystemEvents.TUNING_RUN,
                level=observability.EventLevel.INFO,
                data=result,
                description=(
                    f"Tuning pass ({trigger}) digested {event_count} event(s) into "
                    f"{result['entries_written']} formation log entr(y/ies)"
                ),
            )
            return result


def yaml_declares_file_transport(logging_config: Optional[Dict[str, Any]]) -> bool:
    """True when the formation's ``logging:`` yaml declares a file destination.

    The PRD's retention rule: spool segments are an internal buffer and are
    deleted once digested -- UNLESS the dev declared file logging, in which
    case segment files are kept (they are the dev's telemetry; digestion
    never deletes).
    """
    if not isinstance(logging_config, dict):
        return False
    system_destination = (logging_config.get("system") or {}).get("destination")
    if isinstance(system_destination, str) and system_destination not in ("", "stdout"):
        return True
    conversation = logging_config.get("conversation") or {}
    for stream in conversation.get("streams") or []:
        if (
            isinstance(stream, dict)
            and stream.get("transport") == "file"
            and stream.get("destination")
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Spool aggregation: raw JSONL events -> compact operational report.
# Runs in a worker thread (segments can be large); the LLM only ever sees
# the bounded report, never raw events.
# ---------------------------------------------------------------------------


def _aggregate_segments(spool, segments) -> Tuple[str, List[str], int]:
    """Aggregate spool segments into (report, known_user_ids, event_count)."""
    stats = _SpoolStats()
    for event in spool.iter_events(segments):
        stats.add(event)
    return stats.render(), sorted(stats.user_ids), stats.total


class _SpoolStats:
    """Streaming accumulator over spool events."""

    def __init__(self):
        self.total = 0
        self.first_ts: Optional[int] = None
        self.last_ts: Optional[int] = None
        self.event_counts: Dict[str, int] = {}
        self.level_counts: Dict[str, int] = {}
        self.problem_counts: Dict[str, int] = {}
        self.problem_samples: Dict[str, List[str]] = {}
        self.user_ids: Set[str] = set()
        self.session_ids: Set[str] = set()
        self.request_tokens: Dict[str, Dict[str, Any]] = {}

    def add(self, event: Dict[str, Any]) -> None:
        self.total += 1
        name = event.get("event")
        if isinstance(name, str):
            self.event_counts[name] = self.event_counts.get(name, 0) + 1

        timestamp = event.get("timestamp")
        if isinstance(timestamp, int):
            if self.first_ts is None or timestamp < self.first_ts:
                self.first_ts = timestamp
            if self.last_ts is None or timestamp > self.last_ts:
                self.last_ts = timestamp

        level = event.get("level")
        if isinstance(level, str):
            self.level_counts[level] = self.level_counts.get(level, 0) + 1
            if level in ("warning", "error") and isinstance(name, str):
                self.problem_counts[name] = self.problem_counts.get(name, 0) + 1
                data = event.get("data")
                description = data.get("description") if isinstance(data, dict) else None
                if isinstance(description, str) and description:
                    samples = self.problem_samples.setdefault(name, [])
                    if len(samples) < MAX_SAMPLE_DESCRIPTIONS:
                        snippet = description[:SAMPLE_DESCRIPTION_CHARS]
                        if snippet not in samples:
                            samples.append(snippet)

        request = event.get("request")
        if isinstance(request, dict):
            user_id = request.get("user_id")
            if isinstance(user_id, str) and user_id:
                self.user_ids.add(user_id)
            request_id = request.get("id")
            tokens = request.get("tokens")
            if isinstance(request_id, str) and isinstance(tokens, dict):
                # Last snapshot per request wins (token counts are running
                # totals within one request's lifecycle).
                if request_id in self.request_tokens or (
                    len(self.request_tokens) < MAX_TRACKED_REQUESTS
                ):
                    self.request_tokens[request_id] = tokens
        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id:
            self.session_ids.add(session_id)

        data = event.get("data")
        if isinstance(data, dict):
            data_user = data.get("user_id")
            if isinstance(data_user, str) and data_user:
                self.user_ids.add(data_user)

    def render(self) -> str:
        """Render the bounded plain-text activity report."""
        if self.total == 0:
            return ""
        lines: List[str] = []
        window = ""
        if self.first_ts is not None and self.last_ts is not None:
            window = f" spanning {_format_ts(self.first_ts)} to {_format_ts(self.last_ts)} (UTC)"
        lines.append(
            f"Window: {self.total} events{window}; "
            f"{len(self.user_ids)} distinct user(s), {len(self.session_ids)} session(s), "
            f"{len(self.request_tokens)} tracked request(s)."
        )

        levels = ", ".join(f"{level}={count}" for level, count in sorted(self.level_counts.items()))
        if levels:
            lines.append(f"Event levels: {levels}.")

        top = sorted(self.event_counts.items(), key=lambda item: -item[1])[:TOP_EVENT_TYPES]
        if top:
            lines.append("Top event types:")
            for name, count in top:
                lines.append(f"- {name}: {count}")

        if self.problem_counts:
            lines.append("Warning/error clusters:")
            for name, count in sorted(self.problem_counts.items(), key=lambda item: -item[1]):
                lines.append(f"- {name}: {count}")
                for sample in self.problem_samples.get(name, []):
                    lines.append(f"  e.g. {sample}")

        token_total, model_totals = self._token_totals()
        if token_total:
            lines.append(f"Total tokens across tracked requests: {token_total}.")
        if model_totals:
            lines.append("Token usage by model:")
            for model_name, count in sorted(model_totals.items(), key=lambda item: -item[1]):
                lines.append(f"- {model_name}: {count}")

        report = "\n".join(lines)
        return report[:MAX_REPORT_CHARS]

    def _token_totals(self) -> Tuple[int, Dict[str, int]]:
        total = 0
        model_totals: Dict[str, int] = {}
        for tokens in self.request_tokens.values():
            values = tokens.get("total")
            if isinstance(values, list) and values and isinstance(values[0], int):
                total += values[0]
            breakdown = tokens.get("breakdown")
            if isinstance(breakdown, dict):
                for model_name, model_values in breakdown.items():
                    if (
                        isinstance(model_values, list)
                        and model_values
                        and isinstance(model_values[0], int)
                    ):
                        model_totals[model_name] = model_totals.get(model_name, 0) + model_values[0]
        return total, model_totals


def _format_ts(timestamp_ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


__all__ = ["TuningService", "yaml_declares_file_transport"]
