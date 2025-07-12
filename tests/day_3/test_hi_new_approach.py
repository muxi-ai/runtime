"""
Test simple 'hi' with new webhook approach
"""

import sys
sys.path.insert(0, ".")

import asyncio
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import setup_webhook_test, check_response_with_webhook
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


async def test_hi_new_approach():
    """Simple 'hi' test with new universal webhook handling"""
    
    # Setup webhook testing
    setup_webhook_test()
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("\n=== Simple 'hi' Test with New Approach ===")
    
    # Send simple message - don't specify use_async, let system decide
    response = await overlord.chat(
        user_id="test_hi_user",
        message="hi",
        # Note: Not specifying use_async - let formation/system decide
    )
    
    # Handle async generator if needed
    if hasattr(response, '__aiter__'):
        chunks = []
        async for chunk in response:
            chunks.append(chunk)
        response = "".join(chunks)
    
    print(f"\nInitial response type: {type(response)}")
    
    # Use new universal checker
    result, was_async = check_response_with_webhook(
        response,
        expected_keywords=['hello', 'hi', 'hey', 'greet', 'assist'],
        min_keywords=1,
        min_length=10,
        test_name="Hi Test"
    )
    
    print(f"\n✅ Test Results:")
    print(f"  - Processing mode: {'Async (via webhook)' if was_async else 'Synchronous'}")
    print(f"  - Response length: {len(result)} characters")
    print(f"  - Response preview: {result[:100]}...")
    
    # Verify it's a greeting response
    response_lower = result.lower()
    assert any(greeting in response_lower for greeting in ['hello', 'hi', 'hey', 'how can i']), \
        "Response should contain a greeting"
    
    print("\n✅ Greeting verification passed!")
    
    # Cleanup
    print("\n🧹 Shutting down overlord...")
    try:
        await formation.stop_overlord()
        print("✅ Overlord shut down gracefully")
    except Exception as e:
        print(f"⚠️  Overlord shutdown error: {e}")
        formation.kill_overlord()
    
    return was_async


if __name__ == "__main__":
    import time
    start_time = time.time()
    
    was_async = asyncio.run(test_hi_new_approach())
    
    elapsed = time.time() - start_time
    print(f"\n🎉 Test completed in {elapsed:.2f} seconds")
    print(f"📊 Response was: {'ASYNC' if was_async else 'SYNC'}")
    
    # Force exit
    import os
    os._exit(0)