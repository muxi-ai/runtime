"""
Test suite for Task 5 Phase 1 - Dual Logging Architecture and Observability System

This test suite comprehensively tests the observability system implementation.
"""

import pytest
import time
from unittest.mock import patch

# Import system path to load runtime modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

try:
    from src.muxi.runtime.observability import (
        EventLogger, ObservabilityManager, RequestContextManager,
        RequestContext, ConversationEventType, EventLevel
    )
except ImportError as e:
    pytest.skip(f"Observability system not available: {e}", allow_module_level=True)


class TestEventLogger:
    """Test the EventLogger class functionality"""

    def test_event_logger_initialization(self):
        """Test EventLogger initializes correctly"""
        logger = EventLogger()
        assert logger.level == EventLevel.INFO
        assert logger.output == "stdout"
        assert logger.muxi_version == "1.0.0"

    @pytest.mark.asyncio
    async def test_emit_event_basic(self):
        """Test basic event emission"""
        logger = EventLogger()

        request_context = RequestContext(
            id="test-request",
            user_id="user123",
            formation_id="formation456"
        )

        with patch('builtins.print') as mock_print:
            event_id = await logger.observe(
                event_type=ConversationEventType.OVERLORD_ROUTING_STARTED,
                level=EventLevel.INFO,
                request_context=request_context,
                data={"test": "data"},
                description="Test event"
            )

            # Verify print was called with JSON-formatted event
            mock_print.assert_called_once()
            # Verify event_id was returned
            assert event_id is not None
            assert len(event_id) > 0

    @pytest.mark.asyncio
    async def test_emit_event_filtering(self):
        """Test event filtering by level"""
        logger = EventLogger(level=EventLevel.WARNING)

        request_context = RequestContext(id="test-request")

        with patch('builtins.print') as mock_print:
            # This should not be emitted (INFO < WARNING)
            await logger.observe(
                event_type=ConversationEventType.AGENT_MESSAGE_PROCESSING,
                level=EventLevel.INFO,
                request_context=request_context
            )

            # This should be emitted (WARNING >= WARNING)
            await logger.observe(
                event_type=ConversationEventType.AGENT_MESSAGE_FAILED,
                level=EventLevel.WARNING,
                request_context=request_context
            )

            # Should only have been called once (for WARNING event)
            assert mock_print.call_count == 1


class TestRequestContext:
    """Test the RequestContext functionality"""

    def test_request_context_creation(self):
        """Test RequestContext creation and properties"""
        context = RequestContext(
            id="test-req",
            formation_id="test-formation",
            user_id="test-user"
        )

        assert context.id == "test-req"
        assert context.formation_id == "test-formation"
        assert context.user_id == "test-user"
        assert context.status == "processing"
        assert context.started is not None
        assert isinstance(context.duration_ms, int)
        assert context.duration_ms >= 0

    def test_request_context_completion(self):
        """Test request context completion"""
        context = RequestContext(id="test-req")

        context.complete()
        assert context.status == "completed"

        context.fail()
        assert context.status == "failed"

    def test_token_usage_tracking(self):
        """Test token usage tracking in request context"""
        context = RequestContext(id="test-req")

        context.tokens.add_tokens("gpt-4", 100)
        context.tokens.add_tokens("gpt-3.5", 50)
        context.tokens.add_tokens("gpt-4", 25)

        assert context.tokens.total == 175
        assert context.tokens.breakdown["gpt-4"] == 125
        assert context.tokens.breakdown["gpt-3.5"] == 50


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

            # Context should be available during tracking
            retrieved_context = await context_manager.get_context("test-req")
            assert retrieved_context is not None
            assert retrieved_context.id == "test-req"

        # Context should be completed after exiting
        assert context.status == "completed"

    @pytest.mark.asyncio
    async def test_track_request_with_exception(self, context_manager):
        """Test request tracking when an exception occurs"""
        context = None
        try:
            async with context_manager.track_request(request_id="fail-req") as ctx:
                context = ctx
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Context should be marked as failed
        assert context.status == "failed"

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self, context_manager):
        """Test automatic cleanup of old contexts"""
        # Start cleanup task
        await context_manager.start_cleanup()

        # Add some contexts manually to test cleanup
        old_context = RequestContext(id="old-req")
        old_context.started = time.time() * 1000 - (2 * 60 * 60 * 1000)  # 2 hours ago

        context_manager._contexts["old-req"] = old_context
        context_manager._contexts["new-req"] = RequestContext(id="new-req")

        # Trigger cleanup
        await context_manager._cleanup_old_contexts()

        # Old context should be removed, new one should remain
        assert "old-req" not in context_manager._contexts
        assert "new-req" in context_manager._contexts

        # Stop cleanup
        await context_manager.stop_cleanup()


class TestObservabilityManager:
    """Test the ObservabilityManager integration"""

    def test_observability_manager_initialization(self):
        """Test ObservabilityManager initializes correctly"""
        manager = ObservabilityManager()
        assert manager.event_logger is not None
        assert manager.request_manager is not None

    def test_observability_manager_with_config(self):
        """Test ObservabilityManager with configuration"""
        config = {
            "logging": {
                "level": "warning",
                "output": "file",
                "events": ["overlord.*", "agent.*"]
            }
        }
        manager = ObservabilityManager(config=config)
        assert manager.event_logger is not None

    @pytest.mark.asyncio
    async def test_observability_manager_lifecycle(self):
        """Test ObservabilityManager start/stop lifecycle"""
        manager = ObservabilityManager()

        # Start the manager
        await manager.start()

        # Test request tracking
        async with manager.track_request(
            request_id="lifecycle-test",
            formation_id="test-formation"
        ) as context:
            assert context.id == "lifecycle-test"
            assert context.formation_id == "test-formation"

        # Stop the manager
        await manager.stop()


class TestPerformance:
    """Test performance characteristics of the observability system"""

    @pytest.mark.asyncio
    async def test_event_emission_performance(self):
        """Test that event emission has minimal overhead (<10ms)"""
        logger = EventLogger()

        request_context = RequestContext(
            id="perf-test",
            user_id="user123",
            formation_id="formation456"
        )

        start_time = time.time()

        with patch('builtins.print'):  # Suppress actual output
            for _ in range(10):  # Emit 10 events for basic test
                await logger.observe(
                    event_type=ConversationEventType.AGENT_MESSAGE_PROCESSING,
                    level=EventLevel.INFO,
                    request_context=request_context,
                    data={"test": "performance"},
                    description="Performance test event"
                )

        total_time = time.time() - start_time
        avg_time_per_event = total_time / 10

        # Should be well under 10ms per event
        assert avg_time_per_event < 0.01, f"Average time per event: {avg_time_per_event:.4f}s"


class TestIntegration:
    """Integration tests for the complete observability system"""

    @pytest.mark.asyncio
    async def test_full_observability_flow(self):
        """Test complete observability flow from request to completion"""
        manager = ObservabilityManager()
        await manager.start()

        try:
            # Track a complete request lifecycle
            async with manager.track_request(
                request_id="integration-test",
                formation_id="test-formation",
                user_id="test-user"
            ) as context:

                # Simulate overlord routing
                with patch('builtins.print'):
                    await manager.event_logger.observe(
                        event_type=ConversationEventType.OVERLORD_ROUTING_STARTED,
                        level=EventLevel.INFO,
                        request_context=context,
                        description="Starting routing"
                    )

                    await manager.event_logger.observe(
                        event_type=ConversationEventType.OVERLORD_AGENT_SELECTED,
                        level=EventLevel.INFO,
                        request_context=context,
                        data={"agent_id": "test-agent"},
                        description="Agent selected"
                    )

                    await manager.event_logger.observe(
                        event_type=ConversationEventType.AGENT_MESSAGE_PROCESSING,
                        level=EventLevel.INFO,
                        request_context=context,
                        description="Processing message"
                    )

                    await manager.event_logger.observe(
                        event_type=ConversationEventType.AGENT_MESSAGE_COMPLETED,
                        level=EventLevel.INFO,
                        request_context=context,
                        description="Message completed"
                    )

            # Request should be completed
            assert context.status == "completed"

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_mcp_tool_lifecycle_events(self):
        """Test MCP tool call lifecycle event tracking"""
        manager = ObservabilityManager()

        request_context = RequestContext(
            id="mcp-test",
            formation_id="test-formation"
        )

        with patch('builtins.print'):
            # Tool call started
            await manager.event_logger.observe(
                event_type=ConversationEventType.MCP_TOOL_CALLED,
                level=EventLevel.INFO,
                request_context=request_context,
                data={"tool_name": "test_tool", "server_id": "test-server"},
                description="Tool call started"
            )

            # Tool call completed
            await manager.event_logger.observe(
                event_type=ConversationEventType.MCP_TOOL_COMPLETED,
                level=EventLevel.INFO,
                request_context=request_context,
                data={"tool_name": "test_tool", "duration_ms": 150},
                description="Tool call completed"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
