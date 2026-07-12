"""Unit tests for the event spool (Self-Improving Formation, part 1).

Pins the retention contract: always-on tee through the EventLogger's
background writer, day/size segment rotation, checkpointed single-consumer
reads (read_for_digest rotates first so every returned segment is closed),
delete-after-digest vs keep-when-file-transport-declared, the internal
512MB cap dropping oldest closed segments, and checkpoint persistence
across spool instances (process restarts).
"""

import pytest

from muxi.runtime.datatypes.observability import ConversationEvents, EventLevel
from muxi.runtime.services.observability import EventLogger, spool as spool_module
from muxi.runtime.services.observability.spool import (
    SEGMENT_MAX_BYTES,
    EventSpool,
    get_event_spool,
    reset_event_spool,
)

CONV_EVENT = ConversationEvents.MEMORY_WORKING_RETRIEVED


@pytest.fixture
def spool(tmp_path):
    return EventSpool(str(tmp_path / "spool"))


@pytest.fixture
def isolated_singleton(tmp_path, monkeypatch):
    """Redirect the module singleton into tmp_path for logger-tee tests."""
    monkeypatch.setattr(spool_module, "_spool_dir", lambda: str(tmp_path / "spool"))
    reset_event_spool()
    yield tmp_path / "spool"
    reset_event_spool()


class TestWriteAndRotation:
    def test_lines_append_to_one_daily_segment(self, spool):
        spool.write_lines(['{"event":"a"}', '{"event":"b"}'])
        spool.write_lines(['{"event":"c"}'])
        segments = spool._list_segments()
        assert len(segments) == 1
        assert segments[0].read_text().strip().splitlines() == [
            '{"event":"a"}',
            '{"event":"b"}',
            '{"event":"c"}',
        ]

    def test_size_rotation_starts_a_new_segment(self, spool, monkeypatch):
        monkeypatch.setattr(spool_module, "SEGMENT_MAX_BYTES", 64)
        # The instance reads the module constant at call time via
        # _active_segment; patch the comparison by writing past the limit.
        big_line = '{"event":"x","pad":"' + "p" * 200 + '"}'
        spool.write_lines([big_line])
        spool.write_lines([big_line])
        assert len(spool._list_segments()) == 2

    def test_segment_names_sort_chronologically(self, spool):
        spool.base_dir.mkdir(parents=True, exist_ok=True)
        first = spool._next_segment_path("20260712")
        assert first.name == "events-20260712-0001.jsonl"
        first.write_text("{}\n")
        second = spool._next_segment_path("20260712")
        assert second.name == "events-20260712-0002.jsonl"
        assert sorted([second.name, first.name]) == [first.name, second.name]

    def test_write_never_raises_on_bad_dir(self, tmp_path):
        target = tmp_path / "not-a-dir"
        target.write_text("occupied")
        broken = EventSpool(str(target))
        broken.write_lines(['{"event":"a"}'])  # must not raise


class TestReadDigestCommit:
    def test_read_for_digest_rotates_and_returns_closed_segments(self, spool):
        spool.write_lines(['{"event":"a"}'])
        segments, token = spool.read_for_digest()
        assert [segment.name for segment in segments] == token.segment_names
        assert len(segments) == 1
        # The next write opens a NEW segment: the returned one is closed.
        spool.write_lines(['{"event":"b"}'])
        assert len(spool._list_segments()) == 2

    def test_commit_delete_removes_digested_segments(self, spool):
        spool.write_lines(['{"event":"a"}'])
        segments, token = spool.read_for_digest()
        spool.commit(token, delete=True)
        assert spool._list_segments() == []
        # Checkpoint still advances: nothing is re-read.
        segments, token = spool.read_for_digest()
        assert segments == []

    def test_events_after_delete_commit_stay_visible(self, spool):
        # After delete=True removes every segment, the numbering must
        # continue past the checkpoint -- a reset would produce a name
        # that sorts at/below it, hiding all subsequent events forever.
        spool.write_lines(['{"event":"a"}'])
        segments, token = spool.read_for_digest()
        spool.commit(token, delete=True)

        spool.write_lines(['{"event":"b"}'])
        segments, token = spool.read_for_digest()
        events = list(spool.iter_events(segments))
        assert [event["event"] for event in events] == ["b"]
        spool.commit(token, delete=True)

    def test_commit_keep_preserves_segments_without_rereading(self, spool):
        spool.write_lines(['{"event":"a"}'])
        segments, token = spool.read_for_digest()
        spool.commit(token, delete=False)
        assert len(spool._list_segments()) == 1
        again, _ = spool.read_for_digest()
        assert again == []

    def test_undigested_segments_survive_restart(self, spool):
        spool.write_lines(['{"event":"a"}'])
        segments, token = spool.read_for_digest()
        spool.commit(token, delete=False)
        spool.write_lines(['{"event":"b"}'])

        reopened = EventSpool(str(spool.base_dir))
        segments, _ = reopened.read_for_digest()
        events = list(reopened.iter_events(segments))
        assert [event["event"] for event in events] == ["b"]

    def test_empty_commit_is_a_noop(self, spool):
        segments, token = spool.read_for_digest()
        assert segments == []
        spool.commit(token, delete=True)
        assert spool._read_checkpoint() is None

    def test_iter_events_skips_corrupt_lines(self, spool):
        spool.write_lines(['{"event":"good"}', "not json", '["not a dict"]'])
        segments, _ = spool.read_for_digest()
        events = list(spool.iter_events(segments))
        assert [event["event"] for event in events] == ["good"]


class TestCap:
    def test_cap_drops_oldest_closed_segments(self, spool, monkeypatch):
        monkeypatch.setattr(spool_module, "SPOOL_MAX_BYTES", 150)
        emitted = []
        monkeypatch.setattr(
            spool, "_emit_overrun", lambda dropped, bytes_, total: emitted.append(dropped)
        )
        line = '{"event":"x","pad":"' + "p" * 60 + '"}'
        spool.write_lines([line])
        spool.read_for_digest()  # rotate: segment 1 is now closed
        spool.write_lines([line])
        spool.read_for_digest()  # rotate: segment 2 closed
        spool.write_lines([line])

        names = [segment.name for segment in spool._list_segments()]
        assert len(names) < 3
        assert emitted, "overrun must be reported"

    def test_active_segment_never_dropped(self, spool, monkeypatch):
        monkeypatch.setattr(spool_module, "SPOOL_MAX_BYTES", 10)
        monkeypatch.setattr(spool, "_emit_overrun", lambda *args: None)
        line = '{"event":"x","pad":"' + "p" * 60 + '"}'
        spool.write_lines([line])
        assert len(spool._list_segments()) == 1

    def test_overrun_marker_lands_in_the_spool_itself(self, spool, monkeypatch):
        # The digest must learn about dropped segments even when the
        # logging config filters the spool.overrun event away.
        monkeypatch.setattr(spool_module, "SPOOL_MAX_BYTES", 100)
        line = '{"event":"x","pad":"' + "p" * 60 + '"}'
        spool.write_lines([line])
        spool.read_for_digest()  # close segment 1
        spool.write_lines([line])  # cap pass drops segment 1

        active = spool._current
        assert active is not None
        marker_lines = [
            event for event in spool.iter_events([active]) if event.get("event") == "spool.overrun"
        ]
        assert marker_lines, "no overrun marker was appended to the active segment"
        dropped = marker_lines[0]["data"]["dropped_segments"]
        assert dropped and dropped[0].startswith("events-")


class TestLoggerTee:
    def test_stdout_logger_tees_into_spool(self, isolated_singleton, capsys):
        logger = EventLogger(level=EventLevel.DEBUG, output="stdout")
        logger.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"seq": 0})
        logger.flush()

        segments = list(isolated_singleton.glob("events-*.jsonl"))
        assert len(segments) == 1
        assert '"seq":0' in segments[0].read_text()
        assert '"seq":0' in capsys.readouterr().out

    def test_file_logger_tees_to_both_destinations(self, isolated_singleton, tmp_path):
        log_path = tmp_path / "events.jsonl"
        logger = EventLogger(
            level=EventLevel.DEBUG, output="file", output_config={"path": str(log_path)}
        )
        logger.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"seq": 1})
        logger.flush()

        assert '"seq":1' in log_path.read_text()
        segments = list(isolated_singleton.glob("events-*.jsonl"))
        assert segments and '"seq":1' in segments[0].read_text()

    def test_deep_writer_queue_sheds_spool_writes(self, isolated_singleton, tmp_path):
        log_path = tmp_path / "events.jsonl"
        logger = EventLogger(
            level=EventLevel.DEBUG, output="file", output_config={"path": str(log_path)}
        )
        logger.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"seq": 0})
        logger.flush()
        # Simulate a stalled writer: any depth now exceeds the cap.
        logger._SPOOL_QUEUE_MAX = 0
        logger.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"seq": 1})
        logger.flush()

        assert '"seq":1' in log_path.read_text(), "configured output must never shed"
        segments = list(isolated_singleton.glob("events-*.jsonl"))
        payload = "".join(segment.read_text() for segment in segments)
        assert '"seq":0' in payload
        assert '"seq":1' not in payload, "spool write was not shed at the depth cap"

    def test_spool_survives_logger_replacement(self, isolated_singleton):
        first = EventLogger(level=EventLevel.DEBUG, output="stdout")
        first.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"logger": "first"})
        first.flush()
        # initialization.enable_conversation_logging recreates the logger
        # at server-ready; the spool singleton keeps accumulating.
        second = EventLogger(level=EventLevel.DEBUG, output="stdout")
        second.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"logger": "second"})
        second.flush()

        spool = get_event_spool()
        segments, _ = spool.read_for_digest()
        payload = "".join(segment.read_text() for segment in segments)
        assert '"logger":"first"' in payload
        assert '"logger":"second"' in payload


class TestSingleton:
    def test_singleton_follows_spool_dir(self, isolated_singleton):
        first = get_event_spool()
        assert get_event_spool() is first

    def test_reset_drops_instance(self, isolated_singleton):
        first = get_event_spool()
        reset_event_spool()
        assert get_event_spool() is not first


def test_segment_max_bytes_is_sane():
    assert SEGMENT_MAX_BYTES <= spool_module.SPOOL_MAX_BYTES
