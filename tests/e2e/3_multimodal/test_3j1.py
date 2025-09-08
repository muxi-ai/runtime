"""
Test 3J1: Corrupted File Handling - Partial PDF Recovery
Sync version using files from tests/assets/files
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_3j1_main():
    """Test partial pdf recovery"""
    print("\n=== Test 3J1: Partial PDF Recovery ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read the corrupted PDF file
    corrupted_pdf_path = Path(__file__).parent.parent.parent / "assets/files" / "corrupted_partial.pdf"
    with open(corrupted_pdf_path, "rb") as f:
        corrupted_content = f.read()

    print(f"✓ Loaded corrupted PDF: {len(corrupted_content)} bytes")

    files = [{
        "filename": "corrupted_partial.pdf",
        "content": corrupted_content,
        "content_type": "application/pdf",
        "size": len(corrupted_content)
    }]

    # Test partial pdf recovery
    print("\n📊 Testing partial pdf recovery...")
    response = await overlord.chat(
        user_id="test_user",
        message="Analyze this file and provide insights",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify response
    assert len(result) > 50, "Response should be substantial"
    print("✅ Partial PDF Recovery test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3J1: Partial PDF Recovery (Sync Mode)")
    print("=" * 60)

    asyncio.run(test_3j1_main())

    print("\n🎉 Test 3J1 completed successfully!")
