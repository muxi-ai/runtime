"""
Test 3D3 with Webhooks: Full Multimodal Processing
Tests the system's understanding of analyzing documents, images, and audio together with webhook support.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
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
    
    # Cleanup
    await formation.stop_overlord()


def test_full_multimodal_analysis_with_webhooks(overlord):
    """Test understanding of analyzing all modalities together with webhook support"""
    print("\n=== Test 3D3 with Webhooks: Full Multimodal Analysis ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_full",
            message="How would you analyze a complete package of: a research paper PDF, data visualization charts, and an author interview audio recording to get a comprehensive understanding of the research?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['paper', 'pdf', 'chart', 'visual', 'audio', 'interview', 'comprehensive', 'analyze'],
        min_keywords=5,
        min_length=200,
        test_name="Full Multimodal Analysis"
    )
    
    print(f"Full Multimodal Analysis Complete - Async: {is_async}")


def test_story_telling_across_modalities_with_webhooks(overlord):
    """Test understanding of narrative construction from multiple sources with webhook support"""
    print("\n=== Test 3D3 with Webhooks: Cross-Modal Story Telling ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_story",
            message="If you had a company's annual report PDF, photos from their events, and CEO speech audio, how would you combine these to tell the complete story of their year?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['story', 'narrative', 'combine', 'report', 'photo', 'speech', 'complete', 'year'],
        min_keywords=4,
        min_length=100,
        test_name="Cross-Modal Story Telling"
    )
    
    print(f"Story Telling Complete - Async: {is_async}")


def test_multimodal_verification_with_webhooks(overlord):
    """Test understanding of cross-modal verification with webhook support"""
    print("\n=== Test 3D3 with Webhooks: Multimodal Verification ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_verify",
            message="How would you use multiple modalities (text documents, images, and audio) to verify the accuracy and consistency of information about an event?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['verify', 'accuracy', 'consistency', 'check', 'confirm', 'multiple', 'source', 'cross'],
        min_keywords=3,
        min_length=80,
        test_name="Multimodal Verification"
    )
    
    print(f"Multimodal Verification Complete - Async: {is_async}")


def test_complex_multimodal_memory_with_webhooks(overlord):
    """Test memory retention about complex multimodal content with webhook support"""
    print("\n=== Test 3D3 with Webhooks: Complex Multimodal Memory ===")
    
    # Establish rich multimodal context
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_complex",
            message="I'm analyzing a product launch: The press release PDF announces a $999 price, the product images show a sleek design with 3 color options, and the launch event audio mentions availability in Q2 2024."
        )
    )
    
    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['product', 'launch', 'press', 'release', 'price', 'image', 'audio'],
        min_keywords=2,
        min_length=20,
        test_name="Multimodal Context Setup"
    )
    
    # Test comprehensive memory across all modalities
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_complex",
            message="Summarize all the key details about the product launch I'm working on."
        )
    )
    
    # Check memory - should recall price, colors, availability
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['$999', '999', 'price', '3', 'color', 'design', 'q2', '2024', 'availability'],
        min_keywords=3,
        min_length=50,
        test_name="Complex Multimodal Memory"
    )
    
    print(f"Complex Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


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
            test_full_multimodal_analysis_with_webhooks(overlord)
            test_story_telling_across_modalities_with_webhooks(overlord)
            test_multimodal_verification_with_webhooks(overlord)
            test_complex_multimodal_memory_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())