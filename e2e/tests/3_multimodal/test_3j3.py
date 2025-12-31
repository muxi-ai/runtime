"""
Test 3J3: Corrupted File Handling - Broken Video Frames
Sync version using files from tests/assets/files
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_3j3_main():
    """Test broken video frames"""
    print("\n=== Test 3J3: Broken Video Frames ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read the corrupted video file
    corrupted_video_path = Path(__file__).parent.parent.parent / "assets/files" / "corrupted_video.mov"
    with open(corrupted_video_path, "rb") as f:
        corrupted_content = f.read()

    print(f"✓ Loaded corrupted video: {len(corrupted_content)} bytes")

    files = [{
        "filename": "corrupted_video.mov",
        "content": corrupted_content,
        "content_type": "video/quicktime",
        "size": len(corrupted_content)
    }]

    # Test broken video frames
    print("\n📊 Testing broken video frames...")
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
    print("✅ Broken Video Frames test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3J3: Broken Video Frames (Sync Mode)")
    print("=" * 60)

    asyncio.run(test_3j3_main())

    print("\n🎉 Test 3J3 completed successfully!")
