#!/usr/bin/env python3
"""
Test 13C1: Trigger with transformer routing

A trigger whose frontmatter declares `transformer: test-sink` must:
1. Parse platform context from the incoming payload (parse: section)
2. Run the agent request to completion
3. Format the response with the transformer body template
4. Deliver it to the transformer endpoint with resolved secret auth

A trigger without frontmatter (test-simple) must behave exactly as before
(passthrough pin, exercised in the same run to prove coexistence).
"""

import asyncio
import sys
from pathlib import Path

import httpx
from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

SINK_PORT = 18299


class SinkServer:
    """Local HTTP sink standing in for a platform API (e.g. Slack)."""

    def __init__(self):
        self.requests = []
        self.runner = None

    async def _handle(self, request: web.Request) -> web.Response:
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "headers": dict(request.headers),
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
    """Test transformer routing plus no-transformer passthrough."""
    print("🚀 MUXI Runtime - Test 13C1: Trigger Transformer Routing")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-triggers"
    sink = SinkServer()

    try:
        # Start the local platform sink first so delivery cannot race it
        await sink.start()
        print(f"📥 Sink server listening on 127.0.0.1:{SINK_PORT}")

        # Load formation
        formation = Formation()
        await formation.load(str(formation_path))

        # Start server
        await formation.start_server(block=False)
        await asyncio.sleep(2)  # Wait for server to be ready

        formation_id = formation.formation_id
        base_url = "http://localhost:18271/v1"
        client_key = "testing-api-key"

        print(f"\n✅ Formation loaded: {formation_id}")
        print(f"📡 Server running at {base_url}")

        # The transformer's bearer token references this formation secret;
        # resolve it here so the assertion checks real secret resolution.
        expected_token = await formation.secrets_manager.get_secret("SKILL_TEST_GREETING")
        assert expected_token, "SKILL_TEST_GREETING secret missing from e2e secrets"

        trigger_message = "What is the capital of France? Answer with the city name."

        # --- Part 1: trigger WITH transformer (async) -----------------------
        print("\n📋 Testing POST /triggers/transformed (async, transformer routing)...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/triggers/transformed",
                headers={"X-Muxi-Client-Key": client_key, "X-Muxi-User-Id": "webhook-caller"},
                json={
                    "data": {
                        "event": {
                            "text": trigger_message,
                            "user": "platform-user-42",
                            "channel": "C-E2E-13C1",
                        }
                    },
                    "use_async": True,
                },
            )

            print(f"   Status: {response.status_code}")
            assert response.status_code == 200, f"Unexpected status: {response.text}"
            ack = response.json()
            request_id = ack["request"]["id"]
            print(f"✅ Async ack received, request ID: {request_id}")

        # Wait for the background request + transformer delivery
        print("\n⏳ Waiting for transformer delivery to the sink...")
        for _ in range(45):
            if sink.requests:
                break
            await asyncio.sleep(1)

        assert sink.requests, "Transformer never delivered to the sink endpoint"
        delivered = sink.requests[0]
        payload = delivered["json"]

        print(f"✅ Sink received {delivered['method']} {delivered['path']}")
        print(f"   Payload: {payload}")

        # Endpoint + method from transformer config
        assert delivered["method"] == "POST", f"Wrong method: {delivered['method']}"
        assert delivered["path"] == "/postMessage", f"Wrong path: {delivered['path']}"

        # Secret-backed bearer auth resolved from formation secrets
        auth_header = delivered["headers"].get("Authorization")
        assert (
            auth_header == f"Bearer {expected_token}"
        ), f"Authorization header not built from secret: {auth_header!r}"
        print("✅ Bearer auth resolved from ${{ secrets.SKILL_TEST_GREETING }}")

        # Context captured by the trigger's parse: section
        assert payload["channel"] == "C-E2E-13C1", f"Context lost: {payload}"
        assert "thread_ts" not in payload, "Absent context value should be dropped, not null"
        print("✅ Parse context routed into the body template")

        # Parsed request values
        assert payload["user"] == "platform-user-42", f"Parsed user_id lost: {payload}"
        assert payload["original"] == trigger_message, f"Parsed message lost: {payload}"
        print("✅ Parsed request values available to the template")

        # Formatted agent response
        agent_text = payload.get("text", "")
        assert agent_text and agent_text.strip(), "Transformed body has no response content"
        assert len(agent_text) <= 500, "content_transform.max_length not applied"
        print(f"✅ Agent response delivered: {agent_text[:80]}...")

        # --- Part 2: trigger WITHOUT transformer (passthrough pin) ----------
        print("\n📋 Testing POST /triggers/test-simple (sync, no transformer)...")
        sink_count_before = len(sink.requests)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/triggers/test-simple",
                headers={"X-Muxi-Client-Key": client_key, "X-Muxi-User-Id": "test-trigger-user"},
                json={"data": {"message": "Passthrough check"}, "use_async": False},
            )
            assert response.status_code == 200, f"Passthrough broken: {response.text}"
            data = response.json()
            content = data["data"].get("message") or data["data"].get("content", "")
            assert content, "Passthrough trigger returned no content"
            print(f"✅ Passthrough response: {str(content)[:80]}...")

        await asyncio.sleep(2)  # Any stray delivery would land within this window
        assert (
            len(sink.requests) == sink_count_before
        ), "Trigger without transformer must not touch transformer endpoints"
        print("✅ No transformer delivery for plain trigger")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  🎉 SUCCESS: Trigger transformer routing works end-to-end")
        print("  ✓ Transformer formatted and delivered the agent response")
        print("  ✓ Secret-backed bearer auth and parse context applied")
        print("  ✓ Trigger without transformer behaves exactly as before")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f"\nUser: {trigger_message}")
        print(f"System: {agent_text}")
        print("\nUser: Test trigger: Passthrough check")
        print(f"System: {content}")

        print("\n✅ Test 13C1 PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if "formation" in locals():
            formation.stop()
        await sink.stop()
        await asyncio.sleep(1)


if __name__ == "__main__":
    success = asyncio.run(main())
    import os

    os._exit(0 if success else 1)
