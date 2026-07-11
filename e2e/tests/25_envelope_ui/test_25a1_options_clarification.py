#!/usr/bin/env python3
"""
Test 25A1: Response Envelope UI - options widget + reply path

Verifies the P1 clarification producer and the ui_response reply path:
1. Enumerable clarification (two GitHub accounts) -> the envelope carries an
   `options` widget AND self-sufficient text listing the same choices
2. Reply WITH ui_response {id, value} -> the selection is pinned
   deterministically (the message text alone could never resolve it)
3. Reply with plain text naming the account -> same outcome (hint optional)
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

USER_A = "envelope-user-a"  # ui_response scenario
USER_B = "envelope-user-b"  # plain-text scenario


async def clear_github_credentials(formation, user_id: str) -> None:
    """Idempotency across runs: remove previously seeded credentials via SQL
    (delete_credential expects a single row; seeded users may have several)."""
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
    # Drop the resolver cache so the freshly seeded pair is visible
    overlord.credential_resolver._cache.clear()


def find_options_widget(response):
    for widget in getattr(response, "ui", None) or []:
        if widget.get("type") == "options":
            return widget
    return None


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


async def run_clarification(overlord, user_id: str, session_id: str):
    response = await overlord.chat(
        message="List my GitHub repositories",
        user_id=user_id,
        session_id=session_id,
        stream=False,
    )
    return response


async def main() -> int:
    print("MUXI Runtime - Test 25A1: options widget + ui_response reply path")
    print("=" * 70)

    formation_path = Path(__file__).parent / "formations" / "formation-envelope"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    await asyncio.sleep(2)  # Give MCP servers time to initialize

    try:
        # ---------------------------------------------------------------
        # Scenario A: options widget + deterministic ui_response pinning
        # ---------------------------------------------------------------
        await seed_two_accounts(formation, overlord, USER_A)

        print("\n[A1] Asking an account-ambiguous question...")
        response = await overlord.chat(
            message="List my GitHub repositories",
            user_id=USER_A,
            session_id="sess-25a1-a",
            stream=False,
        )
        content = response.content if hasattr(response, "content") else str(response)
        print(f"     Response: {content[:200]}")

        widget = find_options_widget(response)
        assert (
            widget is not None
        ), f"Expected an options widget, got ui={getattr(response, 'ui', None)}"
        values = [o["value"] for o in widget["options"]]
        assert "acme-prod" in values and "acme-dev" in values, f"Unexpected options: {values}"
        assert widget["id"].startswith("ui_"), widget
        assert widget["multi"] is False, widget
        print(f"     Options widget present: id={widget['id']} values={values}")

        # Self-sufficient text: the same choices must be listed in prose
        assert "acme-prod" in content and "acme-dev" in content, (
            "Text fallback must list the choices in prose; got: " + content[:300]
        )
        print("     Text fallback lists both accounts (self-sufficient)")

        # Reply with a message that CANNOT be resolved from text alone —
        # only the ui_response hint can pin the selection.
        print("\n[A2] Replying with ui_response hint (message text is unresolvable)...")
        await overlord.chat(
            message="use that one",
            user_id=USER_A,
            session_id="sess-25a1-a",
            stream=False,
            ui_response={"id": widget["id"], "value": "acme-dev"},
        )

        cached = cached_github_credential(USER_A)
        assert cached is not None, "Expected the pinned credential to be cached for the user"
        import json as json_lib

        cached_str = json_lib.dumps(cached)
        assert (
            f"fake-dev-{USER_A}" in cached_str
        ), f"Expected acme-dev credential pinned deterministically, cached={cached_str[:200]}"
        print("     ui_response pinned 'acme-dev' deterministically (credential cached)")

        # ---------------------------------------------------------------
        # Scenario B: plain-text reply -> same outcome (hint is optional)
        # ---------------------------------------------------------------
        await seed_two_accounts(formation, overlord, USER_B)

        print("\n[B1] Same clarification for a second user...")
        response_b = await overlord.chat(
            message="List my GitHub repositories",
            user_id=USER_B,
            session_id="sess-25a1-b",
            stream=False,
        )
        widget_b = find_options_widget(response_b)
        assert (
            widget_b is not None
        ), f"Expected an options widget, got ui={getattr(response_b, 'ui', None)}"

        print("[B2] Replying with plain text (no ui_response)...")
        await overlord.chat(
            message="acme-dev",
            user_id=USER_B,
            session_id="sess-25a1-b",
            stream=False,
        )

        cached_b = cached_github_credential(USER_B)
        assert cached_b is not None, "Expected the text-selected credential to be cached"
        import json as json_lib2

        assert f"fake-dev-{USER_B}" in json_lib2.dumps(
            cached_b
        ), "Plain-text reply must reach the same outcome as the ui_response hint"
        print("     Plain-text reply selected the same account (identical outcome)")

        print("\n" + "=" * 70)
        print("SUCCESS: options widget emitted, ui_response pinned deterministically,")
        print("         plain-text reply reached the identical outcome")
        return 0

    finally:
        try:
            await formation.stop_overlord()
            formation.stop()
        except Exception:
            pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    os._exit(exit_code)
