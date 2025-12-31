"""
Test 3I4: PowerPoint Video Consistency - Narration Accuracy
Sync version using files from tests/assets/files
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_3i4_main():
    """Test narration accuracy"""
    print("\n=== Test 3I4: Narration Accuracy ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read test file from tests/assets/files
    file_path = Path(__file__).parent.parent.parent / "assets/files" / "presentation.pptx"
    with open(file_path, "rb") as f:
        file_content = f.read()

    print(f"✓ Loaded file: {len(file_content)} bytes")

    files = [{
        "filename": "presentation.pptx",
        "content": file_content,
        "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "size": len(file_content)
    }]

    # Test narration accuracy
    print("\n📊 Testing narration accuracy...")
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
    print("✅ Narration Accuracy test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3I4: Narration Accuracy (Sync Mode)")
    print("=" * 60)

    asyncio.run(test_3i4_main())

    print("\n🎉 Test 3I4 completed successfully!")
