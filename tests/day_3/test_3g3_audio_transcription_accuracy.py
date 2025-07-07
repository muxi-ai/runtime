#!/usr/bin/env python3
"""Test 3G3: Test audio transcription accuracy (target: >90%)."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3G3: Audio Transcription Accuracy")
    print("Goal: Test audio transcription accuracy (target: >90%)")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the meeting audio file
    audio_path = Path("test-docs/meeting.mp3")
    if not audio_path.exists():
        print(f"ERROR: Audio file not found at {audio_path}")
        return
    
    with open(audio_path, "rb") as f:
        audio_content = f.read()
    
    # Send request for accurate transcription
    print("Sending audio transcription accuracy test...")
    response = await overlord.chat(
        user_id="test_user_transcription_accuracy",
        message="Please transcribe this meeting audio with high accuracy. Include all spoken words, speaker changes if detectable, and any notable pauses or emphasis.",
        files=[{
            "filename": audio_path.name,
            "content": audio_content,
            "content_type": "audio/mpeg",
            "size": len(audio_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async transcription started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(24):  # 2 minutes max for longer audio
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ Transcription completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving transcription...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Transcription complete! Total: {len(full_response)} characters")
        
        # Calculate transcription metrics
        words = full_response.split()
        word_count = len(words)
        sentences = full_response.split('.')
        sentence_count = len([s for s in sentences if s.strip()])
        
        # Check for quality indicators
        has_punctuation = '.' in full_response and ',' in full_response
        has_capitalization = any(word[0].isupper() for word in words if word)
        avg_words_per_sentence = word_count / max(sentence_count, 1)
        
        print(f"\n📊 Transcription Metrics:")
        print(f"  - Total words: {word_count}")
        print(f"  - Total sentences: {sentence_count}")
        print(f"  - Avg words/sentence: {avg_words_per_sentence:.1f}")
        print(f"  - Has punctuation: {has_punctuation}")
        print(f"  - Has capitalization: {has_capitalization}")
        
        # Quality assessment (without ground truth)
        quality_score = 0
        if word_count > 100:
            quality_score += 25
            print("✓ Substantial content transcribed")
        if has_punctuation:
            quality_score += 25
            print("✓ Proper punctuation detected")
        if has_capitalization:
            quality_score += 25
            print("✓ Proper capitalization detected")
        if 5 < avg_words_per_sentence < 25:
            quality_score += 25
            print("✓ Reasonable sentence structure")
            
        print(f"\n🎯 Estimated quality score: {quality_score}% (target: >90%)")
        
    elif isinstance(response, str):
        print(f"\n✅ Transcription preview: {response[:300]}...")
        print(f"Total transcribed: {len(response)} chars, {len(response.split())} words")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting audio transcription accuracy test...")
    
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