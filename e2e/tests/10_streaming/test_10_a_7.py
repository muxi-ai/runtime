#!/usr/bin/env python3
"""
Test 10A7: Final-Response Token Streaming (content deltas)

Tests that the final assistant response streams as incremental
``type: "content"`` events during a streaming chat turn, while the
terminal ``completed`` event still carries the full final text.

Contract under test (feature: overlord.config.response.stream_tokens,
default true):

(a) at least one ``content`` event arrives BEFORE the terminal
    ``completed`` event;
(b) the concatenated ``content`` deltas equal the ``completed`` event's
    content, modulo the deterministic output normalization the runtime
    applies to the final text (strip + newline collapse in
    ``clean_response_text`` -- no rewrite step ran on this turn);
(c) the stream terminates cleanly right after ``completed`` (no events
    follow it; the HTTP SSE framing's ``event: done`` is emitted by the
    unchanged route layer on top of exactly this termination).
"""

import asyncio
import re
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from base_streaming_test import BaseStreamingTest


def normalize_final_text(text: str) -> str:
    """Mirror the runtime's deterministic final-text normalization.

    The runtime cleans the accumulated persona output before putting it
    in the ``completed`` event (``clean_response_text``: strip invisible
    chars, drop separator-only lines, strip, collapse 3+ newlines).
    Deltas are emitted raw as the provider chunks them, so we apply the
    same normalization to both sides before comparing.
    """
    text = re.sub(r"^[─━═┄┅┈┉\-_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main():
    """Test final-response content delta streaming."""
    test = BaseStreamingTest(
        "10a7_content_delta_streaming",
        "Test final response streams as incremental content events",
    )

    async def run_content_delta_test():
        # Setup formation using the shared streaming formation
        formation_path = Path(__file__).parent / "formations" / "formation-streaming"
        await test.setup_formation(formation_path=str(formation_path))

        # An actionable question: routed to an agent, then the persona
        # pass produces the final text (the streamed LLM call under test).
        response = await test.overlord.chat(
            message="What are the key principles of quantum computing?",
            user_id="test_user",
            session_id="streaming_test_10a7",
            use_async=False,
            stream=True,
        )

        success = True

        if not hasattr(response, "__aiter__"):
            test.formatter.print_failure(f"Response is not a stream: {type(response)}")
            test.results.append(False)
            test.print_streaming_summary()
            await test.cleanup_formation()
            return 1

        stream_result = await test.consume_stream(response, timeout=90.0)
        events = stream_result["events"]

        event_types = [e.get("type") for e in events if isinstance(e, dict)]
        test.formatter.print_debug(f"Event sequence: {event_types}")

        content_events = [e for e in events if isinstance(e, dict) and e.get("type") == "content"]
        completed_events = [
            e for e in events if isinstance(e, dict) and e.get("type") == "completed"
        ]

        # --- Terminal completed event still carries the full text ---
        if len(completed_events) != 1:
            test.formatter.print_failure(
                f"Expected exactly one completed event, got {len(completed_events)}"
            )
            success = False
            completed_content = ""
        else:
            completed_content = completed_events[0].get("content", "")
            if not completed_content:
                test.formatter.print_failure("completed event has empty content")
                success = False
            else:
                test.formatter.print_success(
                    f"completed event carries full text ({len(completed_content)} chars)"
                )

        # --- (a) at least one content event, all before completed ---
        if not content_events:
            test.formatter.print_failure("No content delta events received")
            success = False
        else:
            test.formatter.print_success(f"Received {len(content_events)} content delta events")
            completed_idx = next(
                (
                    i
                    for i, e in enumerate(events)
                    if isinstance(e, dict) and e.get("type") == "completed"
                ),
                len(events),
            )
            late = [
                i
                for i, e in enumerate(events)
                if isinstance(e, dict) and e.get("type") == "content" and i > completed_idx
            ]
            if late:
                test.formatter.print_failure(
                    f"content events arrived AFTER completed at indexes {late}"
                )
                success = False
            else:
                test.formatter.print_success("All content deltas arrived before completed")

            # Envelope fields ride every content event
            first = content_events[0]
            for field in ("request_id", "user_id", "session_id", "timestamp"):
                if field not in first:
                    test.formatter.print_failure(f"content event missing '{field}'")
                    success = False

        # --- (b) concatenated deltas == completed content (normalized) ---
        if content_events and completed_content:
            concatenated = "".join(e.get("content", "") for e in content_events)
            if normalize_final_text(concatenated) == normalize_final_text(completed_content):
                test.formatter.print_success("Concatenated deltas match completed content")
            else:
                test.formatter.print_failure(
                    "Concatenated deltas do NOT match completed content\n"
                    f"--- deltas ({len(concatenated)} chars): {concatenated[:200]}...\n"
                    f"--- completed ({len(completed_content)} chars): "
                    f"{completed_content[:200]}..."
                )
                success = False

        # --- (c) stream terminates cleanly right after completed ---
        if events and isinstance(events[-1], dict) and events[-1].get("type") == "completed":
            test.formatter.print_success(
                "Stream terminated cleanly after completed (SSE layer emits "
                "event: done on this termination)"
            )
        else:
            last_type = events[-1].get("type") if events else "none"
            test.formatter.print_failure(
                f"Stream did not end on completed (last event: {last_type})"
            )
            success = False

        test.results.append(success)

        if success:
            test.formatter.print_success("Content delta streaming test passed")
        else:
            test.formatter.print_failure("Content delta streaming test failed")

        test.print_streaming_summary()
        await test.cleanup_formation()

        return 0 if success else 1

    return asyncio.run(run_content_delta_test())


if __name__ == "__main__":
    import os

    exit_code = main()
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
