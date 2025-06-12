"""
Test suite for the observability system components.

This module tests the core observability infrastructure including:
- EventLogger for structured event emission
- RequestContextManager for request lifecycle tracking
- ObservabilityManager for system coordination
- Performance characteristics and error handling
- Formation configuration integration
"""

import json
import os
import pytest
import sys
import time
from unittest.mock import patch

# Import the observability system components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src/muxi/runtime'))

from src.muxi.runtime.observability import (  # noqa: E402
    EventLogger, ObservabilityManager, RequestContextManager,
    RequestContext, EventType, EventLevel, StreamProcessor,
    LoggingConfig, StreamConfig
)


class TestEventLogger:
    """Test the EventLogger class functionality"""

    @pytest.fixture
    def mock_config(self):
        """Mock logging configuration for testing"""
        return LoggingConfig(
            enabled=True,
            streams=[
                StreamConfig(
                    transport="stdout",
                    destination="stdout",
                    level="info",
                    format="jsonl",
                    events=["*"]
                )
            ]
        )

    @pytest.fixture
    def event_logger(self, mock_config):
        """Create an EventLogger instance for testing"""
        return EventLogger(config=mock_config)

    def test_event_logger_initialization(self, mock_config):
        """Test EventLogger initializes correctly"""
        logger = EventLogger(config=mock_config)
        assert logger.enabled is True
        assert len(logger.streams) == 1
        assert logger.server_ip is not None

    def test_event_logger_disabled(self):
        """Test EventLogger when disabled"""
        config = LoggingConfig(enabled=False, streams=[])
        logger = EventLogger(config=config)
        assert logger.enabled is False
        assert len(logger.streams) == 0

    @pytest.mark.asyncio
    async def test_emit_event_basic(self, event_logger):
        """Test basic event emission"""
        request_context = RequestContext(
            id="test-request",
            user_id="user123",
            formation_id="formation456",
            started=time.time(),
            status="processing"
        )

        with patch('builtins.print') as mock_print:
            await event_logger.emit_event(
                event_type=EventType.OVERLORD_ROUTING_STARTED,
                level=EventLevel.INFO,
                request_context=request_context,
                data={"test": "data"},
                description="Test event"
            )

            # Verify print was called with JSON-formatted event
            mock_print.assert_called_once()
            printed_data = mock_print.call_args[0][0]
            event_data = json.loads(printed_data)

            assert event_data["event"] == "overlord.routing.started"
            assert event_data["level"] == "info"
            assert event_data["description"] == "Test event"
            assert event_data["data"]["test"] == "data"
            assert event_data["request_id"] == "test-request"

    @pytest.mark.asyncio
    async def test_emit_event_disabled_logger(self):
        """Test that disabled logger doesn't emit events"""
        config = LoggingConfig(enabled=False, streams=[])
        logger = EventLogger(config=config)

        request_context = RequestContext(
            id="test-request",
            user_id="user123",
            formation_id="formation456",
            started=time.time(),
            status="processing"
        )

        with patch('builtins.print') as mock_print:
            await logger.emit_event(
                event_type=EventType.OVERLORD_ROUTING_STARTED,
                level=EventLevel.INFO,
                request_context=request_context,
                data={"test": "data"},
                description="Test event"
            )

            # Verify no output when disabled
            mock_print.assert_not_called()

    def test_event_type_to_string_conversion(self):
        """Test that event types are properly converted to strings"""
        test_cases = [
            (EventType.OVERLORD_ROUTING_STARTED, "overlord.routing.started"),
            (EventType.AGENT_MESSAGE_RECEIVED, "agent.message.received"),
            (EventType.MCP_TOOL_CALL_STARTED, "mcp.tool.call.started"),
        ]

        for event_type, expected_string in test_cases:
            result = EventLogger._event_type_to_string(event_type)
            assert result == expected_string


class TestRequestContextManager:
    """Test the RequestContextManager functionality"""

    @pytest.fixture
    def context_manager(self):
        """Create a RequestContextManager for testing"""
        return RequestContextManager()

    @pytest.mark.asyncio
    async def test_track_request_context_manager(self, context_manager):
        """Test the async context manager for request tracking"""
        async with context_manager.track_request(
            request_id="test-req",
            formation_id="test-formation",
            user_id="test-user"
        ) as context:
            assert context.id == "test-req"
            assert context.formation_id == "test-formation"
            assert context.user_id == "test-user"
            assert context.status == "processing"
            assert context.started is not None

        # Context should be completed after exiting
        assert context.status == "completed"
        assert context.ended is not None

    @pytest.mark.asyncio
    async def test_track_request_exception_handling(self, context_manager):
        """Test that exceptions in request tracking are handled properly"""
        with pytest.raises(ValueError):
            async with context_manager.track_request(
                request_id="test-req",
                formation_id="test-formation",
                user_id="test-user"
            ) as context:
                assert context.status == "processing"
                raise ValueError("Test exception")

        # Context should be marked as failed after exception
        assert context.status == "failed"

    def test_cleanup_completed_contexts(self, context_manager):
        """Test cleanup of old completed contexts"""
        # Manually add some test contexts
        old_time = time.time() - 7200  # 2 hours ago
        recent_time = time.time() - 1800  # 30 minutes ago

        old_context = RequestContext(
            id="old-req",
            user_id="user1",
            formation_id="formation1",
            started=old_time,
            status="completed"
        )
        old_context.ended = old_time + 10

        recent_context = RequestContext(
            id="recent-req",
            user_id="user2",
            formation_id="formation2",
            started=recent_time,
            status="completed"
        )
        recent_context.ended = recent_time + 10

        context_manager.contexts["old-req"] = old_context
        context_manager.contexts["recent-req"] = recent_context

        # Run cleanup
        context_manager.cleanup_completed()

        # Old context should be removed, recent one should remain
        assert "old-req" not in context_manager.contexts
        assert "recent-req" in context_manager.contexts


class TestObservabilityManager:
    """Test the ObservabilityManager integration"""

    @pytest.fixture
    def mock_formation_config(self):
        """Mock formation configuration"""
        return {
            "logging": {
                "enabled": True,
                "streams": [{
                    "transport": "stdout",
                    "destination": "stdout",
                    "level": "info",
                    "format": "jsonl",
                    "events": ["*"]
                }]
            }
        }

    @pytest.fixture
    def observability_manager(self, mock_formation_config):
        """Create an ObservabilityManager for testing"""
        return ObservabilityManager(config=mock_formation_config)

    def test_observability_manager_initialization(self, observability_manager):
        """Test ObservabilityManager initializes correctly"""
        assert observability_manager.event_logger is not None
        assert observability_manager.request_manager is not None

    @pytest.mark.asyncio
    async def test_track_request_integration(self, observability_manager):
        """Test request tracking integration"""
        with patch.object(observability_manager.event_logger, 'emit_event') as mock_emit:
            async with observability_manager.track_request(
                request_id="integration-test",
                formation_id="test-formation",
                user_id="test-user"
            ) as context:
                assert context.id == "integration-test"

            # Should emit request started and completed events
            assert mock_emit.call_count == 2

            # Check first call (request started)
            first_call = mock_emit.call_args_list[0]
            assert first_call[1]['event_type'] == EventType.REQUEST_STARTED

            # Check second call (request completed)
            second_call = mock_emit.call_args_list[1]
            assert second_call[1]['event_type'] == EventType.REQUEST_COMPLETED


class TestStreamProcessor:
    """Test the StreamProcessor functionality"""

    def test_stdout_stream_processor(self):
        """Test stdout stream processor"""
        config = StreamConfig(
            transport="stdout",
            destination="stdout",
            level="info",
            format="jsonl",
            events=["*"]
        )
        processor = StreamProcessor(config)

        assert processor.transport == "stdout"
        assert processor.format == "jsonl"

    def test_file_stream_processor(self):
        """Test file stream processor configuration"""
        config = StreamConfig(
            transport="file",
            destination="/tmp/test.log",
            level="debug",
            format="jsonl",
            events=["agent.*", "mcp.*"]
        )
        processor = StreamProcessor(config)

        assert processor.transport == "file"
        assert processor.destination == "/tmp/test.log"
        assert processor.events == ["agent.*", "mcp.*"]

    def test_should_log_wildcard(self):
        """Test event filtering with wildcard"""
        config = StreamConfig(
            transport="stdout",
            destination="stdout",
            level="info",
            format="jsonl",
            events=["*"]
        )
        processor = StreamProcessor(config)

        assert processor.should_log("overlord.routing.started", "info") is True
        assert processor.should_log("agent.message.received", "debug") is True

    def test_should_log_pattern_matching(self):
        """Test event filtering with pattern matching"""
        config = StreamConfig(
            transport="stdout",
            destination="stdout",
            level="info",
            format="jsonl",
            events=["agent.*", "mcp.tool.*"]
        )
        processor = StreamProcessor(config)

        assert processor.should_log("agent.message.received", "info") is True
        assert processor.should_log("mcp.tool.call.started", "info") is True
        assert processor.should_log("overlord.routing.started", "info") is False

    @pytest.mark.asyncio
    async def test_emit_to_stdout(self):
        """Test emitting events to stdout"""
        config = StreamConfig(
            transport="stdout",
            destination="stdout",
            level="info",
            format="jsonl",
            events=["*"]
        )
        processor = StreamProcessor(config)

        test_event = {
            "id": "test-event",
            "timestamp": time.time() * 1000,
            "event": "test.event",
            "level": "info"
        }

        with patch('builtins.print') as mock_print:
            await processor.emit(test_event)
            mock_print.assert_called_once_with(json.dumps(test_event))


class TestFormationIntegration:
    """Test formation.yaml configuration parsing and integration"""

    def test_parse_logging_configuration(self):
        """Test parsing logging configuration from formation data"""
        formation_data = {
            "logging": {
                "enabled": True,
                "streams": [
                    {
                        "transport": "stdout",
                        "destination": "stdout",
                        "level": "info",
                        "format": "jsonl",
                        "events": ["*"]
                    },
                    {
                        "transport": "file",
                        "destination": "/tmp/observability.log",
                        "level": "debug",
                        "format": "jsonl",
                        "events": ["agent.*", "mcp.*"]
                    }
                ]
            }
        }

        config = LoggingConfig.from_dict(formation_data.get("logging", {}))

        assert config.enabled is True
        assert len(config.streams) == 2
        assert config.streams[0].transport == "stdout"
        assert config.streams[1].transport == "file"
        assert config.streams[1].destination == "/tmp/observability.log"

    def test_parse_minimal_logging_configuration(self):
        """Test parsing minimal logging configuration"""
        formation_data = {
            "logging": {
                "enabled": True
            }
        }

        config = LoggingConfig.from_dict(formation_data.get("logging", {}))

        assert config.enabled is True
        assert len(config.streams) == 1  # Should have default stdout stream


class TestPerformance:
    """Test performance characteristics of the observability system"""

    @pytest.mark.asyncio
    async def test_event_emission_performance(self):
        """Test that event emission has minimal overhead (<10ms)"""
        config = LoggingConfig(
            enabled=True,
            streams=[StreamConfig(
                transport="stdout",
                destination="stdout",
                level="info",
                format="jsonl",
                events=["*"]
            )]
        )
        logger = EventLogger(config=config)

        request_context = RequestContext(
            id="perf-test",
            user_id="user123",
            formation_id="formation456",
            started=time.time(),
            status="processing"
        )

        start_time = time.time()

        with patch('builtins.print'):  # Suppress actual output
            for _ in range(100):  # Emit 100 events
                await logger.emit_event(
                    event_type=EventType.AGENT_MESSAGE_RECEIVED,
                    level=EventLevel.INFO,
                    request_context=request_context,
                    data={"test": "performance"},
                    description="Performance test event"
                )

        total_time = time.time() - start_time
        avg_time_per_event = total_time / 100

        # Should be well under 10ms per event
        assert avg_time_per_event < 0.01, f"Average time per event: {avg_time_per_event:.4f}s"

    @pytest.mark.asyncio
    async def test_disabled_logger_performance(self):
        """Test that disabled logger has virtually no overhead"""
        config = LoggingConfig(enabled=False, streams=[])
        logger = EventLogger(config=config)

        request_context = RequestContext(
            id="perf-test-disabled",
            user_id="user123",
            formation_id="formation456",
            started=time.time(),
            status="processing"
        )

        start_time = time.time()

        for _ in range(1000):  # Emit 1000 events with disabled logger
            await logger.emit_event(
                event_type=EventType.AGENT_MESSAGE_RECEIVED,
                level=EventLevel.INFO,
                request_context=request_context,
                data={"test": "performance"},
                description="Performance test event"
            )

        total_time = time.time() - start_time
        avg_time_per_event = total_time / 1000

        # Should be extremely fast when disabled
        assert avg_time_per_event < 0.001, f"Average time per event: {avg_time_per_event:.6f}s"


class TestErrorHandling:
    """Test error handling and robustness"""

    @pytest.mark.asyncio
    async def test_emit_event_with_invalid_data(self):
        """Test that invalid data doesn't crash the system"""
        config = LoggingConfig(
            enabled=True,
            streams=[StreamConfig(
                transport="stdout",
                destination="stdout",
                level="info",
                format="jsonl",
                events=["*"]
            )]
        )
        logger = EventLogger(config=config)

        request_context = RequestContext(
            id="error-test",
            user_id="user123",
            formation_id="formation456",
            started=time.time(),
            status="processing"
        )

        # Test with non-serializable data
        with patch('builtins.print') as mock_print:
            # This should not raise an exception
            await logger.emit_event(
                event_type=EventType.AGENT_MESSAGE_RECEIVED,
                level=EventLevel.INFO,
                request_context=request_context,
                data={"function": lambda x: x},  # Non-serializable
                description="Error test event"
            )

            # Should still emit something (even if data is modified)
            mock_print.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_processor_error_handling(self):
        """Test that stream processor errors don't crash the system"""
        config = StreamConfig(
            transport="file",
            destination="/nonexistent/path/test.log",  # Invalid path
            level="info",
            format="jsonl",
            events=["*"]
        )
        processor = StreamProcessor(config)

        test_event = {
            "id": "error-test",
            "timestamp": time.time() * 1000,
            "event": "test.event",
            "level": "info"
        }

        # This should not raise an exception
        await processor.emit(test_event)


class TestEventFiltering:
    """Test event filtering functionality"""

    def test_level_based_filtering(self):
        """Test filtering events based on level"""
        config = StreamConfig(
            transport="stdout",
            destination="stdout",
            level="warning",  # Only warning and above
            format="jsonl",
            events=None  # No event-based filtering
        )
        processor = StreamProcessor(config)

        assert processor.should_log("any.event", "error") is True
        assert processor.should_log("any.event", "warning") is True
        assert processor.should_log("any.event", "info") is False
        assert processor.should_log("any.event", "debug") is False

    def test_event_pattern_filtering(self):
        """Test filtering events based on patterns"""
        config = StreamConfig(
            transport="stdout",
            destination="stdout",
            level="debug",
            format="jsonl",
            events=["overlord.*", "agent.message.*"]
        )
        processor = StreamProcessor(config)

        assert processor.should_log("overlord.routing.started", "info") is True
        assert processor.should_log("agent.message.received", "info") is True
        assert processor.should_log("agent.response.ready", "info") is False
        assert processor.should_log("mcp.tool.call.started", "info") is False


class TestMemoryManagement:
    """Test memory management and cleanup"""

    @pytest.mark.asyncio
    async def test_context_cleanup_prevents_memory_leak(self):
        """Test that context cleanup prevents memory leaks"""
        manager = RequestContextManager()

        # Create many contexts
        context_ids = []
        for i in range(1000):
            async with manager.track_request(
                request_id=f"test-{i}",
                formation_id="test-formation",
                user_id="test-user"
            ):
                context_ids.append(f"test-{i}")

        # All contexts should be completed and cleaned up
        initial_count = len(manager.contexts)

        # Trigger cleanup
        manager.cleanup_completed()

        final_count = len(manager.contexts)

        # Should have cleaned up completed contexts
        assert final_count < initial_count

    def test_context_memory_usage(self):
        """Test that RequestContext objects have reasonable memory usage"""
        context = RequestContext(
            id="memory-test",
            user_id="user123",
            formation_id="formation456",
            started=time.time(),
            status="processing"
        )

        # Basic memory usage check - context should be lightweight
        import sys
        context_size = sys.getsizeof(context)

        # Should be reasonably small (less than 1KB)
        assert context_size < 1024, f"RequestContext size: {context_size} bytes"


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
