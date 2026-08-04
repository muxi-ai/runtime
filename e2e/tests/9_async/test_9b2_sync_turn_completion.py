#!/usr/bin/env python3
"""
Test 9B2: Sync/Streaming Turn Request Completion

Ordinary chat turns register in the RequestTracker as PROCESSING. Only the
overlord fast path and the async background path ever wrote COMPLETED back,
so a turn that had already answered stayed "processing" until the stale
request reaper rewrote it to FAILED 600s later.

This test drives a real sync turn and a real streaming turn against a live
formation and asserts both end up COMPLETED in the tracker with their
response stored as the result -- the state GET /v1/requests/{id} reads.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation.background.request_tracker import RequestStatus  # noqa: E402


def main():
    """Test terminal request status for sync and streaming turns."""
    test = BaseAsyncTest(
        "9b2_sync_turn_completion",
        "Test sync and streaming turns reach COMPLETED in the request tracker",
    )

    async def check_terminal_status(request_id: str, label: str) -> bool:
        """Assert the tracker holds a COMPLETED entry with a stored result."""
        state = await test.overlord.request_tracker.get_request(request_id)

        if state is None:
            test.formatter.print_failure(f"{label}: request {request_id} not tracked")
            return False

        if state.status != RequestStatus.COMPLETED:
            test.formatter.print_failure(f"{label}: expected COMPLETED, got {state.status.value}")
            return False

        if not state.result:
            test.formatter.print_failure(f"{label}: COMPLETED but no result stored")
            return False

        if state.end_time is None:
            test.formatter.print_failure(f"{label}: COMPLETED but end_time not stamped")
            return False

        test.formatter.print_success(f"{label}: COMPLETED with result stored")
        return True

    async def run_completion_test():
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))

        message = "What is 2 + 2? Answer with just the number."

        # --- Sync turn -------------------------------------------------
        sync_request_id = "req_e2e_9b2_sync"
        sync_response = await test.overlord.chat(
            message,
            user_id="test_user",
            session_id="async_test_9b2_sync",
            request_id=sync_request_id,
            use_async=False,
            stream=False,
        )
        sync_content = getattr(sync_response, "content", str(sync_response))
        test.formatter.print_debug(f"Sync response: {sync_content}")

        sync_ok = await check_terminal_status(sync_request_id, "Sync turn")
        test.transcript.append((message, str(sync_content)))

        # --- Streaming turn --------------------------------------------
        stream_request_id = "req_e2e_9b2_stream"
        stream_generator = await test.overlord.chat(
            message,
            user_id="test_user",
            session_id="async_test_9b2_stream",
            request_id=stream_request_id,
            use_async=False,
            stream=True,
        )

        events = []
        async for event in stream_generator:
            events.append(event)

        event_types = [event.get("type") for event in events if isinstance(event, dict)]
        test.formatter.print_debug(f"Stream events: {event_types}")

        if "completed" not in event_types:
            test.formatter.print_failure("Streaming turn never emitted a terminal event")
            stream_ok = False
        else:
            stream_ok = await check_terminal_status(stream_request_id, "Streaming turn")

        success = sync_ok and stream_ok
        test.results.append(success)

        test.print_async_summary()
        await test.cleanup_formation()

        return 0 if success else 1

    import asyncio
    import os

    result = asyncio.run(run_completion_test())
    os._exit(result)  # Force exit to avoid cleanup hangs


if __name__ == "__main__":
    import os

    try:
        main()
        print("SUCCESS", flush=True)
        os._exit(0)
    except SystemExit as e:
        if e.code == 0:
            print("SUCCESS", flush=True)
        os._exit(e.code or 0)
    except Exception:
        os._exit(1)
