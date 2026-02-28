"""
Test 3C1: Video Frame Analysis - Visual Understanding
Sync version using video files from tests/assets/files
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_video_frame_analysis():
    """Test video frame analysis capabilities"""
    print("\n=== Test 3C1: Video Frame Analysis ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read video file from tests/assets/files
    video_path = Path(__file__).parent.parent.parent / "assets/files" / "demo.mov"
    with open(video_path, "rb") as f:
        video_content = f.read()

    print(f"✓ Loaded video file: {len(video_content)} bytes")

    files = [{
        "filename": "demo.mov",
        "content": video_content,
        "content_type": "video/quicktime",
        "size": len(video_content)
    }]

    # Test video analysis
    print("\n🎥 Testing video frame analysis...")
    response = await overlord.chat(
        user_id="test_user",
        message="Analyze the key frames in this video and describe what you see",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify video analysis response
    result_lower = result.lower()
    expected_keywords = ["video", "frame", "visual", "content", "scene", "analyze"]
    found_keywords = [kw for kw in expected_keywords if kw in result_lower]

    assert len(found_keywords) >= 2, \
        f"Expected at least 2 keywords from {expected_keywords}, found: {found_keywords}"
    assert len(result) > 100, "Video analysis should be detailed"

    print(f"✅ Found keywords: {found_keywords}")
    print("✅ Video frame analysis test passed!")

    # Cleanup
    await formation.stop_overlord()


async def run_all():
    """Run all tests with a single formation load."""
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    print("Formation loaded")

    video_path = Path(__file__).parent.parent.parent / "assets/files" / "demo.mov"
    with open(video_path, "rb") as f:
        video_content = f.read()
    print(f"Video: {len(video_content)} bytes")

    files = [{"filename": "demo.mov", "content": video_content, "content_type": "video/quicktime", "size": len(video_content)}]

    response = await overlord.chat(
        user_id="test_user",
        message="Analyze the key frames in this video and describe what you see",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, "content") else str(response)
    print(f"Response: {len(result)} chars — {result[:150]}...")

    result_lower = result.lower()
    expected = ["video", "frame", "visual", "content", "scene", "analyze"]
    found = [kw for kw in expected if kw in result_lower]
    assert len(found) >= 2, f"Expected 2+ keywords from {expected}, got: {found}"
    assert len(result) > 100

    print(f"Keywords found: {found}")
    print("PASS")


if __name__ == "__main__":
    import os as _os

    print("Running Test 3C1: Video Frame Analysis")
    print("=" * 60)

    asyncio.run(run_all())

    print("SUCCESS", flush=True)
    _os._exit(0)
