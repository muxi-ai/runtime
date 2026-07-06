"""
Unit tests for background redaction in observe().

Redaction previously ran a multi-pattern regex walk over the full
payload on the emitting (request) thread. It now runs on the background
emission thread, with a synchronous container snapshot protecting
against caller mutation. These tests pin: emitted events are still
fully redacted end-to-end, and the snapshot isolates the event from
post-observe() caller mutations.
"""

import time

from muxi.runtime.datatypes.observability import ConversationEvents, EventLevel
from muxi.runtime.services import observability
from muxi.runtime.services.observability import EventLogger, _snapshot_structure, observe

EVENT = ConversationEvents.MEMORY_WORKING_RETRIEVED


def _read_when_ready(path, marker, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            content = path.read_text()
            if marker in content:
                return content
        time.sleep(0.01)
    return path.read_text() if path.exists() else ""


class TestSnapshotStructure:
    def test_snapshot_isolates_container_mutation(self):
        original = {"outer": {"items": [1, 2]}, "kept": "value"}
        snapshot = _snapshot_structure(original)

        original["outer"]["items"].append(3)
        original["new_key"] = "added"

        assert snapshot == {"outer": {"items": [1, 2]}, "kept": "value"}

    def test_snapshot_shares_immutable_leaves(self):
        original = {"text": "leaf string"}
        snapshot = _snapshot_structure(original)
        assert snapshot["text"] is original["text"]

    def test_snapshot_preserves_tuple_type(self):
        snapshot = _snapshot_structure({"pair": ("a", "b")})
        assert isinstance(snapshot["pair"], tuple)


class TestBackgroundRedaction:
    def _with_logger(self, logger):
        previous = observability.get_runtime_event_logger()
        observability.set_runtime_event_logger(logger)
        was_enabled = observability.is_enabled()
        observability.enable()
        return previous, was_enabled

    def _restore(self, previous, was_enabled):
        if previous is not None:
            observability.set_runtime_event_logger(previous)
        if not was_enabled:
            observability.disable()

    def test_emitted_event_is_redacted_end_to_end(self, tmp_path):
        log_path = tmp_path / "events.jsonl"
        logger = EventLogger(
            level=EventLevel.DEBUG, output="file", output_config={"path": str(log_path)}
        )
        previous, was_enabled = self._with_logger(logger)
        fake_key = "sk-" + "z" * 30  # synthetic; matches the sk- pattern
        try:
            observe(
                event_type=EVENT,
                level=EventLevel.INFO,
                data={"secret": f"key {fake_key}", "marker": "e2e-redaction"},
            )
            content = _read_when_ready(log_path, "e2e-redaction")

            assert "e2e-redaction" in content
            assert fake_key not in content
            assert "sk-****" in content
        finally:
            self._restore(previous, was_enabled)

    def test_caller_mutation_after_observe_does_not_leak(self, tmp_path):
        log_path = tmp_path / "events.jsonl"
        logger = EventLogger(
            level=EventLevel.DEBUG, output="file", output_config={"path": str(log_path)}
        )
        previous, was_enabled = self._with_logger(logger)
        try:
            payload = {"items": ["stable"], "marker": "mutation-check"}
            observe(event_type=EVENT, level=EventLevel.INFO, data=payload)
            # Mutate immediately after observe() returns; the snapshot
            # taken on the emitting thread must not see this.
            payload["items"].append("added-after-observe")
            payload["late_key"] = "late"

            content = _read_when_ready(log_path, "mutation-check")

            assert "mutation-check" in content
            assert "late_key" not in content
        finally:
            self._restore(previous, was_enabled)
