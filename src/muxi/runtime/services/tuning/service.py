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
# Overlord, cancelled on shutdown), two steps per pass:
#
# 1. Digest: read the event spool since the last checkpoint, aggregate it
#    into a compact activity report, digest that into today's
#    formation-scope captain's log entry, then checkpoint (and delete the
#    digested segments unless the formation's yaml declared its own file
#    transport -- then the files are the dev's).
# 2. Tune: read the fresh digest, recent formation-log entries, and the
#    experiment memories; detect patterns; distill behavioral learnings
#    into a candidate MUXI.md revision (applied directly or written as
#    PENDING-MUXI.md per auto_apply); retire learnings whose watched
#    metric did not move; deliver a morning report.
# =============================================================================

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from .. import observability
from ..memory.log.formation import lint_formation_lines
from ..observability.spool import get_event_spool
from .config import TuningConfig
from .experiments import STATUS_ACTIVE, STATUS_PENDING, ExperimentStore
from .muxi_md import MUXI_MD_MAX_BYTES
from .tuner import TunerStep

# Bounds keeping the aggregated report LLM-sized regardless of spool size.
MAX_REPORT_CHARS = 8000
TOP_EVENT_TYPES = 20
MAX_SAMPLE_DESCRIPTIONS = 3
SAMPLE_DESCRIPTION_CHARS = 160
# Per-request token snapshots tracked during aggregation (last-write-wins
# per request id; capped so a huge interval cannot balloon memory).
MAX_TRACKED_REQUESTS = 5000


class TuningService:
    """Owns the tuning loop: digest step + tune step."""

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
        self.tuner = TunerStep()
        # Overrides the experiment store location (tests only; None means
        # the formation's observability directory).
        self.experiments_dir: Optional[str] = None
        # The apply/dismiss widget the last morning report carried, so a
        # channel button press can resolve regardless of which session
        # the reply arrives on (the report is formation-global).
        self.pending_widget: Optional[Dict[str, Any]] = None

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
        """Run one full pass (digest + tune); safe against overlaps."""
        async with self._run_lock:
            started = time.monotonic()
            spool = get_event_spool()
            segments, token = spool.read_for_digest()

            report, known_user_ids, event_count, metrics = await asyncio.to_thread(
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

            # Step 2: tune. Runs only on a consumed digest with traffic;
            # a tuner failure never breaks the pass (the digest already
            # reached its terminal outcome).
            tune_result: Dict[str, Any] = {}
            if committed and event_count > 0 and model is not None:
                try:
                    tune_result = await self._tune(model, report, metrics, known_user_ids)
                except Exception as e:
                    tune_result = {"tuner_error": f"{type(e).__name__}: {e}"}
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "service": "tuning",
                        },
                        description=f"Tune step failed: {e}",
                    )

            result = {
                "trigger": trigger,
                "events_read": event_count,
                "segments_read": len(token.segment_names),
                "entries_written": digest.get("entries", 0),
                "dropped_sentences": digest.get("dropped_sentences", 0),
                "spool_committed": committed,
                "spool_segments_kept": self.keep_spool_segments,
                **tune_result,
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

    # ------------------------------------------------------------------
    # Step 2: tune (detection, distillation, curation, morning report)
    # ------------------------------------------------------------------

    async def _tune(
        self,
        model,
        activity_report: str,
        metrics: Dict[str, float],
        known_user_ids: List[str],
    ) -> Dict[str, Any]:
        muxi_md = getattr(self.overlord, "muxi_md", None)
        if muxi_md is None:
            return {}

        store = ExperimentStore(self.experiments_dir)
        retired = store.evaluate_watch_windows(metrics)
        for record in retired:
            observability.observe(
                event_type=observability.SystemEvents.TUNING_RETIRED,
                level=observability.EventLevel.INFO,
                data={
                    "content_hash": record.get("content_hash"),
                    "metric_key": record.get("metric_key"),
                    "outcome": record.get("outcome"),
                },
                description="Tuning learning retired: watched metric did not move",
            )

        captains_log = getattr(self.overlord, "captains_log", None)
        formation_log_block = ""
        if captains_log is not None:
            formation_log_block = await captains_log.get_formation_context_block()

        prompt = self.tuner.build_prompt(
            activity_report=activity_report,
            current_muxi_md=muxi_md.read(),
            formation_log_block=formation_log_block,
            active_learnings=store.by_status(STATUS_ACTIVE),
            retired_learnings=retired,
            dismissed_learnings=[
                record.get("learning", "") for record in store.by_status("dismissed")
            ],
            metric_keys=sorted(metrics),
            max_bytes=MUXI_MD_MAX_BYTES,
        )
        # temperature=0: curation should be a deterministic distillation of
        # the report, not a creative writing pass.
        parsed = self.tuner.parse_response(
            await model.generate_text(prompt, temperature=0.0, caching=False)
        )
        if parsed is None:
            store.save()
            return {"learnings_retired": len(retired), "tuner_skipped": "unparseable_response"}

        # Record the distilled learnings; already-known hashes (dismissed,
        # retired, still-watched) are silently skipped -- never re-proposed.
        new_status = STATUS_ACTIVE if self.config.auto_apply else STATUS_PENDING
        recorded = []
        for item in parsed["learnings"]:
            baseline = metrics.get(item["metric_key"]) if item["metric_key"] else None
            proposal = store.propose(
                learning=item["learning"],
                evidence=item["evidence"],
                metric_key=item["metric_key"],
                baseline=baseline,
                status=new_status,
            )
            if proposal is not None:
                recorded.append(proposal)

        # Curate the file. The candidate passes the same privacy gate as
        # the formation log (line-level so markdown survives), and the
        # bounded-file contract is enforced on the tuner's own writes.
        applied = False
        suggested = False
        dropped_lines = 0
        candidate = parsed["muxi_md"]
        if candidate:
            candidate, dropped_lines = lint_formation_lines(candidate, known_user_ids)
        if not candidate and recorded:
            # The model sometimes records learnings without producing the
            # revised file; append them so the file never lags the store.
            current = muxi_md.read() or ""
            appended = "\n".join(f"- {record['learning']}" for record in recorded)
            fallback = f"{current}\n\n{appended}" if current else appended
            candidate, dropped_lines = lint_formation_lines(fallback, known_user_ids)
        rejected_oversize = False
        if candidate and len(candidate.encode("utf-8")) > MUXI_MD_MAX_BYTES:
            candidate = None
            rejected_oversize = True
        if candidate and candidate != (muxi_md.read() or ""):
            if self.config.auto_apply:
                muxi_md.write(candidate)
                applied = True
                observability.observe(
                    event_type=observability.SystemEvents.TUNING_APPLIED,
                    level=observability.EventLevel.INFO,
                    data={
                        "bytes": len(candidate.encode("utf-8")),
                        "learnings_recorded": len(recorded),
                        "dropped_lines": dropped_lines,
                    },
                    description="Tuner applied a MUXI.md revision (auto_apply)",
                )
            else:
                muxi_md.write_pending(candidate)
                suggested = True
                observability.observe(
                    event_type=observability.SystemEvents.TUNING_SUGGESTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "bytes": len(candidate.encode("utf-8")),
                        "learnings_recorded": len(recorded),
                        "dropped_lines": dropped_lines,
                    },
                    description="Tuner wrote a PENDING-MUXI.md suggestion",
                )
        store.save()

        report_delivery = await self._deliver_morning_report(
            applied=applied,
            suggested=suggested,
            recorded=recorded,
            retired=retired,
            recommendations=parsed["recommendations"],
        )

        return {
            "learnings_recorded": len(recorded),
            "learnings_retired": len(retired),
            "muxi_md_applied": applied,
            "muxi_md_suggested": suggested,
            "muxi_md_rejected_oversize": rejected_oversize,
            "recommendations": len(parsed["recommendations"]),
            "report_delivered": report_delivery,
        }

    async def _deliver_morning_report(
        self,
        *,
        applied: bool,
        suggested: bool,
        recorded: List[Dict[str, Any]],
        retired: List[Dict[str, Any]],
        recommendations: List[str],
    ) -> bool:
        """Deliver the morning report; False when there is nothing/nowhere.

        Recipient resolution follows the notification precedence from
        user "0" (the single-user identity): preferred channel >
        formation default_channel > async webhook. Formations without a
        ``proactive:`` block get no report -- the same state remains
        visible via /learnings and the /tuning API.
        """
        if not (applied or suggested or retired or recommendations):
            return False
        router = getattr(self.overlord, "notification_router", None)
        if router is None:
            return False

        lines: List[str] = ["Tuning report"]
        if applied:
            lines.append(
                "MUXI.md was updated with this pass's learnings (git history is the undo)."
            )
        if suggested:
            lines.append(
                "A suggested MUXI.md revision awaits review in PENDING-MUXI.md "
                "(diff it against the live file)."
            )
        if recorded:
            lines.append("New learnings:")
            lines.extend(f"- {record.get('learning')}" for record in recorded)
        if retired:
            lines.append("Retired (watched metric did not move):")
            lines.extend(f"- {record.get('learning')}" for record in retired)
        if recommendations:
            lines.append("Recommendations requiring a human deployment:")
            lines.extend(f"- {item}" for item in recommendations)

        widgets = None
        self.pending_widget = None
        if suggested:
            lines.append("Reply '/learnings apply' to accept or '/learnings dismiss' to discard.")
            from ...datatypes.ui import build_options_widget

            widget = build_options_widget(
                "Apply the suggested MUXI.md revision?",
                [
                    {"value": "apply", "label": "Apply"},
                    {"value": "dismiss", "label": "Dismiss"},
                ],
            )
            if widget is not None:
                widgets = [widget]
                self.pending_widget = {"ui_id": widget["id"], "ui_options": ["apply", "dismiss"]}

        result = await router.notify(
            user_id="0", message="\n".join(lines), source="tuning", ui=widgets
        )
        return bool(result.get("delivered"))

    # ------------------------------------------------------------------
    # Pending suggestion surface (/learnings, /tuning/pending, widget)
    # ------------------------------------------------------------------

    def apply_pending(self) -> Dict[str, Any]:
        """Promote PENDING-MUXI.md to live; opens the watch windows.

        Raises ValueError when no pending suggestion exists.
        """
        muxi_md = self.overlord.muxi_md
        path = muxi_md.promote_pending()
        store = ExperimentStore(self.experiments_dir)
        activated = store.activate_pending()
        store.save()
        self.pending_widget = None
        observability.observe(
            event_type=observability.SystemEvents.TUNING_APPLIED,
            level=observability.EventLevel.INFO,
            data={"path": path, "learnings_activated": len(activated)},
            description="Pending MUXI.md suggestion applied",
        )
        return {"path": path, "learnings_activated": len(activated)}

    def dismiss_pending(self) -> Dict[str, Any]:
        """Discard PENDING-MUXI.md; dismissed hashes are never re-proposed.

        Raises ValueError when no pending suggestion exists.
        """
        muxi_md = self.overlord.muxi_md
        if not muxi_md.discard_pending():
            raise ValueError("No pending MUXI.md suggestion to dismiss")
        store = ExperimentStore(self.experiments_dir)
        dismissed = store.dismiss_pending()
        store.save()
        self.pending_widget = None
        observability.observe(
            event_type=observability.SystemEvents.TUNING_DISMISSED,
            level=observability.EventLevel.INFO,
            data={"learnings_dismissed": len(dismissed)},
            description="Pending MUXI.md suggestion dismissed",
        )
        return {"learnings_dismissed": len(dismissed)}


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


def _aggregate_segments(spool, segments) -> Tuple[str, List[str], int, Dict[str, float]]:
    """Aggregate segments into (report, known_user_ids, count, metrics)."""
    stats = _SpoolStats()
    for event in spool.iter_events(segments):
        stats.add(event)
    return stats.render(), sorted(stats.user_ids), stats.total, stats.metric_snapshot()


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
        self.tool_failures: Dict[str, int] = {}
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
                tool = data.get("tool") if isinstance(data, dict) else None
                if isinstance(tool, str) and tool:
                    self.tool_failures[tool] = self.tool_failures.get(tool, 0) + 1

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

    def metric_snapshot(self) -> Dict[str, float]:
        """Closed set of lower-is-better rates for watch-window checks.

        Keys: ``error_rate``, ``warning_rate``, and ``problem:<event>``
        per warning/error event type. Baselines are frozen from this
        snapshot at proposal time; later snapshots verify movement.
        """
        if self.total == 0:
            return {}
        metrics: Dict[str, float] = {
            "error_rate": self.level_counts.get("error", 0) / self.total,
            "warning_rate": self.level_counts.get("warning", 0) / self.total,
        }
        for name, count in self.problem_counts.items():
            metrics[f"problem:{name}"] = count / self.total
        return metrics

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

        if self.tool_failures:
            lines.append("Failing tools (by name):")
            ranked = sorted(self.tool_failures.items(), key=lambda item: -item[1])
            for tool, count in ranked[:TOP_EVENT_TYPES]:
                lines.append(f"- {tool}: {count} failure(s)")

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
