"""
Unit tests for early event filtering in the observability hot path.

observe() previously redacted the full payload and spawned a background
emission thread for every call, even when the logger's level/event
filter would drop the event. These tests pin the contract that filtered
events are dropped before redaction, while emitted events still go
through redaction as before.
"""

import time
from unittest.mock import patch

from muxi.runtime.datatypes.observability import (
    ConversationEvents,
    EventLevel,
    SystemEvents,
)
from muxi.runtime.services import observability
from muxi.runtime.services.observability import EventLogger, observe


class TestShouldEmit:
    """EventLogger.should_emit mirrors emit_event's filtering."""

    def test_conversation_event_below_level_is_filtered(self):
        logger = EventLogger(level=EventLevel.ERROR)
        assert (
            logger.should_emit(ConversationEvents.MEMORY_WORKING_RETRIEVED, EventLevel.DEBUG)
            is False
        )
        assert (
            logger.should_emit(ConversationEvents.MEMORY_WORKING_RETRIEVED, EventLevel.ERROR)
            is True
        )

    def test_system_event_uses_system_level(self):
        logger = EventLogger(level=EventLevel.ERROR, system_level="debug")
        # System events are governed by system_level, not the
        # conversation level, so DEBUG passes here.
        assert logger.should_emit(SystemEvents.CONFIG_FORMATION_LOADED, EventLevel.DEBUG) is True

    def test_events_filter_applies_to_conversation_events(self):
        allowed = ConversationEvents.MEMORY_WORKING_RETRIEVED
        blocked = ConversationEvents.MEMORY_WORKING_LOOKUP
        logger = EventLogger(level=EventLevel.DEBUG, events=[allowed.value])
        assert logger.should_emit(allowed, EventLevel.INFO) is True
        assert logger.should_emit(blocked, EventLevel.INFO) is False


class TestObserveEarlyFiltering:
    """observe() drops filtered events before redaction."""

    def _with_logger(self, logger):
        previous = observability.get_runtime_event_logger()
        observability.set_runtime_event_logger(logger)
        was_enabled = observability.is_enabled()
        observability.enable()
        return previous, was_enabled

    def _restore(self, previous, was_enabled):
        # Restore unconditionally: previous may legitimately be None and
        # must not leave this test's logger installed for later tests
        observability.set_runtime_event_logger(previous)
        if not was_enabled:
            observability.disable()

    def test_filtered_event_skips_redaction(self):
        logger = EventLogger(
            level=EventLevel.ERROR, output="file", output_config={"path": "/dev/null"}
        )
        previous, was_enabled = self._with_logger(logger)
        try:
            with patch("muxi.runtime.services.observability._redact_data_recursive") as mock_redact:
                observe(
                    event_type=ConversationEvents.MEMORY_WORKING_RETRIEVED,
                    level=EventLevel.DEBUG,
                    data={"payload": "value"},
                    description="filtered event",
                )
                assert mock_redact.call_count == 0
        finally:
            self._restore(previous, was_enabled)

    def test_emitted_event_still_redacts(self):
        logger = EventLogger(
            level=EventLevel.DEBUG, output="file", output_config={"path": "/dev/null"}
        )
        previous, was_enabled = self._with_logger(logger)
        try:
            with patch(
                "muxi.runtime.services.observability._redact_data_recursive",
                side_effect=lambda obj: obj,
            ) as mock_redact:
                observe(
                    event_type=ConversationEvents.MEMORY_WORKING_RETRIEVED,
                    level=EventLevel.INFO,
                    data={"payload": "value"},
                    description="emitted event",
                )
                # Redaction runs on the background emission thread: once
                # for data, once for the description.
                deadline = time.time() + 2.0
                while mock_redact.call_count < 2 and time.time() < deadline:
                    time.sleep(0.01)
                assert mock_redact.call_count == 2
        finally:
            self._restore(previous, was_enabled)
