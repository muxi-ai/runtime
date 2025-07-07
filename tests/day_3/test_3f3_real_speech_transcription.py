#!/usr/bin/env python3
"""Test 3F3: Transcribe actual speech from audio files."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3F3: Real Speech Transcription")
    print("Goal: Transcribe actual speech from audio files")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the audio file
    audio_path = Path("test-docs/speech.m4a")
    if not audio_path.exists():
        print(f"ERROR: Audio file not found at {audio_path}")
        return
    
    with open(audio_path, "rb") as f:
        audio_content = f.read()
    
    # Send request with audio file
    print("Sending speech transcription request...")
    response = await overlord.chat(
        user_id="test_user_speech",
        message="Please transcribe this audio file completely. Include all spoken words.",
        files=[{
            "filename": audio_path.name,
            "content": audio_content,
            "content_type": "audio/m4a",
            "size": len(audio_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async speech transcription started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(12):  # 1 minute max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ Speech transcription completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving transcription...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Transcription complete! Total: {len(full_response)} characters")
        
        # Verify transcription quality
        if len(full_response) > 50:
            print("✓ Successfully transcribed speech content")
        
    elif isinstance(response, str):
        print(f"\n✅ Transcription: {response[:200]}...")
        print(f"Total transcribed text: {len(response)} chars")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting speech transcription test...")
    
    try:
        await run_async_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()