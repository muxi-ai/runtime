"""
Test 3H1: Large PDF Async Processing - 500-Page Technical Manual
Sync version using files from test-docs
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from src.muxi.formation.formation import Formation


async def test_3h1_main():
    """Test 500-page technical manual"""
    print("\n=== Test 3H1: 500-Page Technical Manual ===")

    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read test file from test-docs
    file_path = Path(__file__).parent.parent.parent / "test-docs" / "large.pdf"
    with open(file_path, "rb") as f:
        file_content = f.read()

    print(f"✓ Loaded file: {len(file_content)} bytes")

    files = [{
        "filename": "large.pdf",
        "content": file_content,
        "content_type": "application/pdf",
        "size": len(file_content)
    }]

    # Test 500-page technical manual
    print("\n📊 Testing 500-page technical manual...")
    response = await overlord.chat(
        user_id="test_user",
        message="Analyze this file and provide insights",files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify response
    assert len(result) > 50, "Response should be substantial"
    print("✅ 500-Page Technical Manual test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3H1: 500-Page Technical Manual (Sync Mode)")
    print("=" * 60)

    asyncio.run(test_3h1_main())

    print("\n🎉 Test 3H1 completed successfully!")
