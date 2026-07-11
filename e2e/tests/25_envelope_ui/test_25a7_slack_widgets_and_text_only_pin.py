#!/usr/bin/env python3
"""
Test 25A7: Response Envelope UI - Slack Block Kit rendering + text-only zero-change pin (P3)

Verifies the remaining P3 channel guarantees:

1. Slack variant: a ui-bearing response delivered through the bundled
   slack transformer renders Block Kit blocks -- a section carrying the
   complete text (Slack renders blocks INSTEAD of top-level text) plus
   an actions block of buttons -- while the top-level `text` fallback
   still ships.
2. Zero-change pin: the same ui-bearing response delivered through a
   plain text-only formation-local template produces a payload with
   exactly the template's keys -- widgets never leak into templates
   that do not reference them.
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

SINK_PORT = 18254
SERVER_PORT = 18253
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}/v1"
HEADERS = {"X-Muxi-Client-Key": "envelope-client-key", "X-Muxi-User-Id": "slack-bridge"}

SLACK_USER = "u25a7"  # parse coerces and the runtime lowercases user ids
PLAIN_USER = "plain-user-25a7"


class SinkServer:
    """Local HTTP sink standing in for the developer's channel bridges."""

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


async def wait_for(predicate, timeout=90):
    for _ in range(timeout):
        if predicate():
            return True
        await asyncio.sleep(1)
    return predicate()


async def clear_github_credentials(formation, user_id: str) -> None:
    """Idempotency across runs: remove previously seeded credentials via SQL."""
    from sqlalchemy import text

    async with formation._db_manager.get_async_session() as session:
        await session.execute(
            text(
                "DELETE FROM credentials WHERE service = 'github' AND user_id IN "
                "(SELECT user_id FROM user_identifiers WHERE identifier = :uid)"
            ),
            {"uid": user_id},
        )
        await session.commit()


async def seed_two_accounts(formation, overlord, user_id: str) -> None:
    """Seed exactly two named GitHub credentials so the choice is enumerable."""
    await clear_github_credentials(formation, user_id)
    for name, token in (("acme-prod", f"fake-prod-{user_id}"), ("acme-dev", f"fake-dev-{user_id}")):
        await overlord.credential_resolver.store_credential(
            user_id=user_id,
            service="github",
            credentials={"token": token},
            credential_name=name,
        )
    overlord.credential_resolver._cache.clear()


async def main() -> int:
    print("MUXI Runtime - Test 25A7: Slack Block Kit rendering + text-only zero-change pin")
    print("=" * 70)

    formation_path = Path(__file__).parent / "formations" / "formation-envelope-channels"
    sink = SinkServer()
    formation = Formation()

    try:
        await sink.start()
        print(f"Bridge sink listening on 127.0.0.1:{SINK_PORT}")

        await formation.load(str(formation_path))
        await formation.start_server(block=False)
        await asyncio.sleep(2)
        overlord = formation._overlord

        async with httpx.AsyncClient(timeout=60.0) as client:
            # ---------------------------------------------------------------
            # [1] Slack variant: options widget -> Block Kit blocks
            # ---------------------------------------------------------------
            await seed_two_accounts(formation, overlord, SLACK_USER)
            print("\n[1] POST /triggers/slack (account-ambiguous question)...")
            response = await client.post(
                f"{BASE_URL}/triggers/slack",
                headers=HEADERS,
                json={
                    "data": {
                        "event": {
                            "text": "List my GitHub repositories",
                            "user": SLACK_USER,
                            "channel": "C25A7",
                        }
                    },
                    "session_id": "sess-25a7-slack",
                    "use_async": True,
                },
            )
            assert response.status_code == 200, f"Trigger failed: {response.text[:300]}"

            print("    Waiting for the clarification delivery to the bridge sink...")
            assert await wait_for(
                lambda: sink.requests_for("/slack-bridge")
            ), f"No delivery; sink saw: {[r['path'] for r in sink.requests]}"
            payload = sink.requests_for("/slack-bridge")[0]["json"]
            print(f"    Slack payload: {str(payload)[:400]}")

            # Top-level text fallback stays (Slack notification fallback)
            text_body = payload.get("text", "")
            assert text_body, f"Text body missing: {payload}"
            assert "acme-prod" in text_body and "acme-dev" in text_body, (
                "Text fallback must list the choices in prose; got: " + text_body[:300]
            )
            assert payload.get("channel") == "C25A7", payload
            assert set(payload.keys()) <= {
                "channel",
                "thread_ts",
                "text",
                "blocks",
            }, f"Unexpected keys in Slack payload: {sorted(payload)}"

            # Blocks: section carrying the text, then the buttons
            blocks = payload.get("blocks")
            assert blocks, f"Expected Block Kit blocks, got: {payload}"
            assert blocks[0]["type"] == "section", blocks[0]
            assert blocks[0]["text"]["text"] == text_body, (
                "The section block must carry the complete text (Slack renders "
                "blocks INSTEAD of top-level text)"
            )
            actions = next(b for b in blocks[1:] if b["type"] == "actions")
            labels = [e["text"]["text"] for e in actions["elements"]]
            assert any("prod" in label for label in labels), f"Options missing: {labels}"
            assert any("dev" in label for label in labels), f"Options missing: {labels}"
            for element in actions["elements"]:
                value = element.get("value", "")
                assert value.startswith("ui_") and "#" in value, f"Bad button value: {element}"
            print(f"    Block Kit buttons rendered: {labels}")

            # ---------------------------------------------------------------
            # [2] Zero-change pin: text-only template + ui-bearing response
            # ---------------------------------------------------------------
            await seed_two_accounts(formation, overlord, PLAIN_USER)
            print("\n[2] POST /triggers/plain (same ambiguity, text-only template)...")
            response = await client.post(
                f"{BASE_URL}/triggers/plain",
                headers=HEADERS,
                json={
                    "data": {
                        "payload": {
                            "text": "List my GitHub repositories",
                            "sender": PLAIN_USER,
                            "room": "room-25a7",
                        }
                    },
                    "session_id": "sess-25a7-plain",
                    "use_async": True,
                },
            )
            assert response.status_code == 200, f"Trigger failed: {response.text[:300]}"

            print("    Waiting for the text-only delivery...")
            assert await wait_for(
                lambda: sink.requests_for("/plain-bridge")
            ), f"No delivery; sink saw: {[r['path'] for r in sink.requests]}"
            plain_payload = sink.requests_for("/plain-bridge")[0]["json"]
            print(f"    Plain payload: {str(plain_payload)[:400]}")

            # Exactly the template's keys: the ui-bearing response changed
            # NOTHING about a template that references no widgets.
            assert set(plain_payload.keys()) == {
                "room",
                "reply",
            }, f"Widgets leaked into a text-only template: {sorted(plain_payload)}"
            assert plain_payload["room"] == "room-25a7", plain_payload
            reply = plain_payload["reply"]
            assert "acme-prod" in reply and "acme-dev" in reply, (
                "Text-only delivery must still carry the complete prose fallback: " + reply[:300]
            )
            print("    Text-only payload shape unchanged (no widget keys)")

        print("\n" + "=" * 70)
        print("SUCCESS: Slack blocks rendered additively with the text intact and")
        print("         the text-only template delivery stayed widget-free")
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
