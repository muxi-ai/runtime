#!/usr/bin/env python3
"""
Test 26A1: watch_job full loop (remote async tools).

The complete PRD flow against a real agent and the fixture stdio MCP job
server: the user asks for a render -> the agent calls submit (an
ordinary sync tool call returning {job_id, status: queued}) -> the
bundled watch SOP fragment drives recognition -> the agent calls
watch_job and acknowledges conversationally -> the deterministic poll
loop flips to succeeded after 2 checks -> completion re-enters the
conversation (route_class: watch, fenced payload) -> the agent's answer
referencing the result is delivered through the notification channel.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from aiohttp import web
from watch_common import (
    TEST_SESSION,
    TEST_USER,
    build_formation,
    content_of,
    find_new_watch,
    load_formation,
    snapshot_watch_ids,
    teardown,
    wait_for_reentry,
    wait_for_terminal,
)

SINK_PORT = 18251
RESULT_URL = "https://img.fixture/fox.png"
TASK = "Please render an image of a fox reading a newspaper."


class SinkServer:
    """Local HTTP sink standing in for channel platform APIs."""

    def __init__(self):
        self.requests = []
        self.runner = None

    async def _handle(self, request: web.Request) -> web.Response:
        self.requests.append({"path": request.path, "json": await request.json()})
        return web.json_response({"ok": True})

    async def start(self):
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", SINK_PORT)
        await site.start()

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()


async def main():
    print("MUXI Runtime - Test 26A1: watch_job full loop")
    print("=" * 60)

    formation = None
    sink = SinkServer()
    tmp = Path(tempfile.mkdtemp(prefix="muxi-watch-26a1-"))
    try:
        await sink.start()
        formation_dir = build_formation(
            tmp, interval=2, timeout=120, polls_to_done=2, sink_port=SINK_PORT
        )
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation.formation_id}")

        before = await snapshot_watch_ids(overlord)

        print(f"\nUser: {TASK}")
        response = await overlord.chat(
            message=TASK,
            user_id=TEST_USER,
            session_id=TEST_SESSION,
            use_async=False,
            stream=False,
        )
        reply = content_of(response)
        print(f"System: {reply[:200]}")

        # The agent recognized the job-shaped submit response (SOP
        # fragment) and registered a watch -- the tracked surface is
        # authoritative.
        entry, user = await find_new_watch(overlord, before)
        assert entry is not None, (
            "the agent did not register a watch via watch_job " "(SOP recognition failed)"
        )
        assert entry["kind"] == "watch"
        assert entry["tool"] == "job-server.check_status"
        print(f"Tracked watch: {entry['id']} status={entry['status']}")
        assert reply.strip(), "the acknowledgment turn produced no reply"

        # The poll loop completes deterministically (2 checks * 2s).
        job = await wait_for_terminal(overlord, entry["id"], user, timeout=90)
        assert job.status == "completed", f"watch failed: {job.error}"
        assert RESULT_URL in (job.result or ""), f"result selector missed: {job.result!r}"
        print(f"Watch result extracted: {job.result!r}")

        # Completion re-entered the conversation (route_class: watch)...
        await wait_for_reentry(overlord, entry["id"], user)

        # ... and the agent's user-facing answer reached the notification
        # channel, referencing the watched result.
        deadline = asyncio.get_event_loop().time() + 30
        while not sink.requests and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(1)
        assert sink.requests, "no notification was delivered to the channel sink"
        delivered = sink.requests[-1]["json"]
        print(f"Channel delivery: {delivered['text'][:160]}")
        assert (
            "fox" in delivered["text"].lower() or RESULT_URL in delivered["text"]
        ), f"the delivered answer does not reference the result: {delivered}"

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: watch_job full loop works end-to-end")
        print("  - agent recognized the job-shaped response via the SOP fragment")
        print("  - watch_job registered a tracked background watch")
        print("  - deterministic polls flipped to succeeded and extracted $.output")
        print("  - completion re-entered the conversation and was delivered")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f"\nUser: {TASK}")
        print(f"System: {reply}")
        print(f"System (notification): {delivered['text']}")

        print("\nTest 26A1 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if formation is not None:
            await teardown(formation)
        await sink.stop()
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
