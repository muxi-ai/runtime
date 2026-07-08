#!/usr/bin/env python3
"""
Test 23A5: Channel templates + transformer/webhook composition (Phase 2)

Verifies the two Phase 2 mechanisms end to end:

1. Bundled dormant template activated by reference: a trigger whose
   frontmatter declares `transformer: slack` (shipped with the runtime,
   payload format only, no URL) plus `webhook: <dev url>` must format the
   agent response as a Slack chat.postMessage-style payload and deliver it
   to the trigger-supplied webhook URL.

2. Composition with a formation-local URL-less transformer: the trigger's
   webhook URL is the destination, the transformer defines the payload
   shape. This also pins the URL resolution order (trigger URL wins when
   the transformer defines none).
"""

import asyncio
import sys
from pathlib import Path

import httpx
from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

SINK_PORT = 18241
SERVER_PORT = 18233


class SinkServer:
    """Local HTTP sink standing in for the developer's webhook bridge."""

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

    def requests_for(self, path):
        return [r for r in self.requests if r["path"] == path]


async def wait_for(predicate, timeout=45):
    for _ in range(timeout):
        if predicate():
            return True
        await asyncio.sleep(1)
    return predicate()


async def main():
    print("MUXI Runtime - Test 23A5: Channel Template Composition")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-templates"
    sink = SinkServer()

    try:
        # Start the local bridge sink first so delivery cannot race it
        await sink.start()
        print(f"Bridge sink listening on 127.0.0.1:{SINK_PORT}")

        formation = Formation()
        await formation.load(str(formation_path))
        await formation.start_server(block=False)
        await asyncio.sleep(2)

        base_url = f"http://localhost:{SERVER_PORT}/v1"
        headers = {"X-Muxi-Client-Key": "testing-api-key", "X-Muxi-User-Id": "webhook-caller"}
        print(f"Formation loaded: {formation.formation_id}")

        slack_question = "What is the capital of France? Answer with the city name."
        custom_question = "What is two plus two? Answer with the number."

        async with httpx.AsyncClient(timeout=30.0) as client:
            # --- Part 1: bundled 'slack' template + trigger webhook ---------
            print("\nPOST /triggers/slack (bundled template + webhook composition)...")
            response = await client.post(
                f"{base_url}/triggers/slack",
                headers=headers,
                json={
                    "data": {
                        "event": {
                            "text": slack_question,
                            "user": "U-E2E-23A5",
                            "channel": "C-E2E-23A5",
                        }
                    },
                    "use_async": True,
                },
            )
            assert response.status_code == 200, f"Unexpected status: {response.text}"
            print("Async ack received")

            # --- Part 2: formation-local URL-less transformer + webhook -----
            print("POST /triggers/custom (URL-less transformer + webhook composition)...")
            response = await client.post(
                f"{base_url}/triggers/custom",
                headers=headers,
                json={
                    "data": {
                        "payload": {
                            "text": custom_question,
                            "sender": "sender-1",
                            "room": "room-42",
                        }
                    },
                    "use_async": True,
                },
            )
            assert response.status_code == 200, f"Unexpected status: {response.text}"
            print("Async ack received")

        print("\nWaiting for composed deliveries to the bridge sink...")
        assert await wait_for(
            lambda: sink.requests_for("/slack-bridge") and sink.requests_for("/custom-bridge")
        ), f"Deliveries missing; sink saw: {[r['path'] for r in sink.requests]}"

        # Bundled slack template: chat.postMessage-style payload delivered to
        # the TRIGGER-supplied URL (the template itself has none)
        slack_payload = sink.requests_for("/slack-bridge")[0]["json"]
        print(f"Slack bridge received: {slack_payload}")
        assert slack_payload.get("channel") == "C-E2E-23A5", f"Bad channel: {slack_payload}"
        slack_text = slack_payload.get("text", "")
        assert slack_text and "paris" in slack_text.lower(), f"Bad text: {slack_payload}"
        assert "thread_ts" not in slack_payload, "Absent thread_ts must be dropped, not null"
        assert set(slack_payload.keys()) <= {"channel", "thread_ts", "text"}, (
            f"Unexpected keys in Slack payload: {sorted(slack_payload)}"
        )
        print("Bundled slack template rendered a chat.postMessage-style payload")

        # Formation-local URL-less transformer: custom shape, trigger URL
        custom_payload = sink.requests_for("/custom-bridge")[0]["json"]
        print(f"Custom bridge received: {custom_payload}")
        assert custom_payload.get("room") == "room-42", f"Context lost: {custom_payload}"
        assert custom_payload.get("sender") == "sender-1", f"Parsed user lost: {custom_payload}"
        custom_reply = custom_payload.get("reply", "")
        assert custom_reply and (
            "4" in custom_reply or "four" in custom_reply.lower()
        ), f"Bad reply: {custom_payload}"
        print("URL-less transformer delivered to the trigger-supplied webhook URL")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  🎉 SUCCESS: Channel template composition works end-to-end")
        print("  ✓ Bundled slack template activated by reference and delivered")
        print("  ✓ Transformer+webhook composition routed to the trigger URL")
        print("  ✓ Platform payload shapes rendered from the parse context")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f"\nUser: {slack_question}")
        print(f"System: {slack_text}")
        print(f"\nUser: {custom_question}")
        print(f"System: {custom_reply}")

        print("\nTest 23A5 PASSED")
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
