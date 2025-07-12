"""
Test 3J3 with Webhooks: Unsupported Format Errors
Test handling of unsupported file formats with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_unsupported_format_errors_with_webhooks():
    """Test unsupported format error handling with webhook support"""
    print("\n=== Test 3J3 with Webhooks: Unsupported Format Errors ===")
    
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
            user_id="test_user_unsupported",
            message="How would you handle unsupported file formats: proprietary document formats, rare audio codecs, obscure video formats, and custom binary files?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["unsupported", "format", "handle", "proprietary", "codec", "binary", "error", "file"],
            min_keywords=4,
            min_length=120,
            test_name="Unsupported Format Errors"
        )
        
        print(f"Unsupported Format Errors Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_unsupported_format_errors_with_webhooks())