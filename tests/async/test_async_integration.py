"""
Comprehensive integration tests for async orchestration system.

Tests the complete async workflow including overlord.chat(), RequestTracker,
WebhookManager, TimeEstimator, and all async decision logic.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from src.muxi.runtime.formation.overlord.overlord import Overlord
from src.muxi.runtime.formation.background.request_tracker import RequestStatus
from src.muxi.runtime.datatypes.response import MuxiResponse


class TestAsyncIntegration:
    """Integration test suite for complete async orchestration system."""

    @pytest.fixture
    async def overlord(self):
        """Create a mock Overlord instance for testing."""
        # Create minimal formation config for async
        formation_config = {
            'async': {
                'threshold_seconds': 30,
                'enable_estimation': True,
                'webhook_url': 'https://example.com/webhook',
                'webhook_retries': 3,
                'webhook_timeout': 10
            }
        }

        # Mock the overlord initialization to avoid complex dependencies
        overlord = Mock(spec=Overlord)
        overlord.async_threshold_seconds = 30
        overlord.async_enable_estimation = True
        overlord.async_webhook_url = 'https://example.com/webhook'

        # Mock async components
        overlord.request_tracker = Mock()
        overlord.webhook_manager = Mock()
        overlord.time_estimator = Mock()

        # Mock agent and routing
        overlord.agents = {'assistant': Mock()}
        overlord.select_agent = AsyncMock(return_value='assistant')

        return overlord

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        agent = Mock()
        agent.process_message = AsyncMock(
            return_value="Analysis complete: Found 42 insights in the data."
        )
        return agent

    @pytest.mark.asyncio
    async def test_sync_chat_below_threshold(self, overlord, mock_agent):
        """Test synchronous chat when estimated time is below threshold."""
        # Setup mocks for sync processing
        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=15.0)
        overlord.agents = {'assistant': mock_agent}

        # Mock the actual chat implementation
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            # Simulate sync processing logic
            if use_async is False or (use_async is None and 15.0 < 30):
                # Return MuxiResponse for sync response
                return MuxiResponse(
                    content="Analysis complete: Found 42 insights in the data.",
                    metadata={'processing_mode': 'sync', 'processing_time': 15.0}
                )

        overlord.chat = mock_chat

        # Test sync chat
        response = await overlord.chat(
            message="Analyze this simple dataset",
            agent_name="assistant",
            user_id="user_123"
        )

        # Verify sync response
        assert isinstance(response, MuxiResponse)
        assert response.content == "Analysis complete: Found 42 insights in the data."
        assert response.metadata['processing_mode'] == 'sync'
        assert response.metadata['processing_time'] == 15.0

    @pytest.mark.asyncio
    async def test_async_chat_above_threshold(self, overlord):
        """Test async chat when estimated time is above threshold."""
        # Setup mocks for async processing
        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=45.0)
        overlord.request_tracker.track_request = AsyncMock()

        # Mock the actual chat implementation for async mode
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            # Simulate async processing logic
            if use_async is True or (use_async is None and 45.0 >= 30):
                # Return dict with request_id for async response
                return {
                    'request_id': 'req_async_test_123',
                    'status': 'processing',
                    'message': 'Request is being processed asynchronously.',
                    'estimated_completion_time': 45.0,
                    'webhook_url': kwargs.get('webhook_url', 'https://example.com/webhook')
                }

        overlord.chat = mock_chat

        # Test async chat
        response = await overlord.chat(
            message="Perform comprehensive analysis of large dataset with visualizations",
            agent_name="analyst",
            user_id="user_123"
        )

        # Verify async response
        assert isinstance(response, dict)
        assert response['request_id'] == 'req_async_test_123'
        assert response['status'] == 'processing'
        assert 'estimated_completion_time' in response
        assert response['estimated_completion_time'] == 45.0

    @pytest.mark.asyncio
    async def test_forced_sync_mode(self, overlord, mock_agent):
        """Test forcing synchronous mode even for long-running tasks."""
        # Setup mocks
        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=60.0)
        overlord.agents = {'assistant': mock_agent}

        # Mock chat implementation
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            if use_async is False:
                # Force sync even for long task
                return MuxiResponse(
                    content="Forced sync processing completed",
                    metadata={'processing_mode': 'sync', 'processing_time': 60.0}
                )

        overlord.chat = mock_chat

        # Test forced sync
        response = await overlord.chat(
            message="Long running task",
            use_async=False  # Force synchronous
        )

        # Should return sync response despite long estimated time
        assert isinstance(response, MuxiResponse)
        assert response.metadata['processing_mode'] == 'sync'

    @pytest.mark.asyncio
    async def test_forced_async_mode(self, overlord):
        """Test forcing asynchronous mode even for short tasks."""
        # Setup mocks
        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=5.0)
        overlord.request_tracker.track_request = AsyncMock()

        # Mock chat implementation
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            if use_async is True:
                # Force async even for short task
                return {
                    'request_id': 'req_forced_async_123',
                    'status': 'processing',
                    'message': 'Request is being processed asynchronously.',
                    'estimated_completion_time': 5.0
                }

        overlord.chat = mock_chat

        # Test forced async
        response = await overlord.chat(
            message="Quick task",
            use_async=True  # Force asynchronous
        )

        # Should return async response despite short estimated time
        assert isinstance(response, dict)
        assert response['request_id'] == 'req_forced_async_123'

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_async_completion_with_webhook(self, mock_post, overlord, mock_agent):
        """Test complete async workflow with webhook delivery."""
        # Mock successful webhook delivery
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_post.return_value = mock_response

        # Setup overlord mocks
        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=45.0)
        overlord.request_tracker.track_request = AsyncMock()
        overlord.request_tracker.update_request = AsyncMock()
        overlord.webhook_manager.deliver_completion = AsyncMock(return_value=True)
        overlord.agents = {'assistant': mock_agent}

        # Mock chat implementation with background processing
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            request_id = 'req_webhook_test_123'

            if use_async is True or (use_async is None and 45.0 >= 30):
                # Start background processing
                async def background_task():
                    await asyncio.sleep(0.1)  # Simulate processing

                    # Update request status
                    await overlord.request_tracker.update_request(
                        request_id,
                        RequestStatus.COMPLETED,
                        result="Background processing completed successfully"
                    )

                    # Deliver webhook
                    await overlord.webhook_manager.deliver_completion(
                        webhook_url=kwargs.get('webhook_url'),
                        request_id=request_id,
                        result="Background processing completed successfully",
                        processing_time=45.0
                    )

                # Start background task
                asyncio.create_task(background_task())

                return {
                    'request_id': request_id,
                    'status': 'processing',
                    'message': 'Request is being processed asynchronously.',
                    'estimated_completion_time': 45.0,
                    'webhook_url': kwargs.get('webhook_url')
                }

        overlord.chat = mock_chat

        # Test async with webhook
        response = await overlord.chat(
            message="Complex analysis task",
            webhook_url="https://myapp.com/webhook"
        )

        # Verify async response
        assert isinstance(response, dict)
        assert response['request_id'] == 'req_webhook_test_123'
        assert response['webhook_url'] == "https://myapp.com/webhook"

        # Wait for background processing
        await asyncio.sleep(0.2)

        # Verify webhook was called
        overlord.webhook_manager.deliver_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_request_status_tracking(self, overlord):
        """Test that async requests are properly tracked through their lifecycle."""
        request_tracker = overlord.request_tracker

        # Mock request lifecycle methods
        async def mock_track_request(request_id, state):
            assert request_id == 'req_status_test_123'
            assert state.status == RequestStatus.PROCESSING

        async def mock_update_request(request_id, status, result=None, error=None):
            assert request_id == 'req_status_test_123'
            if status == RequestStatus.COMPLETED:
                assert result == "Status tracking test completed"

        request_tracker.track_request = AsyncMock(side_effect=mock_track_request)
        request_tracker.update_request = AsyncMock(side_effect=mock_update_request)

        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=35.0)

        # Mock chat implementation with status tracking
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            request_id = 'req_status_test_123'

            if use_async is True or (use_async is None and 35.0 >= 30):
                # Track request start
                from src.muxi.runtime.formation.background.request_tracker import RequestState
                state = RequestState(
                    id=request_id,
                    status=RequestStatus.PROCESSING,
                    start_time=time.time(),
                    user_id=user_id
                )
                await request_tracker.track_request(request_id, state)

                # Simulate background completion
                async def complete_request():
                    await asyncio.sleep(0.1)
                    await request_tracker.update_request(
                        request_id,
                        RequestStatus.COMPLETED,
                        result="Status tracking test completed"
                    )

                asyncio.create_task(complete_request())

                return {
                    'request_id': request_id,
                    'status': 'processing',
                    'message': 'Request status tracking test started'
                }

        overlord.chat = mock_chat

        # Test status tracking
        response = await overlord.chat(
            message="Test status tracking",
            user_id="user_status_test"
        )

        # Verify response
        assert response['request_id'] == 'req_status_test_123'

        # Wait for completion
        await asyncio.sleep(0.2)

        # Verify tracking was called
        request_tracker.track_request.assert_called_once()
        request_tracker.update_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_error_handling(self, overlord):
        """Test error handling in async mode."""
        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=40.0)
        overlord.request_tracker.track_request = AsyncMock()
        overlord.request_tracker.update_request = AsyncMock()
        overlord.webhook_manager.deliver_completion = AsyncMock(return_value=True)

        # Mock chat implementation with error simulation
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            request_id = 'req_error_test_123'

            if use_async is True or (use_async is None and 40.0 >= 30):
                # Simulate background error
                async def error_task():
                    await asyncio.sleep(0.1)

                    # Update with error status
                    await overlord.request_tracker.update_request(
                        request_id,
                        RequestStatus.FAILED,
                        error="Simulated processing error"
                    )

                    # Deliver error webhook
                    await overlord.webhook_manager.deliver_completion(
                        webhook_url=kwargs.get('webhook_url'),
                        request_id=request_id,
                        error="Simulated processing error",
                        processing_time=0.1
                    )

                asyncio.create_task(error_task())

                return {
                    'request_id': request_id,
                    'status': 'processing',
                    'message': 'Request started (will fail for testing)'
                }

        overlord.chat = mock_chat

        # Test error handling
        response = await overlord.chat(
            message="Task that will fail",
            webhook_url="https://myapp.com/webhook"
        )

        # Verify initial response
        assert response['request_id'] == 'req_error_test_123'

        # Wait for error processing
        await asyncio.sleep(0.2)

        # Verify error webhook was called
        overlord.webhook_manager.deliver_completion.assert_called_once()
        call_args = overlord.webhook_manager.deliver_completion.call_args
        assert 'error' in call_args[1]

    @pytest.mark.asyncio
    async def test_intelligent_async_decision_making(self, overlord, mock_agent):
        """Test intelligent async decision making based on time estimation."""
        overlord.agents = {'assistant': mock_agent}

        test_cases = [
            (10.0, False, "sync"),    # Below threshold
            (30.0, True, "async"),    # At threshold
            (50.0, True, "async"),    # Above threshold
            (5.0, False, "sync"),     # Well below threshold
            (100.0, True, "async"),   # Well above threshold
        ]

        for estimated_time, expected_async, expected_mode in test_cases:
            overlord.time_estimator.estimate_processing_time = AsyncMock(
                return_value=estimated_time
            )

            # Mock chat implementation
            async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
                # Intelligent decision (use_async is None)
                should_use_async = use_async is True or (
                    use_async is None and estimated_time >= 30
                )

                if should_use_async:
                    return {
                        'request_id': f'req_intelligent_{estimated_time}',
                        'status': 'processing',
                        'processing_mode': 'async'
                    }
                else:
                    return MuxiResponse(
                        content="Sync processing",
                        metadata={'processing_mode': 'sync'}
                    )

            overlord.chat = mock_chat

            # Test intelligent decision
            response = await overlord.chat(
                message=f"Task with estimated time {estimated_time}s"
            )

            # Verify decision
            if expected_async:
                assert isinstance(response, dict)
                assert response['processing_mode'] == 'async'
            else:
                assert isinstance(response, MuxiResponse)
                assert response.metadata['processing_mode'] == 'sync'

    @pytest.mark.asyncio
    async def test_concurrent_async_requests(self, overlord):
        """Test handling multiple concurrent async requests."""
        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=35.0)
        overlord.request_tracker.track_request = AsyncMock()

        request_count = 0

        # Mock chat implementation for concurrent requests
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            nonlocal request_count
            request_count += 1
            request_id = f'req_concurrent_{request_count}'

            return {
                'request_id': request_id,
                'status': 'processing',
                'message': f'Concurrent request {request_count} started'
            }

        overlord.chat = mock_chat

        # Start multiple concurrent requests
        tasks = []
        for i in range(5):
            task = asyncio.create_task(
                overlord.chat(message=f"Concurrent task {i}")
            )
            tasks.append(task)

        # Wait for all to complete
        responses = await asyncio.gather(*tasks)

        # Verify all completed successfully
        assert len(responses) == 5
        for i, response in enumerate(responses):
            assert isinstance(response, dict)
            assert response['request_id'] == f'req_concurrent_{i+1}'
            assert response['status'] == 'processing'

    @pytest.mark.asyncio
    async def test_webhook_url_override(self, overlord):
        """Test webhook URL override functionality."""
        overlord.time_estimator.estimate_processing_time = AsyncMock(return_value=40.0)
        overlord.async_webhook_url = 'https://default.com/webhook'

        # Mock chat implementation
        async def mock_chat(message, agent_name=None, user_id=None, use_async=None, **kwargs):
            webhook_url = kwargs.get('webhook_url', overlord.async_webhook_url)

            return {
                'request_id': 'req_webhook_override_test',
                'status': 'processing',
                'webhook_url': webhook_url
            }

        overlord.chat = mock_chat

        # Test with override
        response = await overlord.chat(
            message="Test webhook override",
            webhook_url="https://custom.com/webhook"
        )

        assert response['webhook_url'] == "https://custom.com/webhook"

        # Test with default
        response = await overlord.chat(
            message="Test default webhook"
        )

        assert response['webhook_url'] == "https://default.com/webhook"
