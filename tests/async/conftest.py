"""
Pytest configuration for async orchestration tests.

Provides shared fixtures and test configuration for the async test suite.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.muxi.formation.background.request_tracker import (  # noqa: E402
    RequestTracker,
    RequestState,
    RequestStatus
)
from src.muxi.formation.background.webhook_manager import (  # noqa: E402
    WebhookManager
)
from src.muxi.utils.response_converter import create_unified_response  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def request_tracker():
    """Create a RequestTracker instance for testing."""
    return RequestTracker()


@pytest.fixture
def webhook_manager():
    """Create a WebhookManager instance for testing."""
    return WebhookManager(default_retries=3, default_timeout=5)


@pytest.fixture
def sample_request_state():
    """Create a sample RequestState for testing."""
    return RequestState(
        id="test_request_123",
        status=RequestStatus.PROCESSING,
        start_time=1640995200.0,
        user_id="test_user_456",
        agent_name="test_agent",
        message="Test message content",
        webhook_url="https://example.com/webhook"
    )


@pytest.fixture
def sample_webhook_payload():
    """Create a sample unified response payload for testing."""
    return create_unified_response(
        request_id="test_request_123",
        status="completed",
        formation_id="test_formation",
        user_id="test_user_456",
        processing_time=42.5,
        processing_mode="async",
        webhook_url="https://example.com/webhook",
        error=None,
        response=[{
            "type": "text",
            "content": "Test processing completed successfully"
        }]
    )


# Async test utilities
class AsyncTestHelper:
    """Helper class for async test operations."""

    @staticmethod
    async def wait_for_background_tasks(timeout=1.0):
        """Wait for background asyncio tasks to complete."""
        await asyncio.sleep(0.1)

        pending_tasks = [
            task for task in asyncio.all_tasks()
            if not task.done() and task != asyncio.current_task()
        ]

        if pending_tasks:
            await asyncio.wait_for(
                asyncio.gather(*pending_tasks, return_exceptions=True),
                timeout=timeout
            )

    @staticmethod
    def create_mock_agent(response="Mock agent response"):
        """Create a mock agent with configurable response."""
        agent = Mock()
        agent.process_message = AsyncMock(return_value=response)
        agent.agent_id = "mock_agent"
        return agent


@pytest.fixture
def async_test_helper():
    """Provide async test helper utilities."""
    return AsyncTestHelper


# Configure asyncio mode for pytest
pytestmark = pytest.mark.asyncio
