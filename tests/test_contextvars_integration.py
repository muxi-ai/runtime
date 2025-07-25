"""
Test for ContextVars infrastructure implementation (Phases 1.1-1.3)

This test verifies that the automatic context propagation works correctly:
- Context is automatically set when entering track_request()
- Context is automatically retrieved in emit_event()
- Context is properly reset when exiting track_request()
"""

import asyncio
import pytest

from muxi.observability import (
    RequestContextManager,
    get_current_request_context,
    emit_event,
    ObservabilityManager
)


class TestContextVarsIntegration:
    """Test the ContextVars infrastructure for automatic context propagation."""

    @pytest.fixture
    async def manager(self):
        """Create a request context manager for testing."""
        return RequestContextManager()

    @pytest.fixture
    async def observability_manager(self):
        """Create observability manager for testing."""
        return ObservabilityManager()

    async def test_context_propagation_basic(self, manager):
        """Test that context is automatically set and retrieved."""
        # Initially no context should be available
        assert get_current_request_context() is None

        # Context should be available within track_request
        async with manager.track_request(request_id="test-123") as context:
            # Context should be automatically available
            current_context = get_current_request_context()
            assert current_context is not None
            assert current_context.id == "test-123"
            assert current_context is context

        # Context should be cleared after exiting
        assert get_current_request_context() is None

    async def test_context_propagation_nested_async(self, manager):
        """Test context propagation through nested async calls."""

        async def nested_function():
            """A nested async function that should have access to context."""
            context = get_current_request_context()
            return context.id if context else None

        async def deeper_nested_function():
            """Even deeper nesting should still have context access."""
            return await nested_function()

        # No context initially
        assert await nested_function() is None

                # Context should propagate through all nested calls
        async with manager.track_request(request_id="test-nested"):
            result1 = await nested_function()
            result2 = await deeper_nested_function()

            assert result1 == "test-nested"
            assert result2 == "test-nested"

        # Context should be gone after exiting
        assert await nested_function() is None

    async def test_emit_event_automatic_context(self, observability_manager):
        """Test that emit_event automatically retrieves context."""

        # Mock the singleton pattern for testing
        original_get_instance = ObservabilityManager.get_instance
        ObservabilityManager.get_instance = lambda: observability_manager

        try:
            # Track emitted events
            emitted_events = []

            async def mock_emit_event(
                event_type, level, request_context=None, data=None, description=""
            ):
                emitted_events.append({
                    'event_type': event_type,
                    'request_context_id': request_context.id if request_context else None
                })
                return "mock-event-id"

            # Replace the event logger's emit_event method
            observability_manager.event_logger.emit_event = mock_emit_event

            # Test emit_event outside of context (should be skipped)
            await emit_event("AGENT_MESSAGE_PROCESSING", "INFO")
            assert len(emitted_events) == 0  # Should be skipped - no context

                        # Test emit_event inside context (should automatically get context)
            async with observability_manager.track_request(request_id="test-auto"):
                await emit_event("AGENT_MESSAGE_PROCESSING", "INFO")

                # Should have emitted event with automatic context
                assert len(emitted_events) == 3  # REQUEST_RECEIVED + our event + REQUEST_COMPLETED

                # Find our event (it should be the middle one)
                our_event = emitted_events[1]
                assert our_event['request_context_id'] == "test-auto"

        finally:
            # Restore original singleton method
            ObservabilityManager.get_instance = original_get_instance

    async def test_context_isolation_between_requests(self, manager):
        """Test that different async contexts have isolated request contexts."""

        async def process_request(request_id: str) -> str:
            async with manager.track_request(request_id=request_id):
                # Simulate some async work
                await asyncio.sleep(0.01)

                context = get_current_request_context()
                return context.id if context else None

        # Run multiple concurrent requests
        tasks = [
            process_request("request-1"),
            process_request("request-2"),
            process_request("request-3")
        ]

        results = await asyncio.gather(*tasks)

        # Each request should have received its own context
        assert "request-1" in results
        assert "request-2" in results
        assert "request-3" in results
        assert len(set(results)) == 3  # All different

    async def test_context_exception_cleanup(self, manager):
        """Test that context is properly cleaned up even when exceptions occur."""

        # No context initially
        assert get_current_request_context() is None

        try:
            async with manager.track_request(request_id="test-exception"):
                # Context should be available
                assert get_current_request_context() is not None

                # Raise an exception
                raise ValueError("Test exception")

        except ValueError:
            pass  # Expected exception

        # Context should be cleaned up even after exception
        assert get_current_request_context() is None


if __name__ == "__main__":
    # Simple async test runner for development
    async def run_tests():
        test = TestContextVarsIntegration()
        manager = RequestContextManager()
        observability_manager = ObservabilityManager()

        print("Testing basic context propagation...")
        await test.test_context_propagation_basic(manager)
        print("✓ Basic context propagation works")

        print("Testing nested async context propagation...")
        await test.test_context_propagation_nested_async(manager)
        print("✓ Nested async context propagation works")

        print("Testing context isolation...")
        await test.test_context_isolation_between_requests(manager)
        print("✓ Context isolation works")

        print("Testing exception cleanup...")
        await test.test_context_exception_cleanup(manager)
        print("✓ Exception cleanup works")

        print("\nAll ContextVars tests passed! 🎉")

    asyncio.run(run_tests())
