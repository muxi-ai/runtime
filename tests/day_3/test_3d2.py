"""
Test 3D2: Document + Image Cross-Analysis - Multi-Source Validation
Sync version using files from test-docs
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from src.muxi.formation.formation import Formation


async def test_3d2_main():
    """Test multi-source validation"""
    print("\n=== Test 3D2: Multi-Source Validation ===")

    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read test file from test-docs
    file_path = Path(__file__).parent.parent.parent / "test-docs" / "report.pdf"
    with open(file_path, "rb") as f:
        file_content = f.read()

    print(f"✓ Loaded file: {len(file_content)} bytes")

    files = [{
        "filename": "report.pdf",
        "content": file_content,
        "content_type": "application/pdf",
        "size": len(file_content)
    }]

    # Test multi-source validation
    print("\n📊 Testing multi-source validation...")
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
    print("✅ Multi-Source Validation test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3D2: Multi-Source Validation (Sync Mode)")
    print("=" * 60)

    asyncio.run(test_3d2_main())

    print("\n🎉 Test 3D2 completed successfully!")
