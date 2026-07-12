# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Tuner Experiment Memories
# Description:  Content-hashed learning records with watch-window lifecycle
# Role:         Sidecar state for the tuning loop's tune step
# Usage:        Loaded/saved once per tuning pass by the TuningService
# Author:       Muxi Framework Team
#
# Self-Improving Formation PRD, "The loop" step 2: every learning carries
# its evidence and a watch window; later runs check whether the targeted
# metric moved and retire learnings that didn't. Retirements and
# dismissals are recorded here so ideas are never re-proposed.
#
# Storage is a sidecar JSON file in the formation's observability
# directory (sibling of the event spool) written with the same atomic
# tmp-then-replace idiom: single consumer (the tuning loop, serialized by
# its run lock), survives restarts, works without persistent memory, and
# is never in any user-visible retrieval path. Internal format, not
# configuration, not AFS surface.
# =============================================================================

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...utils.user_dirs import get_observability_dir

EXPERIMENTS_FILE = "experiments.json"

# Learning lifecycle. "pending" learnings ride a PENDING-MUXI.md
# suggestion awaiting human accept; "active" ones are live in MUXI.md
# under an open watch window; terminal states are never re-proposed.
STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"
STATUS_DISMISSED = "dismissed"

# Default observation window before a learning must show metric movement.
DEFAULT_WATCH_WINDOW_HOURS = 168.0

# A watched metric must improve (drop) by at least this fraction of its
# baseline within the window, or the learning is retired. Metrics in the
# snapshot are all "lower is better" rates.
IMPROVEMENT_FRACTION = 0.1

_WHITESPACE = re.compile(r"\s+")


def _default_experiments_dir() -> str:
    """Where the store lives (follows the formation's observability dir)."""
    return str(Path(get_observability_dir()) / "tuner")


def learning_hash(learning: str) -> str:
    """Content hash of a learning, tolerant of whitespace/case drift."""
    normalized = _WHITESPACE.sub(" ", learning.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ExperimentStore:
    """The tuner's experiment memories: one JSON document, atomic writes."""

    def __init__(self, base_dir: Optional[str] = None):
        self._base_dir_override = base_dir
        self.records: List[Dict[str, Any]] = []
        self.load()

    def _path(self) -> Path:
        return Path(self._base_dir_override or _default_experiments_dir()) / EXPERIMENTS_FILE

    # ------------------------------------------------------------------
    # Persistence (spool-checkpoint idiom: tmp write + os.replace)
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Read the store from disk; a missing/corrupt file means empty."""
        try:
            payload = json.loads(self._path().read_text(encoding="utf-8"))
        except Exception:
            self.records = []
            return
        experiments = payload.get("experiments") if isinstance(payload, dict) else None
        self.records = [record for record in experiments or [] if isinstance(record, dict)]

    def save(self) -> None:
        """Atomically persist the store; failures never break the pass."""
        path = self._path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps({"version": 1, "experiments": self.records}, indent=1),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def known_hashes(self) -> set:
        """Hashes in any status -- everything the tuner must not re-propose."""
        return {record.get("content_hash") for record in self.records}

    def by_status(self, status: str) -> List[Dict[str, Any]]:
        return [record for record in self.records if record.get("status") == status]

    def propose(
        self,
        learning: str,
        evidence: str,
        metric_key: Optional[str],
        baseline: Optional[float],
        status: str,
        window_hours: float = DEFAULT_WATCH_WINDOW_HOURS,
    ) -> Optional[Dict[str, Any]]:
        """Record a newly distilled learning; None when already known."""
        content_hash = learning_hash(learning)
        if content_hash in self.known_hashes():
            return None
        now = time.time()
        record = {
            "content_hash": content_hash,
            "status": status,
            "learning": learning,
            "evidence": evidence,
            "metric_key": metric_key,
            "baseline": baseline,
            "watch": {
                "opened_at": now if status == STATUS_ACTIVE else None,
                "window_hours": window_hours,
            },
            "created_at": now,
            "updated_at": now,
        }
        self.records.append(record)
        return record

    def set_status(self, record: Dict[str, Any], status: str) -> None:
        record["status"] = status
        record["updated_at"] = time.time()
        if status == STATUS_ACTIVE and not (record.get("watch") or {}).get("opened_at"):
            record.setdefault("watch", {"window_hours": DEFAULT_WATCH_WINDOW_HOURS})
            record["watch"]["opened_at"] = time.time()

    def activate_pending(self) -> List[Dict[str, Any]]:
        """Pending suggestion accepted: open every pending watch window."""
        activated = []
        for record in self.by_status(STATUS_PENDING):
            self.set_status(record, STATUS_ACTIVE)
            activated.append(record)
        return activated

    def dismiss_pending(self) -> List[Dict[str, Any]]:
        """Pending suggestion dismissed: hashes stay so ideas never return."""
        dismissed = []
        for record in self.by_status(STATUS_PENDING):
            self.set_status(record, STATUS_DISMISSED)
            dismissed.append(record)
        return dismissed

    def evaluate_watch_windows(
        self, metrics: Dict[str, float], now: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Retire active learnings whose expired window shows no movement.

        Deterministic: a learning with a watched metric key must show the
        metric at or below ``baseline * (1 - IMPROVEMENT_FRACTION)`` when
        its window expires. A metric absent from the current snapshot
        counts as moved to zero (the problem stopped appearing), which is
        the movement the learning promised -- the watch simply closes.
        Learnings without a metric key are observational-only and never
        auto-retire. A closed watch is final: a learning that proved
        itself is never re-scored when the metric later regresses.
        """
        now = now if now is not None else time.time()
        retired = []
        for record in self.by_status(STATUS_ACTIVE):
            watch = record.get("watch") or {}
            if watch.get("closed_at"):
                continue
            opened_at = watch.get("opened_at")
            window_hours = watch.get("window_hours") or DEFAULT_WATCH_WINDOW_HOURS
            if not opened_at or now < opened_at + window_hours * 3600.0:
                continue
            metric_key = record.get("metric_key")
            baseline = record.get("baseline")
            if not metric_key or not isinstance(baseline, (int, float)) or baseline <= 0:
                watch["closed_at"] = now
                continue
            current = float(metrics.get(metric_key, 0.0))
            if current <= baseline * (1 - IMPROVEMENT_FRACTION):
                watch["closed_at"] = now
                record["outcome"] = {
                    "metric": metric_key,
                    "baseline": baseline,
                    "final": current,
                    "moved": True,
                }
                record["updated_at"] = now
            else:
                record["outcome"] = {
                    "metric": metric_key,
                    "baseline": baseline,
                    "final": current,
                    "moved": False,
                }
                self.set_status(record, STATUS_RETIRED)
                retired.append(record)
        return retired


__all__ = [
    "DEFAULT_WATCH_WINDOW_HOURS",
    "EXPERIMENTS_FILE",
    "ExperimentStore",
    "IMPROVEMENT_FRACTION",
    "STATUS_ACTIVE",
    "STATUS_DISMISSED",
    "STATUS_PENDING",
    "STATUS_RETIRED",
    "learning_hash",
]
