# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Event Spool - Internal Observability Retention Buffer
# Description:  Always-on JSONL segment store feeding the tuning digest loop
# Role:         Short-lived operational telemetry buffer (self-improvement)
# Usage:        Written by EventLogger's writer thread; read by TuningService
# Author:       Muxi Framework Team
#
# Self-Improving Formation PRD, part 1 (event spool). The runtime always
# tees emitted observability events into segment files in the formation's
# observability directory, regardless of what the ``logging:`` yaml
# declares. Not configuration, not AFS surface: internal format, bounded
# by an internal cap, consumed solely by the tuning loop's digest step.
#
# Retention contract:
# - The tuning loop is the single consumer; it checkpoints the last fully
#   digested segment. ``read_for_digest`` rotates the active segment first
#   so every segment it returns is closed and fully digestible.
# - ``commit(delete=True)`` (no file transport declared in the yaml)
#   deletes digested segments -- steady-state disk is about one interval.
#   ``commit(delete=False)`` (dev declared a file transport) keeps them.
# - Total spool size is bounded by SPOOL_MAX_BYTES: oldest closed segments
#   drop with a ``spool.overrun`` event rather than eating the disk.
#
# Threading: writes arrive from EventLogger writer threads (one per logger
# instance; the logger is replaced at server-ready, so two writer threads
# can briefly coexist), reads from the tuning loop via asyncio.to_thread.
# One lock serializes all segment mutation.
# =============================================================================

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ...utils.datetime_utils import utc_now_naive
from ...utils.fastjson import json
from ...utils.user_dirs import get_observability_dir

# Internal constants -- deliberately not configuration (PRD: the spool has
# no yaml key; nothing external should parse or tune it).
SEGMENT_MAX_BYTES = 32 * 1024 * 1024
SPOOL_MAX_BYTES = 512 * 1024 * 1024
SEGMENT_PREFIX = "events-"
SEGMENT_SUFFIX = ".jsonl"
CHECKPOINT_FILE = "checkpoint.json"

# Rate limit for spool.overrun emission so a sustained overrun does not
# turn into an event storm (the overrun event itself is spooled).
OVERRUN_EVENT_MIN_INTERVAL_SECONDS = 60.0


class EventSpool:
    """Segmented JSONL spool with rotation, a size cap, and a checkpoint."""

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self._lock = threading.Lock()
        self._current: Optional[Path] = None
        self._pending_new_segment = False
        self._last_overrun_emit = 0.0

    # ------------------------------------------------------------------
    # Write side (EventLogger writer thread)
    # ------------------------------------------------------------------

    def write_lines(self, event_lines: List[str]) -> None:
        """Append JSONL event lines to the active segment.

        Rotates by day and by segment size, then enforces the total cap.
        Never raises: the spool must never disrupt the writer thread.
        """
        if not event_lines:
            return
        try:
            with self._lock:
                self.base_dir.mkdir(parents=True, exist_ok=True)
                segment = self._active_segment()
                payload = "\n".join(event_lines) + "\n"
                with open(segment, "a", encoding="utf-8") as f:
                    f.write(payload)
                self._enforce_cap()
        except Exception:
            pass

    def _active_segment(self) -> Path:
        """Resolve the segment to append to, rotating on day/size change."""
        today = utc_now_naive().strftime("%Y%m%d")
        current = self._current
        if current is None and not self._pending_new_segment:
            # Restart resume: continue the latest segment ONLY when it has
            # not been digested yet -- appending to a checkpointed segment
            # would hide those events from every future read.
            current = self._latest_segment()
            checkpoint = self._read_checkpoint()
            if current is not None and checkpoint is not None and current.name <= checkpoint:
                current = None
        if current is not None and current.name.startswith(f"{SEGMENT_PREFIX}{today}-"):
            try:
                if current.exists() and current.stat().st_size < SEGMENT_MAX_BYTES:
                    self._current = current
                    return current
            except OSError:
                pass
        self._pending_new_segment = False
        self._current = self._next_segment_path(today)
        return self._current

    def _latest_segment(self) -> Optional[Path]:
        segments = self._list_segments()
        return segments[-1] if segments else None

    def _next_segment_path(self, today: str) -> Path:
        """Next per-day sequence number; names sort lexicographically."""
        prefix = f"{SEGMENT_PREFIX}{today}-"
        max_seq = 0
        for segment in self._list_segments():
            if segment.name.startswith(prefix):
                seq_text = segment.name[len(prefix) : -len(SEGMENT_SUFFIX)]
                try:
                    max_seq = max(max_seq, int(seq_text))
                except ValueError:
                    continue
        return self.base_dir / f"{prefix}{max_seq + 1:04d}{SEGMENT_SUFFIX}"

    def _list_segments(self) -> List[Path]:
        """All segment files, lexicographic order == chronological order."""
        try:
            return sorted(
                p
                for p in self.base_dir.iterdir()
                if p.name.startswith(SEGMENT_PREFIX) and p.name.endswith(SEGMENT_SUFFIX)
            )
        except OSError:
            return []

    def _enforce_cap(self) -> None:
        """Drop oldest closed segments while the spool exceeds the cap."""
        segments = self._list_segments()
        sizes = {}
        for segment in segments:
            try:
                sizes[segment] = segment.stat().st_size
            except OSError:
                sizes[segment] = 0
        total = sum(sizes.values())
        if total <= SPOOL_MAX_BYTES:
            return

        dropped: List[str] = []
        dropped_bytes = 0
        for segment in segments:
            if total <= SPOOL_MAX_BYTES:
                break
            if segment == self._current:
                break  # never drop the active segment
            try:
                segment.unlink()
            except OSError:
                continue
            total -= sizes[segment]
            dropped_bytes += sizes[segment]
            dropped.append(segment.name)

        if dropped:
            self._emit_overrun(dropped, dropped_bytes, total)

    def _emit_overrun(self, dropped: List[str], dropped_bytes: int, total: int) -> None:
        """Report an overrun, rate-limited to avoid an event storm.

        Two paths: a marker line appended straight into the active
        segment (unfilterable -- the digest must always learn that
        retained events were dropped, whatever the ``logging:`` levels
        say), plus a regular spool.overrun event for external telemetry.
        """
        now = time.time()
        if now - self._last_overrun_emit < OVERRUN_EVENT_MIN_INTERVAL_SECONDS:
            return
        self._last_overrun_emit = now

        overrun_data = {
            "dropped_segments": dropped,
            "dropped_bytes": dropped_bytes,
            "spool_bytes": total,
            "cap_bytes": SPOOL_MAX_BYTES,
        }
        description = (
            f"Event spool exceeded {SPOOL_MAX_BYTES // (1024 * 1024)}MB cap; "
            f"dropped {len(dropped)} oldest segment(s) before digestion"
        )

        # Inline marker append (the caller holds self._lock and just
        # appended to the active segment).
        if self._current is not None:
            try:
                marker = json.dumps(
                    {
                        "event": "spool.overrun",
                        "level": "warning",
                        "timestamp": int(now * 1000),
                        "data": {**overrun_data, "description": description},
                    },
                    separators=(",", ":"),
                )
                with open(self._current, "a", encoding="utf-8") as f:
                    f.write(marker + "\n")
            except Exception:
                pass

        # Local import: spool is imported by the logger module at the
        # bottom of the observability package's dependency chain.
        from . import EventLevel, SystemEvents, observe

        observe(
            event_type=SystemEvents.SPOOL_OVERRUN,
            level=EventLevel.WARNING,
            data=overrun_data,
            description=description,
        )

    # ------------------------------------------------------------------
    # Read side (tuning loop, single consumer)
    # ------------------------------------------------------------------

    def read_for_digest(self) -> Tuple[List[Path], "SpoolCheckpointToken"]:
        """Rotate the active segment and return the undigested segments.

        Everything returned is a closed segment strictly after the current
        checkpoint. Call ``commit`` with the returned token once digested.
        """
        with self._lock:
            # Force rotation so the active segment becomes digestible: the
            # next write MUST open a fresh segment, never resume one that
            # is about to be checkpointed (or deleted) behind it.
            self._current = None
            self._pending_new_segment = True
            checkpoint = self._read_checkpoint()
            segments = [
                segment
                for segment in self._list_segments()
                if checkpoint is None or segment.name > checkpoint
            ]
            return segments, SpoolCheckpointToken([segment.name for segment in segments])

    def iter_events(self, segments: List[Path]) -> Iterator[Dict[str, Any]]:
        """Stream parsed events from segment files; skips corrupt lines."""
        for segment in segments:
            try:
                with open(segment, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except Exception:
                            continue
                        if isinstance(event, dict):
                            yield event
            except OSError:
                continue

    def commit(self, token: "SpoolCheckpointToken", delete: bool) -> None:
        """Advance the checkpoint past the digested segments.

        With ``delete=True`` the digested segments are removed (the spool
        is an internal buffer); with ``delete=False`` they are kept (the
        yaml declared a file transport, so the files are the dev's).
        """
        if not token.segment_names:
            return
        with self._lock:
            self._write_checkpoint(token.segment_names[-1])
            if delete:
                for name in token.segment_names:
                    try:
                        (self.base_dir / name).unlink()
                    except OSError:
                        continue

    def _checkpoint_path(self) -> Path:
        return self.base_dir / CHECKPOINT_FILE

    def _read_checkpoint(self) -> Optional[str]:
        try:
            payload = json.loads(self._checkpoint_path().read_text(encoding="utf-8"))
        except Exception:
            return None
        value = payload.get("digested_through") if isinstance(payload, dict) else None
        return value if isinstance(value, str) and value else None

    def _write_checkpoint(self, segment_name: str) -> None:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = self._checkpoint_path().with_suffix(".tmp")
            tmp_path.write_text(json.dumps({"digested_through": segment_name}), encoding="utf-8")
            os.replace(tmp_path, self._checkpoint_path())
        except Exception:
            pass

    def total_bytes(self) -> int:
        """Total size of all segments (diagnostics and tests)."""
        with self._lock:
            total = 0
            for segment in self._list_segments():
                try:
                    total += segment.stat().st_size
                except OSError:
                    continue
            return total


class SpoolCheckpointToken:
    """Names of the segments one ``read_for_digest`` call returned."""

    def __init__(self, segment_names: List[str]):
        self.segment_names = segment_names


# ---------------------------------------------------------------------------
# Module singleton: the spool must survive the EventLogger replacement at
# server-ready (initialization.enable_conversation_logging recreates the
# logger), so segment/rotation state lives here, keyed by the resolved
# spool directory (which follows utils.user_dirs.FORMATION_ID).
# ---------------------------------------------------------------------------

_spool: Optional[EventSpool] = None
_spool_lock = threading.Lock()


def _spool_dir() -> str:
    return str(Path(get_observability_dir()) / "spool")


def get_event_spool() -> EventSpool:
    """Return the process-wide spool for the current formation."""
    global _spool
    base_dir = _spool_dir()
    spool = _spool
    if spool is not None and str(spool.base_dir) == base_dir:
        return spool
    with _spool_lock:
        if _spool is None or str(_spool.base_dir) != base_dir:
            _spool = EventSpool(base_dir)
        return _spool


def reset_event_spool() -> None:
    """Drop the singleton (tests only)."""
    global _spool
    with _spool_lock:
        _spool = None
