"""
Test 3F1 with Webhooks: Keep-Alive Mechanisms
Test keep-alive mechanisms for long-running document analysis tasks with webhook support.
"""

import asyncio
from pathlib import Path

import pytest

from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


@pytest.fixture
async def formation():
    """Load formation for testing"""
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    # Setup webhook testing environment
    setup_webhook_test()

    overlord = await formation.start_overlord()
    yield overlord
    await formation.stop_overlord()


async def test_keep_alive_long_task_with_webhooks(overlord):
    """Test keep-alive during long-running document processing with webhook support"""
    print("\n=== Test 3F1 with Webhooks: Keep-Alive Long-Running Tasks ===")

    # Simulate a complex document processing request that should trigger keep-alive
    response = await overlord.chat(
        user_id="test_user_keepalive",
        message="Process this large document and provide a comprehensive analysis including: "
                "1) Executive summary with detailed insights and recommendations, "
                "2) Key findings with statistical analysis and trend identification, "
                "3) Risk assessment with mitigation strategies and contingency plans, "
                "4) Financial impact analysis with projections and scenarios, "
                "5) Implementation roadmap with timelines and resource requirements. "
                "Make this analysis extremely detailed and comprehensive."
    )

    # Use universal webhook checker for complex keep-alive processing
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=["analysis", "summary", "finding", "risk", "assessment", "comprehensive"],
        min_keywords=3,
        min_length=100,
        timeout=90.0,  # Extended timeout for keep-alive testing
        test_name="Keep-Alive Long Task Processing"
    )

    print(f"Keep-Alive Long Task Complete - Async: {is_async}")

    # Test keep-alive mechanism awareness
    keepalive_response = await overlord.chat(
        user_id="test_user_keepalive",
        message="How do keep-alive mechanisms work for long-running tasks? What strategies ensure task completion?"
    )

    keepalive_result, keepalive_is_async = check_response_with_webhook(
        keepalive_response,
        expected_keywords=["keep-alive", "mechanism", "long-running", "task", "strategy", "completion"],
        min_keywords=3,
        min_length=80,
        test_name="Keep-Alive Mechanism Understanding"
    )

    print(f"Keep-Alive Mechanism Understanding Complete - Async: {keepalive_is_async}")


async def test_background_task_monitoring_with_webhooks(overlord):
    """Test background task monitoring capabilities with webhook support"""
    print("\n=== Test 3F1 with Webhooks: Background Task Monitoring ===")

    response = await overlord.chat(
        user_id="test_user_background",
        message="How do you monitor background tasks and ensure they don't get terminated "
                "prematurely? What monitoring strategies work best for async document processing?"
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=["background", "task", "monitor", "async", "processing", "strategy", "document"],
        min_keywords=4,
        min_length=100,
        test_name="Background Task Monitoring"
    )

    print(f"Background Task Monitoring Complete - Async: {is_async}")


async def test_task_lifecycle_management_with_webhooks(overlord):
    """Test task lifecycle management with webhook support"""
    print("\n=== Test 3F1 with Webhooks: Task Lifecycle Management ===")

    response = await overlord.chat(
        user_id="test_user_lifecycle",
        message="What are the key phases in async task lifecycle management? How do you handle "
                "task initialization, execution monitoring, and cleanup?"
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=["lifecycle", "management", "async", "task", "phase", "execution", "monitoring"],
        min_keywords=4,
        min_length=100,
        test_name="Task Lifecycle Management"
    )

    print(f"Task Lifecycle Management Complete - Async: {is_async}")


if __name__ == "__main__":
    # Run async tests
    async def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        formation = Formation()
        await formation.load(str(formation_path))

        # Setup webhook testing environment
        setup_webhook_test()

        overlord = await formation.start_overlord()

        try:
            await test_keep_alive_long_task_with_webhooks(overlord)
            await test_background_task_monitoring_with_webhooks(overlord)
            await test_task_lifecycle_management_with_webhooks(overlord)
            print("\nAll keep-alive mechanism webhook tests passed!")
        finally:
            await formation.stop_overlord()

    asyncio.run(run_test())
