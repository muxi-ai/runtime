#!/usr/bin/env python3
"""
Test 25A6: Response Envelope UI - Telegram widget rendering + callback round trip (P3)

Verifies the two P3 mechanisms for Telegram end to end:

1. Outbound: a trigger response carrying an `options` widget, delivered
   through the bundled telegram transformer, renders a native
   inline_keyboard (labels + `<widget_id>#<index>` callback data) while
   the complete text body still ships (widgets are additive).
2. Inbound: a simulated callback_query POSTed to the callback trigger
   route is decoded by `parse.ui_response` into the {id, index} reply
   hint, rides the chat re-entry, and pins the selection
   deterministically (the message text alone could never resolve it).
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
HEADERS = {"X-Muxi-Client-Key": "envelope-client-key", "X-Muxi-User-Id": "telegram-bridge"}

TELEGRAM_USER = "777001"  # str(message.from.id) after parse coercion
TELEGRAM_CHAT = 424242
SESSION_ID = "sess-25a6-telegram"


class SinkServer:
    """Local HTTP sink standing in for the developer's Telegram bridge."""

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

    def bridge_requests(self):
        return [r for r in self.requests if r["path"] == "/telegram-bridge"]


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


def cached_github_credential(user_id: str):
    """Return the MCP-cached credential auth for the user (set on selection)."""
    from muxi.runtime.services.mcp.service import MCPService

    mcp_svc = MCPService.get_instance()
    if not mcp_svc:
        return None
    for server_id, per_user in (mcp_svc.user_credentials or {}).items():
        if "github" in server_id.lower() and user_id in per_user:
            return per_user[user_id]
    return None


async def main() -> int:
    print("MUXI Runtime - Test 25A6: Telegram widget rendering + callback round trip")
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

        await seed_two_accounts(formation, overlord, TELEGRAM_USER)
        print(f"Seeded two GitHub accounts for user {TELEGRAM_USER}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # ---------------------------------------------------------------
            # [1] Outbound: options widget -> native inline keyboard
            # ---------------------------------------------------------------
            print("\n[1] POST /triggers/telegram (account-ambiguous question)...")
            response = await client.post(
                f"{BASE_URL}/triggers/telegram",
                headers=HEADERS,
                json={
                    "data": {
                        "message": {
                            "text": "List my GitHub repositories",
                            "from": {"id": int(TELEGRAM_USER)},
                            "chat": {"id": TELEGRAM_CHAT},
                        }
                    },
                    "session_id": SESSION_ID,
                    "use_async": True,
                },
            )
            assert response.status_code == 200, f"Trigger failed: {response.text[:300]}"

            print("    Waiting for the clarification delivery to the bridge sink...")
            assert await wait_for(
                lambda: sink.bridge_requests()
            ), f"No delivery; sink saw: {[r['path'] for r in sink.requests]}"
            payload = sink.bridge_requests()[0]["json"]
            print(f"    Telegram payload: {str(payload)[:400]}")

            # Text always ships and is self-sufficient (lists both accounts)
            text_body = payload.get("text", "")
            assert text_body, f"Text body missing: {payload}"
            assert "acme-prod" in text_body and "acme-dev" in text_body, (
                "Text fallback must list the choices in prose; got: " + text_body[:300]
            )
            assert str(payload.get("chat_id")) == str(TELEGRAM_CHAT), payload

            # Widgets are additive: native inline keyboard alongside the text
            markup = payload.get("reply_markup")
            assert markup and markup.get(
                "inline_keyboard"
            ), f"Expected inline_keyboard, got: {payload}"
            buttons = [b for row in markup["inline_keyboard"] for b in row]
            labels = [b.get("text", "") for b in buttons]
            assert any("prod" in label for label in labels), f"Options missing: {labels}"
            assert any("dev" in label for label in labels), f"Options missing: {labels}"
            for button in buttons:
                data = button.get("callback_data", "")
                assert data.startswith("ui_") and "#" in data, f"Bad callback data: {button}"
                assert len(data.encode("utf-8")) <= 64, f"callback_data over 64 bytes: {data}"
            print(f"    Inline keyboard rendered: {labels}")

            # ---------------------------------------------------------------
            # [2] Inbound: callback_query -> deterministic pinning
            # ---------------------------------------------------------------
            dev_button = next(b for b in buttons if "dev" in b.get("text", ""))
            print(f"\n[2] POST /triggers/telegram-callback (pressing {dev_button['text']!r})...")
            response = await client.post(
                f"{BASE_URL}/triggers/telegram-callback",
                headers=HEADERS,
                json={
                    "data": {
                        "callback_query": {
                            "from": {"id": int(TELEGRAM_USER)},
                            "data": dev_button["callback_data"],
                            "message": {"chat": {"id": TELEGRAM_CHAT}},
                        }
                    },
                    "session_id": SESSION_ID,
                    "use_async": True,
                },
            )
            assert response.status_code == 200, f"Callback trigger failed: {response.text[:300]}"

            print("    Waiting for the post-pin reply delivery...")
            assert await wait_for(
                lambda: len(sink.bridge_requests()) >= 2
            ), "No reply delivery after the button press"

            cached = cached_github_credential(TELEGRAM_USER)
            assert cached is not None, "Expected the pinned credential to be cached for the user"
            import json as json_lib

            cached_str = json_lib.dumps(cached)
            assert (
                f"fake-dev-{TELEGRAM_USER}" in cached_str
            ), f"Expected acme-dev pinned deterministically, cached={cached_str[:200]}"
            print("    Button press pinned 'acme-dev' deterministically (credential cached)")

        print("\n" + "=" * 70)
        print("SUCCESS: inline keyboard rendered additively and the callback_query")
        print("         round-tripped into deterministic ui_response pinning")
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
