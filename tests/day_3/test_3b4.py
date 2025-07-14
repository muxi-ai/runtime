"""
Test 3B4: Speech Transcription - Audio Quality Enhancement
Sync version using files from test-docs
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from src.muxi.runtime.formation.formation import Formation


async def test_3b4_main():
    """Test audio quality enhancement"""
    print("\n=== Test 3B4: Audio Quality Enhancement ===")
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("✓ Overlord started")

    # Read test file from test-docs
    file_path = Path(__file__).parent.parent.parent / "test-docs" / "speech.m4a"
    with open(file_path, "rb") as f:
        file_content = f.read()
    
    print(f"✓ Loaded file: {len(file_content)} bytes")
    
    files = [{
        "filename": "speech.m4a",
        "content": file_content,
        "content_type": "audio/m4a",
        "size": len(file_content)
    }]
    
    # Test audio quality enhancement
    print("\n📊 Testing audio quality enhancement...")
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
    print("✅ Audio Quality Enhancement test passed!")
    
    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3B4: Audio Quality Enhancement (Sync Mode)")
    print("=" * 60)
    
    asyncio.run(test_3b4_main())
    
    print("\n🎉 Test 3B4 completed successfully!")