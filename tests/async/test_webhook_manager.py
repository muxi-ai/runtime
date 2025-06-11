"""
Comprehensive tests for WebhookManager component.

Tests cover webhook delivery, retry logic with exponential backoff,
error handling, timeout scenarios, and payload formatting.
"""

import asyncio
import json
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock
from aiohttp import ClientError, ClientTimeout, ServerTimeoutError
from aiohttp.web_response import Response

from muxi.runtime.overlord.async_patterns.webhook_manager import (
    WebhookManager,
    WebhookPayload
)


class TestWebhookManager:
    """Test suite for WebhookManager functionality."""

    @pytest.fixture
    def webhook_manager(self):
        """Create a WebhookManager instance for testing."""
        return WebhookManager(default_retries=3, default_timeout=5)

    @pytest.fixture
    def sample_payload(self):
        """Create a sample WebhookPayload for testing."""
        return WebhookPayload(
            request_id="req_test_123",
            status="completed",
            result="Analysis complete with 42 insights",
            processing_mode="async",
            processing_time=125.5,
            timestamp=time.time(),
            user_id="user_456"
        )

    @pytest.mark.asyncio
    async def test_webhook_payload_serialization(self, sample_payload):
        """Test that WebhookPayload serializes correctly to dict."""
        payload_dict = {
            "request_id": sample_payload.request_id,
            "status": sample_payload.status,
            "result": sample_payload.result,
            "processing_mode": sample_payload.processing_mode,
            "processing_time": sample_payload.processing_time,
            "timestamp": sample_payload.timestamp,
            "user_id": sample_payload.user_id
        }

        assert payload_dict["request_id"] == "req_test_123"
        assert payload_dict["status"] == "completed"
        assert payload_dict["result"] == "Analysis complete with 42 insights"
        assert payload_dict["processing_mode"] == "async"
        assert payload_dict["processing_time"] == 125.5
        assert payload_dict["user_id"] == "user_456"

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_deliver_webhook_success(self, mock_post, webhook_manager, sample_payload):
        """Test successful webhook delivery."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        # Deliver webhook
        webhook_url = "https://example.com/webhook"
        success = await webhook_manager.deliver_webhook(webhook_url, sample_payload)

        assert success is True

        # Verify the POST was called correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        assert call_args[0][0] == webhook_url  # URL
        assert 'json' in call_args[1]  # JSON payload
        assert 'timeout' in call_args[1]  # Timeout configured

        # Verify payload content
        sent_payload = call_args[1]['json']
        assert sent_payload['request_id'] == "req_test_123"
        assert sent_payload['status'] == "completed"
        assert sent_payload['result'] == "Analysis complete with 42 insights"

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_deliver_webhook_failure_with_retries(self, mock_post, webhook_manager, sample_payload):
        """Test webhook delivery failure with retry logic."""
        # Mock failing responses
        mock_response = Mock()
        mock_response.status = 500  # Server error
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        webhook_url = "https://example.com/webhook"

        # Measure time to verify exponential backoff
        start_time = time.time()
        success = await webhook_manager.deliver_webhook(webhook_url, sample_payload)
        end_time = time.time()

        assert success is False

        # Should have retried 3 times (default)
        assert mock_post.call_count == 3

        # Should have taken some time due to exponential backoff
        # With backoffs of 1s, 2s (total ~3s minimum)
        assert end_time - start_time >= 3.0

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_deliver_webhook_success_after_retries(self, mock_post, webhook_manager, sample_payload):
        """Test webhook delivery succeeding after initial failures."""
        # Mock responses: fail, fail, succeed
        responses = []

        # First two responses fail
        for _ in range(2):
            fail_response = Mock()
            fail_response.status = 503  # Service unavailable
            fail_response.__aenter__ = AsyncMock(return_value=fail_response)
            fail_response.__aexit__ = AsyncMock(return_value=None)
            responses.append(fail_response)

        # Third response succeeds
        success_response = Mock()
        success_response.status = 200
        success_response.__aenter__ = AsyncMock(return_value=success_response)
        success_response.__aexit__ = AsyncMock(return_value=None)
        responses.append(success_response)

        mock_post.side_effect = responses

        webhook_url = "https://example.com/webhook"
        success = await webhook_manager.deliver_webhook(webhook_url, sample_payload)

        assert success is True
        assert mock_post.call_count == 3  # Tried 3 times total

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_deliver_webhook_network_error(self, mock_post, webhook_manager, sample_payload):
        """Test webhook delivery with network errors."""
        # Mock network error
        mock_post.side_effect = ClientError("Connection failed")

        webhook_url = "https://example.com/webhook"
        success = await webhook_manager.deliver_webhook(webhook_url, sample_payload)

        assert success is False
        assert mock_post.call_count == 3  # Should retry on network errors

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_deliver_webhook_timeout_error(self, mock_post, webhook_manager, sample_payload):
        """Test webhook delivery with timeout errors."""
        # Mock timeout error
        mock_post.side_effect = ServerTimeoutError("Request timed out")

        webhook_url = "https://example.com/webhook"
        success = await webhook_manager.deliver_webhook(webhook_url, sample_payload)

        assert success is False
        assert mock_post.call_count == 3  # Should retry on timeouts

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_deliver_completion_success(self, mock_post, webhook_manager):
        """Test the deliver_completion convenience method."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        # Call deliver_completion
        webhook_url = "https://example.com/webhook"
        success = await webhook_manager.deliver_completion(
            webhook_url=webhook_url,
            request_id="req_completion_test",
            result="Task completed successfully",
            processing_time=98.7
        )

        assert success is True

        # Verify correct payload was sent
        call_args = mock_post.call_args
        sent_payload = call_args[1]['json']

        assert sent_payload['request_id'] == "req_completion_test"
        assert sent_payload['status'] == "completed"
        assert sent_payload['result'] == "Task completed successfully"
        assert sent_payload['processing_time'] == 98.7
        assert sent_payload['processing_mode'] == "async"

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_deliver_completion_with_error(self, mock_post, webhook_manager):
        """Test deliver_completion with error status."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        # Call deliver_completion with error
        webhook_url = "https://example.com/webhook"
        success = await webhook_manager.deliver_completion(
            webhook_url=webhook_url,
            request_id="req_error_test",
            error="Processing failed due to invalid input",
            processing_time=15.2
        )

        assert success is True

        # Verify error payload was sent
        call_args = mock_post.call_args
        sent_payload = call_args[1]['json']

        assert sent_payload['request_id'] == "req_error_test"
        assert sent_payload['status'] == "failed"
        assert sent_payload['result'] is None
        assert sent_payload['error'] == "Processing failed due to invalid input"
        assert sent_payload['processing_time'] == 15.2

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_custom_retries_and_timeout(self, mock_post):
        """Test WebhookManager with custom retry and timeout settings."""
        # Create manager with custom settings
        custom_manager = WebhookManager(default_retries=5, default_timeout=15)

        # Mock failing response
        mock_response = Mock()
        mock_response.status = 502  # Bad gateway
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        payload = WebhookPayload(
            request_id="req_custom_test",
            status="completed",
            result="Test result",
            processing_mode="async",
            processing_time=30.0,
            timestamp=time.time(),
            user_id="user_custom"
        )

        success = await custom_manager.deliver_webhook("https://example.com/webhook", payload)

        assert success is False
        assert mock_post.call_count == 5  # Should use custom retry count

        # Verify timeout was configured correctly
        call_args = mock_post.call_args
        timeout = call_args[1]['timeout']
        assert timeout.total == 15  # Should use custom timeout

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_concurrent_webhook_deliveries(self, mock_post, webhook_manager):
        """Test concurrent webhook deliveries don't interfere."""
        # Mock successful responses
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        # Create multiple payloads
        payloads = []
        for i in range(5):
            payload = WebhookPayload(
                request_id=f"req_concurrent_{i}",
                status="completed",
                result=f"Result {i}",
                processing_mode="async",
                processing_time=float(i * 10),
                timestamp=time.time(),
                user_id=f"user_{i}"
            )
            payloads.append(payload)

        # Deliver all webhooks concurrently
        webhook_url = "https://example.com/webhook"
        tasks = []
        for payload in payloads:
            task = asyncio.create_task(
                webhook_manager.deliver_webhook(webhook_url, payload)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(results)
        assert mock_post.call_count == 5

        # Verify all payloads were sent correctly
        all_calls = mock_post.call_args_list
        sent_request_ids = set()

        for call in all_calls:
            payload = call[1]['json']
            sent_request_ids.add(payload['request_id'])

        expected_ids = {f"req_concurrent_{i}" for i in range(5)}
        assert sent_request_ids == expected_ids

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_webhook_payload_timestamp_format(self, mock_post, webhook_manager):
        """Test that webhook payload includes proper timestamp."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        current_time = time.time()
        payload = WebhookPayload(
            request_id="req_timestamp_test",
            status="completed",
            result="Timestamp test",
            processing_mode="async",
            processing_time=45.3,
            timestamp=current_time,
            user_id="user_timestamp"
        )

        await webhook_manager.deliver_webhook("https://example.com/webhook", payload)

        # Verify timestamp in payload
        call_args = mock_post.call_args
        sent_payload = call_args[1]['json']

        assert 'timestamp' in sent_payload
        assert abs(sent_payload['timestamp'] - current_time) < 1.0  # Should be very close

    @pytest.mark.asyncio
    @patch('time.sleep')  # Mock sleep to speed up tests
    @patch('aiohttp.ClientSession.post')
    async def test_exponential_backoff_timing(self, mock_post, mock_sleep, webhook_manager, sample_payload):
        """Test that exponential backoff timing works correctly."""
        # Mock failing responses
        mock_response = Mock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        # Replace asyncio.sleep with our mock
        original_sleep = asyncio.sleep

        async def mock_async_sleep(delay):
            mock_sleep(delay)
            return

        with patch('asyncio.sleep', side_effect=mock_async_sleep):
            await webhook_manager.deliver_webhook("https://example.com/webhook", sample_payload)

        # Verify exponential backoff pattern: 1s, 2s (for 3 retries with 2 sleeps)
        assert mock_sleep.call_count == 2
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]

        assert sleep_calls[0] == 1  # 2^0 = 1 second
        assert sleep_calls[1] == 2  # 2^1 = 2 seconds

    def test_webhook_payload_dataclass_fields(self):
        """Test that WebhookPayload dataclass has all required fields."""
        current_time = time.time()
        payload = WebhookPayload(
            request_id="test_req",
            status="processing",
            result=None,
            processing_mode="sync",
            processing_time=None,
            timestamp=current_time,
            user_id="test_user"
        )

        # Verify all fields are accessible
        assert payload.request_id == "test_req"
        assert payload.status == "processing"
        assert payload.result is None
        assert payload.processing_mode == "sync"
        assert payload.processing_time is None
        assert payload.timestamp == current_time
        assert payload.user_id == "test_user"

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_webhook_manager_with_none_values(self, mock_post, webhook_manager):
        """Test webhook delivery with None values in payload."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        # Create payload with None values
        payload = WebhookPayload(
            request_id="req_none_test",
            status="processing",
            result=None,
            processing_mode="async",
            processing_time=None,
            timestamp=time.time(),
            user_id="user_none"
        )

        success = await webhook_manager.deliver_webhook("https://example.com/webhook", payload)

        assert success is True

        # Verify None values are properly serialized
        call_args = mock_post.call_args
        sent_payload = call_args[1]['json']

        assert sent_payload['result'] is None
        assert sent_payload['processing_time'] is None
        assert sent_payload['status'] == "processing"
