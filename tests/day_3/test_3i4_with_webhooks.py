"""
Test 3I4 with Webhooks: Word Document Extraction Completeness
Test completeness of Word document content extraction with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_word_document_extraction_completeness_with_webhooks():
    """Test Word document extraction completeness with webhook support"""
    print("\n=== Test 3I4 with Webhooks: Word Document Extraction Completeness ===")
    
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
            user_id="test_user_word_extraction",
            message="How would you ensure complete extraction from Word documents including text, tables, headers/footers, images, comments, and tracked changes?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["word", "document", "extraction", "complete", "text", "table", "header", "footer", "comment"],
            min_keywords=4,
            min_length=120,
            test_name="Word Document Extraction Completeness"
        )
        
        print(f"Word Document Extraction Completeness Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_word_document_extraction_completeness_with_webhooks())