#!/usr/bin/env python3
"""
Test 23A1: Proactive notification routing via transformers

Verifies the Phase 1 routing precedence end to end:
1. No preference set -> notification resolves to webhook (inert default)
2. PUT /users/{id}/channels sets a preferred channel + addressing context
3. POST /notifications delivers to the preferred channel through its
   transformer (template substitution with the user's stored context)
4. Explicit channels array overrides the preference (multi-channel fan-out)
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
    """Local HTTP sink standing in for channel platform APIs."""

    def __init__(self):
        self.requests = []
        self.runner = None

    async def _handle(self, request: web.Request) -> web.Response:
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "json": await request.json(),
            }
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


async def main():
    print("MUXI Runtime - Test 23A1: Proactive Notification Routing")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-proactive"
    sink = SinkServer()

    try:
        await sink.start()
        print(f"Sink server listening on 127.0.0.1:{SINK_PORT}")

        formation = Formation()
        await formation.load(str(formation_path))
        await formation.start_server(block=False)
        await asyncio.sleep(2)

        base_url = f"http://localhost:{SERVER_PORT}/v1"
        headers = {"X-Muxi-Client-Key": "testing-api-key", "X-Muxi-User-Id": "notify-user"}
        print(f"Formation loaded: {formation.formation_id}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # --- Part 1: preference set via API, notification follows it ----
            print("\nSetting preferred channel via PUT /users/notify-user/channels...")
            response = await client.put(
                f"{base_url}/users/notify-user/channels",
                headers=headers,
                json={
                    "preferred_channel": "chan-b",
                    "channels": {"chan-b": {"room": "ROOM-B1"}},
                },
            )
            assert response.status_code == 200, f"PUT channels failed: {response.text}"
            state = response.json()["data"]
            assert state["preferred_channel"] == "chan-b", state
            print("Preference stored: chan-b with room ROOM-B1")

            print("\nPOST /notifications (no explicit channel)...")
            response = await client.post(
                f"{base_url}/notifications",
                headers=headers,
                json={"user_id": "notify-user", "message": "Preferred channel message"},
            )
            assert response.status_code == 200, f"notify failed: {response.text}"
            result = response.json()["data"]
            assert result["delivered"] == ["chan-b"], f"Wrong routing: {result}"

            assert len(sink.requests) == 1, f"Expected 1 delivery, got {sink.requests}"
            delivered = sink.requests[0]
            assert delivered["path"] == "/b", f"Preferred channel ignored: {delivered}"
            payload = delivered["json"]
            assert payload["text"] == "Preferred channel message", payload
            assert payload["room"] == "ROOM-B1", f"User context not rendered: {payload}"
            assert payload["user"] == "notify-user", payload
            print("Delivered to chan-b transformer with the user's stored context")

            # --- Part 2: explicit channels array overrides preference ------
            print("\nPOST /notifications with explicit channels [chan-a, chan-b]...")
            response = await client.post(
                f"{base_url}/notifications",
                headers=headers,
                json={
                    "user_id": "notify-user",
                    "message": "Fan-out message",
                    "channels": ["chan-a", "chan-b"],
                },
            )
            assert response.status_code == 200, f"notify failed: {response.text}"
            result = response.json()["data"]
            assert result["delivered"] == ["chan-a", "chan-b"], result

            paths = sorted(r["path"] for r in sink.requests[1:])
            assert paths == ["/a", "/b"], f"Multi-channel fan-out broken: {paths}"
            print("Explicit array delivered to both channels")

            # --- Part 3: user without preference resolves per default ------
            print("\nPOST /notifications for a fresh user (default_channel)...")
            response = await client.post(
                f"{base_url}/notifications",
                headers=headers,
                json={"user_id": "fresh-user", "message": "Default channel message"},
            )
            assert response.status_code == 200, f"notify failed: {response.text}"
            result = response.json()["data"]
            # formation declares default_channel: chan-a
            assert result["delivered"] == ["chan-a"], result
            assert sink.requests[-1]["path"] == "/a", sink.requests[-1]
            print("Fresh user routed to the formation default channel")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: Notification routing precedence works end-to-end")
        print("  - Preferred channel routed through its transformer")
        print("  - User addressing context rendered into the template")
        print("  - Explicit channel arrays fan out and override preference")
        print("  - Fresh users fall back to the formation default channel")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: (API) notify 'Preferred channel message'")
        print(f"System: delivered {sink.requests[0]['json']['text']} -> chan-b")

        print("\nTest 23A1 PASSED")
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
