"""
Test 3H2 with Webhooks: Long Audio Async Processing  
Test async processing for long audio files with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_long_audio_async_processing_with_webhooks():
    """Test long audio async processing with webhook support"""
    print("\n=== Test 3H2 with Webhooks: Long Audio Async Processing ===")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        response = await overlord.chat(
            user_id="test_user_long_audio",
            message="How would you process a 4-hour conference recording with multiple speakers, varying audio quality, and mixed content (presentations, Q&A, discussions)?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["audio", "hour", "conference", "speaker", "quality", "process", "presentation", "discussion"],
            min_keywords=4,
            min_length=150,
            test_name="Long Audio Async Processing"
        )
        
        print(f"Long Audio Async Processing Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_long_audio_async_processing_with_webhooks())