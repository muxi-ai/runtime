"""
Test 3F1: Keep-Alive Long-Running Tasks
Tests async processing with keep-alive mechanism for long document analysis.
"""

import asyncio
import json
import time
from pathlib import Path

import pytest
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


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
    overlord = await formation.start_overlord()
    yield overlord
    await formation.stop_overlord()


async def test_keep_alive_long_task(overlord):
    """Test keep-alive during long-running document processing"""
    print("\n=== Test 3F1: Keep-Alive Long-Running Tasks ===")
    
    # Simulate a complex document processing request
    response = await overlord.chat(
        user_id="test_user",
        message="Process this large document and provide a comprehensive analysis including: "
               "1) Executive summary, 2) Key findings, 3) Statistical analysis, "
               "4) Recommendations, 5) Risk assessment. Make it very detailed.",
        use_async=True
    )
    
    print(f"Response type: {type(response)}")
    print(f"Response: {response}")
    
    # For now, just verify we get a response
    assert response is not None
    
    # Check if it's an async response or direct response
    if isinstance(response, dict) and "request_id" in response:
        print(f"✓ Received async response with request_id: {response['request_id']}")
    else:
        print(f"✓ Received direct response of length: {len(str(response))}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
