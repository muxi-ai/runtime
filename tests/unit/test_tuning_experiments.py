"""Unit tests for the tuner's experiment memories (Phase 2).

Pins the sidecar store contract: content-hash dedupe across every
status (dismissed ideas are never re-proposed), the pending -> active ->
retired lifecycle, deterministic watch-window evaluation, and atomic
persistence that survives corrupt/missing files.
"""

from __future__ import annotations

import json
import time

from muxi.runtime.services.tuning.experiments import (
    DEFAULT_WATCH_WINDOW_HOURS,
    STATUS_ACTIVE,
    STATUS_DISMISSED,
    STATUS_PENDING,
    STATUS_RETIRED,
    ExperimentStore,
    learning_hash,
)


def make_store(tmp_path):
    return ExperimentStore(str(tmp_path / "tuner"))


class TestLearningHash:
    def test_whitespace_and_case_insensitive(self):
        assert learning_hash("Route FAQ  requests\nto sonnet.") == learning_hash(
            "route faq requests to sonnet."
        )

    def test_distinct_content_distinct_hash(self):
        assert learning_hash("a") != learning_hash("b")


class TestPersistence:
    def test_roundtrip(self, tmp_path):
        store = make_store(tmp_path)
        store.propose("Back off jira 14:00-16:00.", "timeouts clustered", None, None, STATUS_ACTIVE)
        store.save()

        reloaded = make_store(tmp_path)
        assert len(reloaded.records) == 1
        assert reloaded.records[0]["learning"] == "Back off jira 14:00-16:00."
        assert reloaded.records[0]["status"] == STATUS_ACTIVE

    def test_missing_file_means_empty(self, tmp_path):
        assert make_store(tmp_path).records == []

    def test_corrupt_file_means_empty(self, tmp_path):
        base = tmp_path / "tuner"
        base.mkdir()
        (base / "experiments.json").write_text("{not json")
        assert make_store(tmp_path).records == []

    def test_non_dict_records_are_dropped(self, tmp_path):
        base = tmp_path / "tuner"
        base.mkdir()
        (base / "experiments.json").write_text(
            json.dumps({"version": 1, "experiments": ["junk", {"content_hash": "x"}]})
        )
        assert make_store(tmp_path).records == [{"content_hash": "x"}]


class TestLifecycle:
    def test_propose_dedupes_across_statuses(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("Route FAQ to sonnet.", "e", None, None, STATUS_PENDING)
        assert record is not None
        store.set_status(record, STATUS_DISMISSED)
        # A dismissed idea is never re-proposed, even normalized differently.
        assert store.propose("route faq  to sonnet.", "e2", None, None, STATUS_ACTIVE) is None
        assert len(store.records) == 1

    def test_active_proposal_opens_watch_window(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("L", "e", "error_rate", 0.4, STATUS_ACTIVE)
        assert record["watch"]["opened_at"] is not None
        assert record["watch"]["window_hours"] == DEFAULT_WATCH_WINDOW_HOURS
        assert record["baseline"] == 0.4

    def test_pending_proposal_holds_watch_until_activated(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("L", "e", "error_rate", 0.4, STATUS_PENDING)
        assert record["watch"]["opened_at"] is None

        activated = store.activate_pending()
        assert [r["content_hash"] for r in activated] == [record["content_hash"]]
        assert record["status"] == STATUS_ACTIVE
        assert record["watch"]["opened_at"] is not None

    def test_dismiss_pending_marks_all_pending(self, tmp_path):
        store = make_store(tmp_path)
        store.propose("L1", "e", None, None, STATUS_PENDING)
        store.propose("L2", "e", None, None, STATUS_PENDING)
        store.propose("L3", "e", None, None, STATUS_ACTIVE)

        dismissed = store.dismiss_pending()
        assert len(dismissed) == 2
        assert len(store.by_status(STATUS_DISMISSED)) == 2
        assert len(store.by_status(STATUS_ACTIVE)) == 1


class TestWatchWindows:
    def _expired(self, record):
        record["watch"]["opened_at"] = time.time() - 8 * 24 * 3600  # past the 168h default

    def test_unmoved_metric_retires_the_learning(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("L", "e", "problem:mcp.tool.failed", 0.4, STATUS_ACTIVE)
        self._expired(record)

        retired = store.evaluate_watch_windows({"problem:mcp.tool.failed": 0.39})
        assert retired == [record]
        assert record["status"] == STATUS_RETIRED
        assert record["outcome"]["moved"] is False

    def test_moved_metric_keeps_the_learning(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("L", "e", "problem:mcp.tool.failed", 0.4, STATUS_ACTIVE)
        self._expired(record)

        retired = store.evaluate_watch_windows({"problem:mcp.tool.failed": 0.1})
        assert retired == []
        assert record["status"] == STATUS_ACTIVE
        assert record["outcome"]["moved"] is True
        assert record["watch"]["closed_at"] is not None

    def test_absent_metric_counts_as_moved_to_zero(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("L", "e", "problem:mcp.tool.failed", 0.4, STATUS_ACTIVE)
        self._expired(record)

        assert store.evaluate_watch_windows({}) == []
        assert record["status"] == STATUS_ACTIVE
        assert record["outcome"]["moved"] is True

    def test_open_window_is_left_alone(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("L", "e", "error_rate", 0.4, STATUS_ACTIVE)
        assert store.evaluate_watch_windows({"error_rate": 0.4}) == []
        assert record["status"] == STATUS_ACTIVE
        assert "outcome" not in record

    def test_closed_watch_is_never_rescored(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("L", "e", "problem:mcp.tool.failed", 0.4, STATUS_ACTIVE)
        self._expired(record)
        store.evaluate_watch_windows({"problem:mcp.tool.failed": 0.1})
        assert record["outcome"]["moved"] is True

        # The metric regresses after the watch proved the learning.
        retired = store.evaluate_watch_windows({"problem:mcp.tool.failed": 0.9})
        assert retired == []
        assert record["status"] == STATUS_ACTIVE
        assert record["outcome"]["moved"] is True

    def test_observational_learning_never_auto_retires(self, tmp_path):
        store = make_store(tmp_path)
        record = store.propose("L", "e", None, None, STATUS_ACTIVE)
        self._expired(record)

        assert store.evaluate_watch_windows({"error_rate": 1.0}) == []
        assert record["status"] == STATUS_ACTIVE
        assert record["watch"]["closed_at"] is not None
