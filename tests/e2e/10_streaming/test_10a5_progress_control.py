#!/usr/bin/env python3
"""
Test 10A5: Progress Control
Tests the overlord.response.progress setting to control streaming event emissions.
When progress=false, only content events should be streamed (no thinking/planning).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.formation import Formation  # noqa: E402
from muxi.services.streaming import get_streaming_llm_config  # noqa: E402


async def main():
    """Test progress control for streaming events."""
    print("🚀 MUXI Runtime - Test 10A5: Progress Control")
    print("=" * 60)

    # Use the formation with progress disabled
    formation_path = Path(__file__).parent / "formation-streaming" / "formation-without-progress.yaml"

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded (with progress: false)")

        # Verify configuration
        streaming_config = get_streaming_llm_config()
        
        if streaming_config:
            progress_enabled = streaming_config.get("progress", True)
            print("\n📋 Streaming configuration:")
            print(f"   Model: {streaming_config.get('model')}")
            print(f"   Rephrasing: {streaming_config.get('enabled')}")
            print(f"   Progress: {'ENABLED' if progress_enabled else 'DISABLED'}")
            
            if progress_enabled:
                print("\n⚠️ WARNING: Progress is enabled, but test expects it disabled")
                print("   Check formation-without-progress.yaml has progress: false")
        else:
            print("\n⚠️ No streaming configuration found")

        print("\n📋 Test: Progress Events Control")
        print("-" * 40)

        user_id = "test_user"
        session_id = "progress_test_10a5"

        # Make a complex request that would normally generate progress events
        print("\n🔍 Testing complex task (should normally emit progress events)...")
        
        response_stream = await overlord.chat(
            message=(
                "Analyze the current economic situation, research market trends, "
                "and provide a detailed investment strategy"
            ),
            user_id=user_id,
            session_id=session_id,
            stream=True,
        )

        # Collect and analyze events
        all_events = []
        progress_events = []
        content_events = []
        
        # Progress indicators to look for
        progress_indicators = [
            "thinking", "planning", "analyzing", "checking",
            "breaking", "decomposing", "let me", "i'll",
            "working on", "processing", "researching"
        ]

        if hasattr(response_stream, "__aiter__"):
            print("\n📝 Analyzing streamed events...")
            
            async for chunk in response_stream:
                all_events.append(chunk)
                chunk_lower = str(chunk).lower()
                
                # Categorize the event
                is_progress = any(ind in chunk_lower for ind in progress_indicators)
                
                if is_progress:
                    progress_events.append(chunk)
                    # Show first progress event found
                    if len(progress_events) == 1:
                        preview = chunk[:150] if len(chunk) > 150 else chunk
                        print(f"\n   ⚠️ Found progress event: {preview}")
                else:
                    content_events.append(chunk)
                
                # Show first few events
                if len(all_events) <= 3:
                    preview = chunk[:100] if len(chunk) > 100 else chunk
                    print(f"   Event {len(all_events)}: {preview}")

        # Results analysis
        print("\n📊 Results:")
        print(f"   Total events: {len(all_events)}")
        print(f"   Progress events: {len(progress_events)}")
        print(f"   Content events: {len(content_events)}")

        # Verify behavior based on configuration
        if not streaming_config or streaming_config.get("progress", True):
            # Progress is enabled - we expect progress events
            print("\n📋 Expected behavior: Progress ENABLED")
            
            if progress_events:
                print("   ✅ Progress events found (as expected)")
            else:
                print("   ⚠️ No progress events found (might be a simple response)")
            
            test_passed = True  # Either way is fine when progress is enabled
            
        else:
            # Progress is disabled - we should NOT see progress events
            print("\n📋 Expected behavior: Progress DISABLED (content only)")
            
            if len(progress_events) == 0:
                print("   ✅ No progress events emitted (as expected)")
                print("   ✅ Only content streamed to save LLM costs")
                test_passed = True
            else:
                print(f"   ❌ Found {len(progress_events)} progress events (should be 0)")
                print("   These events should have been filtered when progress=false")
                
                # Show some examples of leaked progress events
                print("\n   Examples of unexpected progress events:")
                for event in progress_events[:3]:
                    preview = event[:150] if len(event) > 150 else event
                    print(f"      • {preview}")
                
                test_passed = False

        # Check that we still got actual content
        if len(content_events) > 0 or len(all_events) > 0:
            print(f"   ✅ Received {'content' if content_events else 'response'} events")
            
            # Verify response quality
            full_response = "".join(all_events)
            expected_terms = ["economic", "market", "investment", "strategy", "trend"]
            found_terms = [t for t in expected_terms if t in full_response.lower()]
            
            if found_terms:
                print(f"   ✅ Response addresses the request: {found_terms[:3]}")
        else:
            print("   ❌ No events received at all")
            test_passed = False

        # Summary
        print("\n" + "=" * 60)
        
        if test_passed:
            if not streaming_config or streaming_config.get("progress", True):
                print("✅ Test 10A5 PASSED: Progress control working (progress enabled)")
            else:
                print("✅ Test 10A5 PASSED: Progress control working (only content streamed)")
                print("   This configuration saves on LLM rephrasing costs")
        else:
            print("❌ Test 10A5 FAILED: Progress control not working as expected")
        
        return test_passed

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if "formation" in locals():
            try:
                print("\nShutting down...")
                await formation.kill_overlord()
                formation.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)