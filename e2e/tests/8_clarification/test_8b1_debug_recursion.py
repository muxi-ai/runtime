#!/usr/bin/env python3
"""
Debug version of test 8b1 that captures full RecursionError stack trace.
"""

import asyncio
import sys
import traceback
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


# Disable asyncio's default exception handler to prevent recursion
def custom_asyncio_exception_handler(loop, context):
    """Custom handler that doesn't use logging (which causes recursion)"""
    exception = context.get("exception")
    message = context.get("message")
    sys.stdout.write(f"\n🔥 ASYNCIO EXCEPTION: {message}\n")
    if exception:
        sys.stdout.write(f"Exception type: {type(exception).__name__}\n")
        sys.stdout.write(f"Exception: {exception}\n")
        traceback.print_exception(type(exception), exception, exception.__traceback__)
    sys.stdout.flush()


# Set custom exception handler for asyncio
loop = asyncio.get_event_loop()
loop.set_exception_handler(custom_asyncio_exception_handler)


# Monkey patch sys.excepthook to capture RecursionError stack traces
original_excepthook = sys.excepthook
recursion_traces = []


def custom_excepthook(exc_type, exc_value, exc_traceback):
    if exc_type == RecursionError:
        print("\n" + "=" * 80)
        print("🔥 CAUGHT RecursionError! Full stack trace:")
        print("=" * 80)
        trace_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        full_trace = "".join(trace_lines)
        print(full_trace)
        recursion_traces.append(full_trace)
        print("=" * 80 + "\n")
    original_excepthook(exc_type, exc_value, exc_traceback)


sys.excepthook = custom_excepthook

# Also patch threading excepthook for background threads
original_threading_excepthook = threading.excepthook


def custom_threading_excepthook(args):
    if args.exc_type == RecursionError:
        print("\n" + "=" * 80)
        print("🔥 CAUGHT RecursionError in thread! Full stack trace:")
        print(f"Thread: {args.thread.name}")
        print("=" * 80)
        trace_lines = traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        full_trace = "".join(trace_lines)
        print(full_trace)
        recursion_traces.append(full_trace)
        print("=" * 80 + "\n")
    original_threading_excepthook(args)


threading.excepthook = custom_threading_excepthook


async def test_multi_turn_clarification():
    """Test multi-turn clarification flow."""
    print("\n" + "=" * 80)
    print("Test 8B1: Multi-Turn Clarification (DEBUG VERSION)")
    print("=" * 80)

    formation_path = (
        Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"
    )

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")

        # Test multi-turn clarification flow
        session_id = "multi_turn_test"
        user_id = "test_user"

        # Turn 1: Send ambiguous request
        print("\n2. Turn 1: Sending ambiguous request...")
        print("   Request: 'Build a website'")
        response1 = await overlord.chat(
            message="Build a website", user_id=user_id, session_id=session_id, stream=False
        )

        content1 = response1.content if hasattr(response1, "content") else str(response1)
        print(f"   Response received ({len(content1)} chars)")

        # Check if we got any recursion errors
        if recursion_traces:
            print(f"\n🔥 CAPTURED {len(recursion_traces)} RECURSION ERROR(S)!")
            print("Saving to /tmp/recursion_trace.txt")
            with open("/tmp/recursion_trace.txt", "w") as f:
                for i, trace in enumerate(recursion_traces):
                    f.write(f"\n\n{'='*80}\n")
                    f.write(f"RECURSION ERROR #{i+1}\n")
                    f.write(f"{'='*80}\n\n")
                    f.write(trace)

        # Cleanup
        await formation.stop_overlord()
        formation.stop()
        print("\n✅ Test completed")

        if recursion_traces:
            print(f"\n🔍 Found {len(recursion_traces)} RecursionError(s)")
            print("Full traces saved to /tmp/recursion_trace.txt")
            print("\nFirst few lines of trace:")
            print(recursion_traces[0][:1000])

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    import os
    result = asyncio.run(test_multi_turn_clarification())
    os._exit(result if result is not None else 0)
