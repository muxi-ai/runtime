#!/usr/bin/env python3
"""
Test 25A5: completion delivery resolution (PRD D6).

The channel variant using the existing channel-template fixture
machinery: the user has a PREFERRED proactiveness channel (chan-b) that
differs from the formation default (chan-a). The watch completion must
be delivered through the preferred channel's transformer -- user channel
beats formation default -- exactly like delegation completions.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from aiohttp import web
from watch_common import (
    build_formation,
    load_formation,
    start_watch_directly,
    teardown,
    wait_for_reentry,
    wait_for_terminal,
)

SINK_PORT = 18252
USER = "watch-user"


class SinkServer:
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
    print("MUXI Runtime - Test 25A5: completion delivery resolution (D6)")
    print("=" * 60)

    formation = None
    sink = SinkServer()
    tmp = Path(tempfile.mkdtemp(prefix="muxi-watch-25a5-"))
    try:
        await sink.start()
        print(f"Sink server listening on 127.0.0.1:{SINK_PORT}")

        # default_channel is chan-a; the user will prefer chan-b.
        formation_dir = build_formation(
            tmp,
            interval=1,
            timeout=60,
            polls_to_done=2,
            sink_port=SINK_PORT,
            default_channel="chan-a",
        )
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation.formation_id}")

        # The user's preferred channel wins over the formation default.
        await overlord.user_channel_store.set_preferences(USER, preferred_channel="chan-b")
        print("User preference stored: chan-b (formation default is chan-a)")

        result = await start_watch_directly(overlord, user=USER, label="preferred render")
        job = await wait_for_terminal(overlord, result["job_id"], USER, timeout=60)
        assert job.status == "completed", f"watch failed: {job.error}"
        await wait_for_reentry(overlord, result["job_id"], USER)

        deadline = asyncio.get_event_loop().time() + 30
        while not sink.requests and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(1)
        assert sink.requests, "no notification was delivered to any channel"
        delivered = sink.requests[-1]
        print(f"Delivered to {delivered['path']}: {delivered['json']['text'][:120]}")

        # D6: user channel (preferred chan-b -> /b) beats formation
        # default (chan-a -> /a).
        assert (
            delivered["path"] == "/b"
        ), f"delivery ignored the user's preferred channel: {delivered}"
        assert delivered["json"]["user"] == USER, delivered

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: D6 delivery resolution works for watch completions")
        print("  - completion delivered via the NotificationRouter")
        print("  - user's preferred channel beat the formation default")
        print("  - transformer rendered the agent's answer for the channel")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: (service) watch a fixture render job")
        print(f"System (chan-b): {delivered['json']['text']}")

        print("\nTest 25A5 PASSED")
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
