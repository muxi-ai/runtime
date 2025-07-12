"""
Test 3H1 with Webhooks: Large PDF Async Processing
Test async processing for large PDF files with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_large_pdf_async_processing_with_webhooks():
    """Test large PDF async processing with webhook support"""
    print("\n=== Test 3H1 with Webhooks: Large PDF Async Processing ===")
    
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
            user_id="test_user_large_pdf",
            message="How would you handle processing a 500-page technical manual PDF with complex diagrams, tables, and mathematical formulas? What async processing strategies would you use?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["large", "pdf", "async", "processing", "page", "complex", "diagram", "strategy"],
            min_keywords=4,
            min_length=150,
            test_name="Large PDF Async Processing"
        )
        
        print(f"Large PDF Async Processing Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_large_pdf_async_processing_with_webhooks())