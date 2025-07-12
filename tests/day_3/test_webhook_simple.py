"""
Simple webhook test to verify webhook functionality
"""

import sys
sys.path.insert(0, ".")
import asyncio
from pathlib import Path

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import get_response_universal
from tests.day_3.webhook_test_utils import (
    setup_webhook_test,
    extract_request_id,
    wait_for_webhook_result,
)


async def test_webhook():
    """Test webhook functionality directly"""
    
    # Setup
    setup_webhook_test()
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("\n=== Testing Webhook Functionality ===")
    
    # Force async with a complex request
    response = get_response_universal(
        overlord.chat(
            user_id="test_webhook_user",
            message=(
                "Create an extremely detailed 5000-word essay about the history, "
                "technology, applications, and future of artificial intelligence. "
                "Include sections on machine learning, deep learning, neural networks, "
                "computer vision, natural language processing, and robotics. "
                "This should be comprehensive and detailed."
            ),
            use_async=True,
        )
    )
    
    print(f"\nResponse: {response}")
    print(f"\nResponse type: {type(response)}")
    print(f"\nResponse length: {len(str(response))}")
    
    # Extract request ID with improved pattern
    request_id = extract_request_id(response)
    print(f"\nExtracted request ID: {request_id}")
    
    if request_id:
        print(f"\n⏳ Waiting for webhook (request_id: {request_id})...")
        webhook_result = wait_for_webhook_result(request_id, timeout=60)
        
        if webhook_result:
            print(f"\n✅ Webhook received!")
            print(f"Result length: {len(str(webhook_result))} characters")
            print(f"Result preview: {str(webhook_result)[:500]}...")
        else:
            print("\n❌ No webhook received")
    else:
        print("\n❌ Could not extract request ID")
        # Print response for debugging
        print(f"\nFull response for debugging:")
        print(response)
    
    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    asyncio.run(test_webhook())