"""
Test 3J2: Corrupted File Handling - Truncated Audio Handling
Sync version using files from test-docs
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from src.muxi.runtime.formation.formation import Formation


async def test_3j2_main():
    """Test truncated audio handling"""
    print("\n=== Test 3J2: Truncated Audio Handling ===")
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("✓ Overlord started")

    # Read the corrupted audio file
    corrupted_audio_path = Path(__file__).parent.parent.parent / "test-docs" / "corrupted_audio.m4a"
    with open(corrupted_audio_path, "rb") as f:
        corrupted_content = f.read()
    
    print(f"✓ Loaded corrupted audio: {len(corrupted_content)} bytes")
    
    files = [{
        "filename": "corrupted_audio.m4a",
        "content": corrupted_content,
        "content_type": "audio/m4a",
        "size": len(corrupted_content)
    }]
    
    # Test truncated audio handling
    print("\n📊 Testing truncated audio handling...")
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
    print("✅ Truncated Audio Handling test passed!")
    
    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3J2: Truncated Audio Handling (Sync Mode)")
    print("=" * 60)
    
    asyncio.run(test_3j2_main())
    
    print("\n🎉 Test 3J2 completed successfully!")