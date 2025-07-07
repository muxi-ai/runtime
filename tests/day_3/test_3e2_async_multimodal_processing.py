"""
Test 3E2: Async Multimodal Processing
Tests the system's handling of asynchronous processing for large multimodal tasks.
"""

import sys

sys.path.insert(0, ".")
import pytest  # noqa: E402
import asyncio  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from tests.day_3.test_utils import (  # noqa: E402
    TestVisibility,
    get_response_with_visibility,
    assert_with_visibility,
    capture_observability_events,
    restore_observability,
)
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    result = await coro

    # Handle async generators
    if hasattr(result, "__aiter__"):

        async def collect():
            chunks = []
            async for chunk in result:
                chunks.append(chunk)
            return "".join(chunks)

        return await collect()

    return result


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
    formation_path = (
        Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    )

    formation = Formation()
    await formation.load(str(formation_path))

    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    overlord = await formation.start_overlord()

    yield overlord

    # Cleanup
    await formation.stop_overlord()


def test_large_multimodal_analysis(overlord):
    """Test async processing for comprehensive multimodal analysis"""
    print("\n=== Test 3E2: Large Multimodal Analysis ===")

    start_time = time.time()

    # Complex request that should trigger async
    response = get_response(
        overlord.chat(
            user_id="test_user_async_large",
            message="""Please create an extremely detailed analysis plan for a multimodal dataset containing:
            1) 500 pages of technical documentation in PDF format
            2) 1000 data visualization charts and graphs
            3) 50 hours of recorded presentations and meetings
            4) 200 screenshots of software interfaces

            For each modality, provide:
            - Preprocessing requirements
            - Analysis methodology
            - Feature extraction techniques
            - Integration strategies with other modalities
            - Expected computational resources
            - Timeline estimates

            Make this analysis plan as comprehensive and detailed as possible.""",
            use_async=True,  # Force async
        )
    )

    duration = time.time() - start_time
    print(f"Response received in {duration:.2f} seconds")
    print(f"Async Response: {response}")

    # Check for async response
    if isinstance(response, dict) and "request_id" in response:
        print(f"✓ Received async response with request ID: {response['request_id']}")
        assert response["status"] == "processing", "Status should be processing"
        assert duration < 5, "Async should return immediately"
    else:
        # Sync response is also acceptable but should be very detailed
        assert len(response) > 1000, "If processed synchronously, should be extremely detailed"


def test_async_video_processing_request(overlord):
    """Test async mode for heavy video processing request"""
    print("\n=== Test 3E2: Async Video Processing ===")

    start_time = time.time()

    response = get_response(
        overlord.chat(
            user_id="test_user_video_async",
            message=(
                "Analyze a 10-hour conference video with multiple speakers, "
                "presentations, and panel discussions. Extract all key insights, create timestamps "
                "for important moments, identify all speakers, and summarize each session. "
                "Make sure to use the video file attached."
            ),
            use_async=True,
        )
    )

    duration = time.time() - start_time

    # Should return quickly with async
    if isinstance(response, dict) and "request_id" in response:
        assert duration < 5, "Async response should be immediate"
        assert "webhook_url" in response or "message" in response
    else:
        # If sync, should still handle the request
        assert len(response) > 200, "Should provide substantial analysis"


def test_async_decision_making(overlord):
    """Test intelligent async decision making"""
    print("\n=== Test 3E2: Async Decision Making ===")

    # First, a simple request (should be sync)
    simple_response = get_response(
        overlord.chat(
            user_id="test_user_decision",
            message="What file formats are commonly used for images?",
            use_async=None,  # Let system decide
        )
    )

    print(f"Simple request response type: {type(simple_response)}")
    assert isinstance(simple_response, str), "Simple request should process synchronously"

    # Then, a complex request (might trigger async)
    complex_response = get_response(
        overlord.chat(
            user_id="test_user_decision",
            message=(
                "Create a comprehensive 50-point checklist for analyzing enterprise-scale "
                "multimodal datasets including compliance, quality assurance, and performance "
                "optimization considerations."
            ),
            use_async=None,  # Let system decide
        )
    )

    print(f"Complex request response type: {type(complex_response)}")
    # Either async or very detailed sync response is acceptable


def test_async_with_webhook(overlord):
    """Test async processing with webhook URL"""
    vis = TestVisibility("Async Processing with Webhook")
    vis.start_test("Testing async mode with webhook URL for large multimodal processing")

    # Capture observability events
    capture_observability_events(vis)

    try:
        webhook_url = "https://webhook.site/test-endpoint"
        vis.webhook_check(webhook_url)

        vis.sending_message(
            message=(
                "Process this large multimodal analysis task: Compare 100 research papers with "
                "their associated datasets and create a comprehensive meta-analysis."
            ),
            user_id="test_user_webhook",
            use_async=True,
            webhook_url=webhook_url,
        )

        response = get_response_with_visibility(
            overlord.chat(
                user_id="test_user_webhook",
                message=(
                    "Process this large multimodal analysis task: Compare 100 research papers with "
                    "their associated datasets and create a comprehensive meta-analysis."
                ),
                use_async=True,
                webhook_url=webhook_url,
            ),
            vis,
            "Sending async request with webhook URL",
        )

        # Check response type
        vis.step("Validating async response structure")

        if isinstance(response, dict) and "request_id" in response:
            assert_with_visibility(
                "webhook_url" in response,
                "Response should include webhook_url",
                vis,
                actual_value=list(response.keys()),
            )

            assert_with_visibility(
                response.get("webhook_url") == webhook_url,
                "Response should use provided webhook URL",
                vis,
                actual_value=response.get("webhook_url"),
            )

            assert_with_visibility(
                "webhook_info" in response,
                "Response should explain webhook delivery",
                vis,
                actual_value=response.get("webhook_info"),
            )

            vis.step(
                "Webhook should be called soon", f"Monitor {webhook_url} for incoming POST request"
            )

            # Give the background task time to execute
            vis.step(
                "Waiting for background task to send webhook",
                "Waiting 5 seconds for webhook delivery",
            )
            # Note: Can't use await here since we're not in an async function
            time.sleep(5.0)

        vis.complete_test("PASSED")

    except Exception:
        vis.complete_test("FAILED")
        raise
    finally:
        restore_observability()


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    async def run_test():
        formation_path = (
            Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        )

        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        try:
            test_large_multimodal_analysis(overlord)
            test_async_video_processing_request(overlord)
            test_async_decision_making(overlord)
            test_async_with_webhook(overlord)
            print("\nAll tests passed!")
        finally:
            await formation.stop_overlord()

    asyncio.run(run_test())
        future = executor.submit(run_test)
        future.result()
