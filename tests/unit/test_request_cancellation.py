"""Unit tests for request cancellation functionality."""

import asyncio
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.background.request_tracker import RequestTracker
from muxi.formation.background.cancellation import (
    RequestCancelledException,
    cancellable,
    check_cancellation,
    check_cancellation_from_context,
)


class TestRequestTracker(unittest.TestCase):
    """Test RequestTracker cancellation methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = RequestTracker()

    def test_initial_state_not_cancelled(self):
        """Test that new requests are not cancelled by default."""
        self.assertFalse(self.tracker.is_cancelled("req_123"))
        self.assertFalse(self.tracker.is_cancelled("req_456"))

    def test_mark_cancelled(self):
        """Test marking a request as cancelled."""
        async def run():
            await self.tracker.mark_cancelled("req_123")
            self.assertTrue(self.tracker.is_cancelled("req_123"))
            self.assertFalse(self.tracker.is_cancelled("req_456"))
        
        asyncio.run(run())

    def test_clear_cancelled(self):
        """Test clearing cancelled status."""
        async def run():
            await self.tracker.mark_cancelled("req_123")
            self.assertTrue(self.tracker.is_cancelled("req_123"))
            
            await self.tracker.clear_cancelled("req_123")
            self.assertFalse(self.tracker.is_cancelled("req_123"))
        
        asyncio.run(run())

    def test_clear_cancelled_idempotent(self):
        """Test that clearing non-cancelled request doesn't error."""
        async def run():
            # Should not raise
            await self.tracker.clear_cancelled("req_never_cancelled")
            self.assertFalse(self.tracker.is_cancelled("req_never_cancelled"))
        
        asyncio.run(run())

    def test_multiple_cancellations(self):
        """Test cancelling multiple requests."""
        async def run():
            await self.tracker.mark_cancelled("req_1")
            await self.tracker.mark_cancelled("req_2")
            await self.tracker.mark_cancelled("req_3")
            
            self.assertTrue(self.tracker.is_cancelled("req_1"))
            self.assertTrue(self.tracker.is_cancelled("req_2"))
            self.assertTrue(self.tracker.is_cancelled("req_3"))
            self.assertFalse(self.tracker.is_cancelled("req_4"))
            
            await self.tracker.clear_cancelled("req_2")
            self.assertTrue(self.tracker.is_cancelled("req_1"))
            self.assertFalse(self.tracker.is_cancelled("req_2"))
            self.assertTrue(self.tracker.is_cancelled("req_3"))
        
        asyncio.run(run())

    def test_is_cancelled_sync(self):
        """Test that is_cancelled is synchronous (non-blocking)."""
        # This should complete instantly without awaiting
        result = self.tracker.is_cancelled("req_123")
        self.assertFalse(result)

    def test_remove_request_clears_cancelled(self):
        """Test that remove_request also clears cancelled status."""
        async def run():
            # Mark as cancelled
            await self.tracker.mark_cancelled("req_123")
            self.assertTrue(self.tracker.is_cancelled("req_123"))
            
            # Remove request (should also clear cancelled)
            await self.tracker.remove_request("req_123")
            self.assertFalse(self.tracker.is_cancelled("req_123"))
        
        asyncio.run(run())


class TestRequestCancelledException(unittest.TestCase):
    """Test RequestCancelledException."""

    def test_exception_message(self):
        """Test exception contains request_id in message."""
        exc = RequestCancelledException("req_abc123")
        self.assertEqual(exc.request_id, "req_abc123")
        self.assertIn("req_abc123", str(exc))
        self.assertIn("cancelled", str(exc).lower())

    def test_exception_inheritance(self):
        """Test exception inherits from Exception."""
        exc = RequestCancelledException("req_123")
        self.assertIsInstance(exc, Exception)


class TestCheckCancellation(unittest.TestCase):
    """Test check_cancellation function."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = RequestTracker()

    def test_raises_when_cancelled(self):
        """Test that check_cancellation raises when request is cancelled."""
        async def run():
            await self.tracker.mark_cancelled("req_123")
            
            with self.assertRaises(RequestCancelledException) as ctx:
                await check_cancellation(self.tracker, "req_123")
            
            self.assertEqual(ctx.exception.request_id, "req_123")
        
        asyncio.run(run())

    def test_no_raise_when_not_cancelled(self):
        """Test that check_cancellation doesn't raise for active requests."""
        async def run():
            # Should not raise
            await check_cancellation(self.tracker, "req_123")
        
        asyncio.run(run())

    def test_clears_cancelled_status_on_raise(self):
        """Test that raising clears the cancelled status."""
        async def run():
            await self.tracker.mark_cancelled("req_123")
            
            with self.assertRaises(RequestCancelledException):
                await check_cancellation(self.tracker, "req_123")
            
            # Should be cleared now
            self.assertFalse(self.tracker.is_cancelled("req_123"))
        
        asyncio.run(run())


class TestCheckCancellationFromContext(unittest.TestCase):
    """Test check_cancellation_from_context function."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = RequestTracker()

    def test_raises_when_cancelled_with_context(self):
        """Test raises when request in context is cancelled."""
        async def run():
            await self.tracker.mark_cancelled("req_ctx_123")
            
            # Mock the context
            mock_ctx = MagicMock()
            mock_ctx.id = "req_ctx_123"
            
            with patch(
                "muxi.services.observability.context.get_current_request_context",
                return_value=mock_ctx
            ):
                with self.assertRaises(RequestCancelledException) as ctx:
                    await check_cancellation_from_context(self.tracker)
                
                self.assertEqual(ctx.exception.request_id, "req_ctx_123")
        
        asyncio.run(run())

    def test_no_raise_when_no_context(self):
        """Test doesn't raise when no context is set."""
        async def run():
            await self.tracker.mark_cancelled("req_123")
            
            with patch(
                "muxi.services.observability.context.get_current_request_context",
                return_value=None
            ):
                # Should not raise even though req_123 is cancelled
                await check_cancellation_from_context(self.tracker)
        
        asyncio.run(run())

    def test_no_raise_when_context_id_none(self):
        """Test doesn't raise when context.id is None."""
        async def run():
            mock_ctx = MagicMock()
            mock_ctx.id = None
            
            with patch(
                "muxi.services.observability.context.get_current_request_context",
                return_value=mock_ctx
            ):
                # Should not raise
                await check_cancellation_from_context(self.tracker)
        
        asyncio.run(run())

    def test_clears_cancelled_status_on_raise(self):
        """Test that raising clears the cancelled status."""
        async def run():
            await self.tracker.mark_cancelled("req_ctx_456")
            
            mock_ctx = MagicMock()
            mock_ctx.id = "req_ctx_456"
            
            with patch(
                "muxi.services.observability.context.get_current_request_context",
                return_value=mock_ctx
            ):
                with self.assertRaises(RequestCancelledException):
                    await check_cancellation_from_context(self.tracker)
            
            # Should be cleared now
            self.assertFalse(self.tracker.is_cancelled("req_ctx_456"))
        
        asyncio.run(run())


class TestCancellableDecorator(unittest.TestCase):
    """Test cancellable decorator factory."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = RequestTracker()

    def test_decorator_raises_when_cancelled(self):
        """Test decorated function raises when request is cancelled."""
        async def run():
            await self.tracker.mark_cancelled("req_decorated")
            
            check_cancelled = cancellable(self.tracker)
            
            @check_cancelled
            async def my_function():
                return "success"
            
            mock_ctx = MagicMock()
            mock_ctx.id = "req_decorated"
            
            with patch(
                "muxi.services.observability.context.get_current_request_context",
                return_value=mock_ctx
            ):
                with self.assertRaises(RequestCancelledException):
                    await my_function()
        
        asyncio.run(run())

    def test_decorator_allows_when_not_cancelled(self):
        """Test decorated function executes when not cancelled."""
        async def run():
            check_cancelled = cancellable(self.tracker)
            
            @check_cancelled
            async def my_function():
                return "success"
            
            mock_ctx = MagicMock()
            mock_ctx.id = "req_not_cancelled"
            
            with patch(
                "muxi.services.observability.context.get_current_request_context",
                return_value=mock_ctx
            ):
                result = await my_function()
                self.assertEqual(result, "success")
        
        asyncio.run(run())

    def test_decorator_passes_arguments(self):
        """Test decorated function receives arguments correctly."""
        async def run():
            check_cancelled = cancellable(self.tracker)
            
            @check_cancelled
            async def add(a, b, c=0):
                return a + b + c
            
            with patch(
                "muxi.services.observability.context.get_current_request_context",
                return_value=None
            ):
                result = await add(1, 2, c=3)
                self.assertEqual(result, 6)
        
        asyncio.run(run())

    def test_decorator_clears_cancelled_on_raise(self):
        """Test decorator clears cancelled status when raising."""
        async def run():
            await self.tracker.mark_cancelled("req_clear_test")
            
            check_cancelled = cancellable(self.tracker)
            
            @check_cancelled
            async def my_function():
                return "success"
            
            mock_ctx = MagicMock()
            mock_ctx.id = "req_clear_test"
            
            with patch(
                "muxi.services.observability.context.get_current_request_context",
                return_value=mock_ctx
            ):
                with self.assertRaises(RequestCancelledException):
                    await my_function()
            
            # Should be cleared
            self.assertFalse(self.tracker.is_cancelled("req_clear_test"))
        
        asyncio.run(run())


class TestConcurrency(unittest.TestCase):
    """Test thread safety and concurrent access."""

    def test_concurrent_mark_and_check(self):
        """Test concurrent marking and checking of cancellation."""
        tracker = RequestTracker()
        
        async def run():
            async def mark_requests():
                for i in range(100):
                    await tracker.mark_cancelled(f"req_{i}")
            
            async def check_requests():
                results = []
                for i in range(100):
                    results.append(tracker.is_cancelled(f"req_{i}"))
                return results
            
            # Run both concurrently
            await asyncio.gather(mark_requests(), check_requests())
            
            # After both complete, all should be cancelled
            for i in range(100):
                self.assertTrue(tracker.is_cancelled(f"req_{i}"))
        
        asyncio.run(run())

    def test_concurrent_clear(self):
        """Test concurrent clearing doesn't cause issues."""
        tracker = RequestTracker()
        
        async def run():
            # Mark all first
            for i in range(50):
                await tracker.mark_cancelled(f"req_{i}")
            
            async def clear_requests():
                for i in range(50):
                    await tracker.clear_cancelled(f"req_{i}")
            
            # Clear from multiple coroutines
            await asyncio.gather(
                clear_requests(),
                clear_requests(),
                clear_requests(),
            )
            
            # All should be cleared
            for i in range(50):
                self.assertFalse(tracker.is_cancelled(f"req_{i}"))
        
        asyncio.run(run())


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_empty_request_id(self):
        """Test behavior with empty request_id."""
        tracker = RequestTracker()
        
        async def run():
            # Empty string should work
            await tracker.mark_cancelled("")
            self.assertTrue(tracker.is_cancelled(""))
            await tracker.clear_cancelled("")
            self.assertFalse(tracker.is_cancelled(""))
        
        asyncio.run(run())

    def test_special_characters_in_request_id(self):
        """Test request IDs with special characters."""
        tracker = RequestTracker()
        
        async def run():
            special_ids = [
                "req-with-dashes",
                "req_with_underscores",
                "req.with.dots",
                "req:with:colons",
                "req/with/slashes",
                "req with spaces",
                "req_αβγ_unicode",
            ]
            
            for req_id in special_ids:
                await tracker.mark_cancelled(req_id)
                self.assertTrue(tracker.is_cancelled(req_id), f"Failed for {req_id}")
                await tracker.clear_cancelled(req_id)
                self.assertFalse(tracker.is_cancelled(req_id), f"Failed clear for {req_id}")
        
        asyncio.run(run())

    def test_mark_cancelled_idempotent(self):
        """Test that marking same request multiple times is safe."""
        tracker = RequestTracker()
        
        async def run():
            await tracker.mark_cancelled("req_123")
            await tracker.mark_cancelled("req_123")
            await tracker.mark_cancelled("req_123")
            
            self.assertTrue(tracker.is_cancelled("req_123"))
            
            # Only need to clear once
            await tracker.clear_cancelled("req_123")
            self.assertFalse(tracker.is_cancelled("req_123"))
        
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
