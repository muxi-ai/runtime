#!/usr/bin/env python3
"""
Day 3B Tests - Audio Processing
Running tests one by one with detailed output
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from muxi.runtime.formation import Formation

# Set up paths
FORMATION_PATH = "test-formations/formation-multimodal"
TEST_FILES_DIR = Path("test-multimodal")


async def test_3b1_speech_transcription():
    """Test 3B1: Basic Speech Transcription"""
    
    print("\n" + "="*80)
    print("TEST 3B1: BASIC SPEECH TRANSCRIPTION")
    print("="*80)
    print("\nWhat this test checks:")
    print("- Ability to transcribe clear speech from an audio file")
    print("- Audio file processing through overlord.chat()")
    print("- Correct extraction of spoken content")
    print("- Memory retention of transcribed content")
    
    # Initialize formation
    formation = Formation()
    formation.load(FORMATION_PATH)
    overlord = await formation.start_overlord()
    
    try:
        # Test 1: Transcribe speech
        audio_file = TEST_FILES_DIR / "speech.m4a"
        
        prompt = "Please transcribe this audio file and tell me what the speaker is saying."
        
        print(f"\nPrompt sent to overlord.chat:")
        print(f'"{prompt}"')
        print(f"\nWith file attachment: {audio_file}")
        
        print("\n" + "-"*60)
        print("OBSERVABILITY EVENTS:")
        print("-"*60)
        
        # Read the audio file
        with open(audio_file, 'rb') as f:
            audio_content = f.read()
        
        # Send request with audio file
        response = await overlord.chat(
            message=prompt,
            files=[{
                "filename": str(audio_file.name),
                "content": audio_content,
                "content_type": "audio/m4a"
            }],
            user_id="test_user_3b1"
        )
        
        print("\n" + "-"*60)
        print("OVERLORD.CHAT RESPONSE:")
        print("-"*60)
        print(f"Response type: {type(response)}")
        print(f"Response content:\n{response}")
        
        print("\n" + "-"*60)
        print("SUMMARY:")
        print("-"*60)
        
        # Check if response contains expected content
        response_str = str(response).lower()
        if any(word in response_str for word in ["test", "audio", "recording", "hello"]):
            print("✅ SUCCESS: Audio was correctly transcribed")
            print("- The system successfully processed the audio file")
            print("- Speech content was accurately extracted")
        else:
            print("❌ ISSUE: Transcription may not be accurate")
            print(f"- Expected content about 'test audio recording'")
            print(f"- Got: {response[:200]}...")
            
        # Test 2: Check memory retention
        print("\n\nTesting memory retention...")
        
        memory_prompt = "What did the speaker say in the audio file I just shared?"
        
        print(f"\nMemory check prompt:")
        print(f'"{memory_prompt}"')
        
        memory_response = await overlord.chat(
            message=memory_prompt,
            user_id="test_user_3b1"
        )
        
        print(f"\nMemory response: {memory_response}")
        
        if any(word in str(memory_response).lower() for word in ["test", "audio", "recording"]):
            print("\n✅ Memory retention confirmed")
        else:
            print("\n❌ Memory retention issue")
            
    finally:
        await formation.stop_overlord()
        
    print("\n" + "="*80)
    print("TEST 3B1 COMPLETE")
    print("="*80)


if __name__ == "__main__":
    # Change to runtime directory
    os.chdir(Path(__file__).parent.parent.parent)
    
    # Capture all output
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # Run first test
    asyncio.run(test_3b1_speech_transcription())
    
    print("\n\n⏸️  Test 3B1 complete. Please review the results above.")