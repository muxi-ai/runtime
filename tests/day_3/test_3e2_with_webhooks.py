"""
Test 3E2 with Webhooks: Async Multimodal Processing
Tests the system's handling of asynchronous processing for large multimodal tasks with webhook support.
"""

import sys

sys.path.insert(0, ".")
import pytest  # noqa: E402
import asyncio  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


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
    # Setup webhook testing environment
    setup_webhook_test()
    
    overlord = await formation.start_overlord()

    yield overlord

    # Cleanup
    await formation.stop_overlord()


def test_large_multimodal_analysis_with_webhooks(overlord):
    """Test async processing for comprehensive multimodal analysis with webhook support"""
    print("\n=== Test 3E2 with Webhooks: Large Multimodal Analysis ===")

    start_time = time.time()

    # Complex request that should trigger async
    response = asyncio.run(
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

            Make this analysis plan as comprehensive and detailed as possible."""
        )
    )

    duration = time.time() - start_time
    print(f"Response received in {duration:.2f} seconds")

    # Use universal webhook checker - this complex request should likely be async
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['analysis', 'plan', 'multimodal', 'preprocessing', 'methodology', 'extraction', 'integration'],
        min_keywords=5,
        min_length=500,
        timeout=60.0,  # Give more time for this complex request
        test_name="Large Multimodal Analysis"
    )

    print(f"Large Multimodal Analysis Complete - Async: {is_async}, Duration: {duration:.2f}s")


def test_complex_cross_modal_integration_with_webhooks(overlord):
    """Test async processing for complex cross-modal integration with webhook support"""
    print("\n=== Test 3E2 with Webhooks: Complex Cross-Modal Integration ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_integration",
            message="""Design a comprehensive integration framework that can simultaneously process and correlate:
            - Financial reports (PDFs) with quarterly earnings data
            - Executive interview audio recordings with transcript analysis
            - Stock performance charts and market visualization images
            - Social media sentiment data from text and image posts
            - Company presentation videos with slide deck content

            Include detailed workflows for:
            1. Temporal alignment across all modalities
            2. Semantic correlation and conflict resolution
            3. Confidence scoring for integrated insights
            4. Real-time processing pipeline architecture
            5. Quality assurance and validation procedures

            Provide specific technical implementation details for each component."""
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['integration', 'framework', 'correlation', 'temporal', 'semantic', 'pipeline', 'workflow'],
        min_keywords=4,
        min_length=400,
        timeout=45.0,
        test_name="Complex Cross-Modal Integration"
    )

    print(f"Cross-Modal Integration Complete - Async: {is_async}")


def test_large_scale_processing_strategy_with_webhooks(overlord):
    """Test async processing for large-scale processing strategy with webhook support"""
    print("\n=== Test 3E2 with Webhooks: Large Scale Processing Strategy ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_scale",
            message="""Create a detailed processing strategy for handling enterprise-scale multimodal content:
            - 10,000+ PDF documents (legal, technical, financial)
            - 50,000+ images (photos, charts, diagrams, screenshots)
            - 5,000+ hours of audio (meetings, calls, presentations)
            - 1,000+ hours of video (training, conferences, demos)

            Address these critical aspects:
            1. Distributed processing architecture
            2. Memory and storage optimization
            3. Load balancing and resource management
            4. Error handling and recovery mechanisms
            5. Progress tracking and monitoring
            6. Quality control and validation processes
            7. Security and privacy considerations
            8. Cost optimization strategies

            Include specific recommendations for cloud infrastructure, processing frameworks, and monitoring tools."""
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['strategy', 'processing', 'distributed', 'architecture', 'optimization', 'enterprise', 'scale'],
        min_keywords=4,
        min_length=300,
        timeout=50.0,
        test_name="Large Scale Processing Strategy"
    )

    print(f"Large Scale Strategy Complete - Async: {is_async}")


def test_async_processing_memory_with_webhooks(overlord):
    """Test memory retention about async processing discussion with webhook support"""
    print("\n=== Test 3E2 with Webhooks: Async Processing Memory ===")

    # Establish context about async work
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_async_memory",
            message="I'm working on async processing for a project with 10TB of mixed media files including documents, images, audio, and video. Processing time is critical."
        )
    )

    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['async', 'processing', '10tb', 'mixed', 'media'],
        min_keywords=2,
        min_length=20,
        test_name="Async Processing Context"
    )

    # Ask about optimization for the specific context
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_async_memory",
            message="What are the key bottlenecks I should watch out for in my project?"
        )
    )

    # Check memory - should recall the 10TB mixed media context
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['10tb', 'mixed', 'media', 'file', 'processing', 'bottleneck', 'performance'],
        min_keywords=2,
        min_length=50,
        test_name="Async Processing Memory"
    )

    print(f"Async Processing Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


if __name__ == "__main__":
    # Run with async support
    async def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"

        formation = Formation()
        await formation.load(str(formation_path))
        
        # Setup webhook testing environment
        setup_webhook_test()

        overlord = await formation.start_overlord()

        try:
            test_large_multimodal_analysis_with_webhooks(overlord)
            test_complex_cross_modal_integration_with_webhooks(overlord)
            test_large_scale_processing_strategy_with_webhooks(overlord)
            test_async_processing_memory_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()

    asyncio.run(run_test())