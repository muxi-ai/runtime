#!/usr/bin/env python3
"""
Test 23A2: Conversation source tracking ("last" channel)

Verifies that an inbound trigger declaring `channel: chan-b` records the
user's last-used channel (with addressing context parsed from the
platform payload), and that a notification targeting the reserved "last"
channel routes back there - even when the user's preferred channel is
different ("reply where they are").
"""

import asyncio
import sys
from pathlib import Path

import httpx
from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

SINK_PORT = 18239
SERVER_PORT = 18231


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
    print("MUXI Runtime - Test 23A2: Last-Channel Tracking")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-proactive"
    sink = SinkServer()

    try:
        await sink.start()

        formation = Formation()
        await formation.load(str(formation_path))
        await formation.start_server(block=False)
        await asyncio.sleep(2)

        base_url = f"http://localhost:{SERVER_PORT}/v1"
        headers = {"X-Muxi-Client-Key": "testing-api-key", "X-Muxi-User-Id": "platform-user"}
        print(f"Formation loaded: {formation.formation_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # The user prefers chan-a...
            response = await client.put(
                f"{base_url}/users/platform-user/channels",
                headers=headers,
                json={"preferred_channel": "chan-a"},
            )
            assert response.status_code == 200, f"PUT channels failed: {response.text}"
            print("Preference set to chan-a")

            # ...but their latest message arrives on chan-b via a trigger
            # whose frontmatter declares `channel: chan-b` and parses the
            # room id from the platform payload.
            print("\nFiring inbound trigger (channel: chan-b)...")
            response = await client.post(
                f"{base_url}/triggers/inbound-b",
                headers=headers,
                json={
                    "data": {
                        "event": {
                            "text": "Say OK.",
                            "user": "platform-user",
                            "room": "ROOM-B7",
                        }
                    },
                    "use_async": True,
                },
            )
            assert response.status_code == 200, f"Trigger failed: {response.text}"

            # Last-channel recording happens when the chat turn starts;
            # poll the channels endpoint until it lands.
            print("Waiting for last-channel recording...")
            state = None
            for _ in range(30):
                response = await client.get(
                    f"{base_url}/users/platform-user/channels", headers=headers
                )
                assert response.status_code == 200, response.text
                state = response.json()["data"]
                if state.get("last_channel") == "chan-b":
                    break
                await asyncio.sleep(1)

            assert (
                state and state["last_channel"] == "chan-b"
            ), f"Last channel not recorded: {state}"
            assert (
                state["channels"].get("chan-b", {}).get("room") == "ROOM-B7"
            ), f"Trigger parse context not captured into channel state: {state}"
            assert state["preferred_channel"] == "chan-a", state
            print("Last channel recorded: chan-b (room ROOM-B7); preference still chan-a")

            # A notification targeting "last" must go to chan-b, not the
            # preferred chan-a.
            print("\nPOST /notifications with channels=['last']...")
            sink_count_before = len(sink.requests)
            response = await client.post(
                f"{base_url}/notifications",
                headers=headers,
                json={
                    "user_id": "platform-user",
                    "message": "Reply where they are",
                    "channels": ["last"],
                },
            )
            assert response.status_code == 200, f"notify failed: {response.text}"
            result = response.json()["data"]
            assert result["delivered"] == ["chan-b"], f"'last' did not route to chan-b: {result}"

            deliveries = sink.requests[sink_count_before:]
            notify_hits = [d for d in deliveries if d["json"].get("text") == "Reply where they are"]
            assert len(notify_hits) == 1, f"Notification delivery missing: {deliveries}"
            assert notify_hits[0]["path"] == "/b", notify_hits
            assert (
                notify_hits[0]["json"]["room"] == "ROOM-B7"
            ), f"Captured addressing context not used for 'last' delivery: {notify_hits}"
            print("Notification followed the conversation to chan-b with its room context")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: Last-channel tracking works end-to-end")
        print("  - Trigger frontmatter channel recorded as the user's last channel")
        print("  - Addressing context captured from the trigger parse spec")
        print("  - 'last' target routed the notification back to that channel")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: (chan-b trigger) Say OK.")
        print("System: (notification via chan-b) Reply where they are")

        print("\nTest 23A2 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if "formation" in locals():
            formation.stop()
        await sink.stop()
        await asyncio.sleep(1)


if __name__ == "__main__":
    success = asyncio.run(main())
    import os

    os._exit(0 if success else 1)
