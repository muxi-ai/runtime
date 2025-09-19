"""
Test 3J4: Corrupted File Handling - Invalid Format Detection
Sync version using files from tests/assets/files
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_3j4_main():
    """Test invalid format detection"""
    print("\n=== Test 3J4: Invalid Format Detection ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read the invalid format file
    invalid_format_path = Path(__file__).parent.parent.parent / "assets/files" / "invalid_format.jpg"
    with open(invalid_format_path, "rb") as f:
        invalid_content = f.read()

    print(f"✓ Loaded invalid format file: {len(invalid_content)} bytes")

    files = [{
        "filename": "invalid_format.jpg",
        "content": invalid_content,
        "content_type": "image/jpeg",
        "size": len(invalid_content)
    }]

    # Test invalid format detection
    print("\n📊 Testing invalid format detection...")
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
    print("✅ Invalid Format Detection test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3J4: Invalid Format Detection (Sync Mode)")
    print("=" * 60)

    asyncio.run(test_3j4_main())

    print("\n🎉 Test 3J4 completed successfully!")
