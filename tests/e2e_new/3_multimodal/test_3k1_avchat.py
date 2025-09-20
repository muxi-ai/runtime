#!/usr/bin/env python3
"""Test 3K1_AVCHAT: AVChat Transcript Test

This test validates:
1. AVChat functionality with audio files
2. Audio transcription and response generation
3. Synchronous processing mode
"""

import sys
import asyncio
import time
import os
from pathlib import Path

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

sys.path.insert(0, str(Path(__file__).parent))
from base_multimodal_test import BaseMultimodalTest
class TestMultimodal3K1_AVCHAT(BaseMultimodalTest):
    """Test AVChat functionality."""

    async def test_avchat_transcript(self):
        """Test to see actual avchat response."""
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            print("\n🎤 Test: AVChat Transcript Test")

            # Test with a small audio file
            audio_path = Path(__file__).parent.parent.parent / "assets/files" / "audio-request.m4a"

            if not audio_path.exists():
                print(f"   ⚠️ Audio file not found: {audio_path}")
                # Try alternative audio file
                audio_path = Path(__file__).parent.parent.parent / "assets/files" / "speech.m4a"
                if not audio_path.exists():
                    print("   ❌ No audio files available for testing")
                    return False, checks_passed, transcript

            print(f"   📁 Using audio file: {audio_path.name}")
            print(f"   Size: {audio_path.stat().st_size / 1024:.1f} KB")

            # Read and prepare the audio file
            with open(audio_path, 'rb') as f:
                audio_content = f.read()

            audio_file = {
                'content': audio_content,
                'content_type': 'audio/m4a',
                'filename': 'short.m4a'
            }

            # Call avchat with timeout and force synchronous mode
            print("   Calling avchat() with audio file...")
            print("   Generated prompt: 'Please transcribe this audio and respond to what was said.'")
            print("   Mode: Synchronous (use_async=False)")

            transcript.append(("User", "[Uploaded audio file: short.m4a]"))

            try:
                response = await asyncio.wait_for(
                    self.overlord.avchat(
                        files=[audio_file],
                        user_id="test-user",
                        session_id="test-3k1",
                        use_async=False,  # Force synchronous processing
                        stream=False  # Force non-streaming response
                    ),
                    timeout=120.0  # 120 second timeout for audio transcription
                )

                # Extract response content
                if isinstance(response, dict):
                    content = response.get('content', str(response))
                elif hasattr(response, 'content'):
                    content = response.content
                else:
                    content = str(response)

                print(f"   Response length: {len(content)} chars")
                print(f"   Response preview: {content[:200]}...")
                transcript.append(("System", content[:300] + "..."))

                # Verify we got a meaningful response
                if len(content) > 10:  # At least some response
                    checks_passed.append("AVChat: Successfully processed audio file and generated response")
                    print("   ✅ Test completed successfully!")
                else:
                    print("   ❌ Response too short or empty")
                    all_passed = False

            except asyncio.TimeoutError:
                print("   ❌ Timeout: No response after 120 seconds")
                transcript.append(("System", "Error: Timeout after 120 seconds"))
                all_passed = False
            except Exception as e:
                print(f"   ❌ Error during avchat: {e}")
                transcript.append(("System", f"Error: {str(e)}"))
                all_passed = False

        except Exception as e:
            print(f"  ✗ AVChat test failed: {e}")
            all_passed = False

        return all_passed, checks_passed, transcript

    async def test_3k1_avchat(self):
        """Main test method."""
        test_name = "3k1_avchat"
        self.print_test_header(
            test_name,
            "Test AVChat Transcript"
        )

        start_time = time.time()
        all_checks_passed = []
        all_transcript = []
        all_passed = True

        try:
            # Setup formation
            await self.setup_multimodal_formation()
            print("  ✓ Multimodal formation loaded")

            # Run the avchat test
            success, checks, transcript = await self.test_avchat_transcript()
            all_checks_passed.extend(checks)
            all_transcript.extend(transcript)
            if not success:
                all_passed = False

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, all_checks_passed, all_transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "="*60)
        print("🎤📹 AREA 3K1_AVCHAT: AVCHAT TRANSCRIPT")
        print("="*60)

        # Run test cases
        result = await self.test_3k1_avchat()

        print("\n" + "="*60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("="*60)

        return result
def main():
    """Main entry point."""
    test = TestMultimodal3K1_AVCHAT()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)
if __name__ == "__main__":
    main()
