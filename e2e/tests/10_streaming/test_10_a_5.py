#!/usr/bin/env python3
"""
Test 10A5: Progress Control

Tests the overlord.response.progress setting to control streaming event emissions.
When progress=false, only content events should be streamed (no thinking/planning).
"""

import asyncio
import sys
from pathlib import Path

from .base_streaming_test import BaseStreamingTest


def main():
    """Test progress control for streaming events."""
    test = BaseStreamingTest("10a5_progress_control", "Test progress event control")

    async def run_progress_test():
        # Setup formation using the formation without progress
        # We load formation-without-progress.yaml which has progress: false
        formation_path = Path(__file__).parent / "formations" / "formation-streaming" / "formation-without-progress.yaml"
        
        # Load formation with specific YAML file (progress: false)
        await test.setup_formation(formation_path=str(formation_path))

        test.formatter.print_success("Formation loaded")

        user_id = "test_user"
        session_id = "progress_test_10a5"

        # Make a request that would normally generate progress events
        # Using a simple, non-ambiguous prompt to avoid clarification
        print("\n" + "=" * 60); print("Testing task with progress=false (should only get final content)"); print("=" * 60)

        response_stream = await test.overlord.chat(
            message="What is the capital of France? Please answer in one sentence.",
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
            "thinking",
            "planning",
            "analyzing",
            "checking",
            "breaking",
            "decomposing",
            "let me",
            "i'll",
            "working on",
            "processing",
            "researching",
        ]

        if hasattr(response_stream, "__aiter__"):
            test.formatter.print_debug("Analyzing streamed events...")

            stream_result = await test.consume_stream(response_stream, timeout=30.0)
            all_events = stream_result["events"]

            for chunk in all_events:
                # Extract content from dict events
                if isinstance(chunk, dict):
                    chunk_text = chunk.get("content", "")
                    event_type = chunk.get("type", "")
                    # Progress events might be marked in type
                    if event_type == "progress":
                        progress_events.append(chunk)
                        continue
                else:
                    chunk_text = str(chunk)
                    event_type = ""

                chunk_lower = chunk_text.lower()

                # Categorize the event by content
                is_progress = any(ind in chunk_lower for ind in progress_indicators)

                if is_progress and chunk not in progress_events:
                    progress_events.append(chunk)
                else:
                    content_events.append(chunk)

        # Results analysis
        print("\n" + "=" * 60); print("Results"); print("=" * 60)
        test.formatter.print_debug(f"Total events: {len(all_events)}")
        test.formatter.print_debug(f"Progress events: {len(progress_events)}")
        test.formatter.print_debug(f"Content events: {len(content_events)}")

        # With progress disabled, we should have no progress events
        print("\n" + "=" * 60); print("Expected behavior: Progress DISABLED (content only)"); print("=" * 60)

        if len(progress_events) == 0:
            test.formatter.print_success("No progress events emitted (as expected)")
            test.formatter.print_success("Only content streamed to save LLM costs")
            test_passed = True
        else:
            test.formatter.print_failure(
                f"Found {len(progress_events)} progress events (should be 0)"
            )
            test.formatter.print_error(
                "These events should have been filtered when progress=false"
            )

            # Show some examples
            test.formatter.print_debug("Examples of unexpected progress events:")
            for i, event in enumerate(progress_events[:3], 1):
                if isinstance(event, dict):
                    preview = event.get("content", "")[:100]
                else:
                    preview = str(event)[:100]
                test.formatter.print_debug(f"  {i}. {preview}")

            test_passed = False

        # Check that we still got actual content
        if len(content_events) > 0 or len(all_events) > 0:
            test.formatter.print_success(
                f"Received {'content' if content_events else 'response'} events"
            )

            # Verify response quality
            text_events = []
            for event in all_events:
                if isinstance(event, dict):
                    text_events.append(event.get("content", ""))
                else:
                    text_events.append(str(event))
            full_response = "".join(text_events)

            expected_terms = ["paris", "france", "capital"]
            found_terms = [t for t in expected_terms if t in full_response.lower()]

            if found_terms:
                test.formatter.print_success(f"Response contains expected terms: {found_terms}")
        else:
            test.formatter.print_failure("No events received at all")
            test_passed = False

        # Record result
        test.results.append(test_passed)

        if test_passed:
            test.formatter.print_success("Progress control test passed")
        else:
            test.formatter.print_failure("Progress control test failed")

        # Print streaming summary
        test.print_streaming_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if test_passed else 1

    return asyncio.run(run_progress_test())


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
