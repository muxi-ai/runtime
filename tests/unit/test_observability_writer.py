"""
Unit tests for the EventLogger background writer.

File and network destinations previously did a blocking open/write/flush
or requests.post per event on the emitting thread. Events are now queued
to a single writer thread that batches per destination. These tests pin:
ordering, delivery via flush(), and NDJSON batching for stream posts.

Since the event spool (Self-Improving Formation), every emitted event is
teed to disk through the writer, so even stdout-only loggers spawn it on
first emit; the tests isolate the spool singleton into tmp_path.
"""

from unittest.mock import MagicMock, patch

import pytest

from muxi.runtime.datatypes.observability import (
    ConversationEvents,
    EventLevel,
    SystemEvents,
)
from muxi.runtime.services.observability import EventLogger, spool as spool_module
from muxi.runtime.services.observability.spool import reset_event_spool

CONV_EVENT = ConversationEvents.MEMORY_WORKING_RETRIEVED
SYS_EVENT = SystemEvents.CONFIG_FORMATION_LOADED


@pytest.fixture(autouse=True)
def isolated_spool(tmp_path, monkeypatch):
    """Keep the always-on spool tee inside tmp_path for every test here."""
    monkeypatch.setattr(spool_module, "_spool_dir", lambda: str(tmp_path / "spool"))
    reset_event_spool()
    yield
    reset_event_spool()


class TestFileWriter:
    def test_file_output_written_in_order(self, tmp_path):
        log_path = tmp_path / "events.jsonl"
        logger = EventLogger(
            level=EventLevel.DEBUG, output="file", output_config={"path": str(log_path)}
        )

        for i in range(5):
            logger.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"seq": i})
        logger.flush()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 5
        assert [f'"seq":{i}' in line for i, line in enumerate(lines)] == [True] * 5

    def test_system_file_destination_written(self, tmp_path):
        log_path = tmp_path / "system.jsonl"
        logger = EventLogger(system_level="debug", system_destination=str(log_path))

        logger.emit_event(SYS_EVENT, level=EventLevel.INFO, data={"marker": "sys"})
        logger.flush()

        content = log_path.read_text()
        assert '"marker":"sys"' in content


class TestStreamWriter:
    def test_stream_posts_ndjson_via_session(self):
        logger = EventLogger(
            level=EventLevel.DEBUG,
            output="stream",
            output_config={"url": "http://collector.test/ingest"},
        )

        mock_requests = MagicMock()
        session = MagicMock()
        mock_requests.Session.return_value = session

        with patch("muxi.runtime.services.observability.logger.requests", mock_requests):
            for i in range(3):
                logger.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"seq": i})
            logger.flush()

        assert session.post.call_count >= 1
        posted_lines = []
        for call in session.post.call_args_list:
            assert call.args[0] == "http://collector.test/ingest"
            body = call.kwargs["data"]
            assert body.endswith("\n")
            assert call.kwargs["headers"]["Content-Type"] == "application/x-ndjson"
            posted_lines.extend(body.strip().splitlines())
        assert len(posted_lines) == 3


class TestWriterLifecycle:
    def test_stdout_output_spawns_writer_for_spool_tee(self, capsys):
        logger = EventLogger(level=EventLevel.DEBUG, output="stdout")

        logger.emit_event(CONV_EVENT, level=EventLevel.INFO, data={"seq": 0})

        # stdout stays synchronous, but the spool tee rides the writer.
        assert logger._write_queue is not None
        assert '"seq":0' in capsys.readouterr().out

    def test_flush_without_writer_is_noop(self):
        logger = EventLogger(level=EventLevel.DEBUG, output="stdout")
        logger.flush()
