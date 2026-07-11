#!/usr/bin/env python3
"""
Test 25A5: Response Envelope UI - channel delivery ignores ui (P1)

Channels (slack/telegram-style transformer templates) are text-first in
P1: the payload a channel platform receives carries the complete text
and NO `ui` field — the text fallback IS the channel experience.

Reuses the existing channel fixture from area 23 (formation-proactive's
sink transformers standing in for channel platform APIs).
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

SINK_PORT = 18239
SERVER_PORT = 18231
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}/v1"
HEADERS = {"X-Muxi-Client-Key": "testing-api-key", "X-Muxi-User-Id": "envelope-channel-user"}


class SinkServer:
    """Local HTTP sink standing in for channel platform APIs."""

    def __init__(self):
        self.requests = []
        self.runner = None

    async def _handle(self, request: web.Request) -> web.Response:
        self.requests.append(
            {"method": request.method, "path": request.path, "json": await request.json()}
        )
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


async def main() -> int:
    print("MUXI Runtime - Test 25A5: channel delivery ignores ui")
    print("=" * 70)

    # Existing channel fixture: area 23's proactive formation with sink
    # transformers standing in for channel platform APIs
    formation_path = Path(__file__).parent.parent / "23_proactive" / "formation-proactive"
    sink = SinkServer()

    formation = Formation()
    try:
        await sink.start()
        print(f"Sink server listening on 127.0.0.1:{SINK_PORT}")

        await formation.load(str(formation_path))
        await formation.start_server(block=False)
        await asyncio.sleep(2)

        async with httpx.AsyncClient(timeout=60.0) as client:
            print("\n[1] Setting preferred channel...")
            response = await client.put(
                f"{BASE_URL}/users/envelope-channel-user/channels",
                headers=HEADERS,
                json={
                    "preferred_channel": "chan-a",
                    "channels": {"chan-a": {"room": "ROOM-UI"}},
                },
            )
            assert response.status_code == 200, f"PUT channels failed: {response.text[:300]}"

            print("[2] Delivering a message through the channel transformer...")
            response = await client.post(
                f"{BASE_URL}/notifications",
                headers=HEADERS,
                json={
                    "user_id": "envelope-channel-user",
                    "message": "Complete text message for the channel",
                },
            )
            assert response.status_code == 200, f"notify failed: {response.text[:300]}"

            assert len(sink.requests) == 1, f"Expected one delivery, got {sink.requests}"
            payload = sink.requests[0]["json"]
            print(f"    Channel payload: {payload}")

            assert (
                payload.get("text") == "Complete text message for the channel"
            ), f"Channel text incomplete: {payload}"
            assert "ui" not in payload, f"Channel payload must not carry ui: {payload}"
            print("    Text complete; no 'ui' field in the channel payload")

        print("\n" + "=" * 70)
        print("SUCCESS: channel delivery carried complete text and no ui field")
        return 0

    finally:
        try:
            formation.stop()
        except Exception:
            pass
        try:
            await sink.stop()
        except Exception:
            pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    os._exit(exit_code)
