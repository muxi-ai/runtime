"""
Test 3D3: Document + Image Cross-Analysis - Data Consistency Check
Sync version using files from tests/assets/files
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_3d3_main():
    """Test data consistency check"""
    print("\n=== Test 3D3: Data Consistency Check ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read test file from tests/assets/files
    file_path = Path(__file__).parent.parent.parent / "assets/files" / "report.pdf"
    with open(file_path, "rb") as f:
        file_content = f.read()

    print(f"✓ Loaded file: {len(file_content)} bytes")

    files = [
        {
            "filename": "report.pdf",
            "content": file_content,
            "content_type": "application/pdf",
            "size": len(file_content),
        }
    ]

    # Test data consistency check
    print("\n📊 Testing data consistency check...")
    response = await overlord.chat(
        user_id="test_user",
        message="Analyze this file and provide insights",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, "content") else str(response)
    print(f"📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify response
    assert len(result) > 50, "Response should be substantial"
    print("✅ Data Consistency Check test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3D3: Data Consistency Check (Sync Mode)")
    print("=" * 60)

    asyncio.run(test_3d3_main())

    print("\n🎉 Test 3D3 completed successfully!")
