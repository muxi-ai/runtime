#!/usr/bin/env python3
"""
Test 23A7: Default heartbeat SOP fallback (Proactiveness Phase 4)

Loads a dedicated formation (formation-heartbeat-default) whose heartbeat
is enabled with NO `sop:` and NO `instruction:`, and verifies with the
real agent pipeline:
1. Config parsing accepts the sop-less heartbeat (no relaxation needed;
   sop/instruction were always optional) and the bundled default
   heartbeat SOP (formation/proactive/builtin/heartbeat.md) becomes the
   prompt
2. A real heartbeat run under the default SOP wakes the agent; nothing
   needs the user's attention, so the agent follows the bundled SOP's
   reply rule (HEARTBEAT_OK) and the suppression keeps the channel silent
3. Active-hours gating still applies around the default SOP

The formation deliberately has no formation SOPs: semantic SOP matching
would otherwise be free to hijack the generic wake-up prompt (the shared
proactive formation's `ping` SOP does exactly that). Override precedence
(formation `sop:` wins over the bundled default) is pinned by unit tests
in tests/unit/test_heartbeat.py::TestPromptResolution.
"""

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402
from muxi.runtime.formation.proactive import load_default_heartbeat_sop  # noqa: E402
from muxi.runtime.formation.proactive.heartbeat import (  # noqa: E402
    BUILTIN_HEARTBEAT_SOP_PATH,
)

SINK_PORT = 18242

INSIDE_HOURS = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)  # Wednesday noon UTC
OUTSIDE_HOURS = datetime(2026, 7, 8, 23, 0, tzinfo=timezone.utc)  # Wednesday night UTC


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
    print("MUXI Runtime - Test 23A7: Default Heartbeat SOP")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-heartbeat-default"
    sink = SinkServer()

    try:
        await sink.start()

        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print(f"Formation loaded: {formation.formation_id}")

        heartbeat = overlord.heartbeat_service
        assert heartbeat is not None, "Heartbeat service not initialized"

        # 1. Heartbeat enabled with no sop:/instruction: resolves to the
        #    bundled default SOP shipped with the runtime
        assert heartbeat.config.sop is None, heartbeat.config.sop
        assert heartbeat.config.instruction is None, heartbeat.config.instruction
        assert BUILTIN_HEARTBEAT_SOP_PATH.is_file(), "Bundled heartbeat SOP missing"
        default_sop = load_default_heartbeat_sop()
        assert "HEARTBEAT_OK" in default_sop, "Bundled SOP lacks the suppression sentinel"
        prompt = heartbeat._build_prompt()
        assert prompt == default_sop, "Heartbeat prompt is not the bundled default SOP"
        assert "## Your Task" in prompt
        print("No `sop:` configured: bundled default SOP drives the heartbeat")

        # Hermetic setup: clear persisted channel state left by earlier
        # runs so known_users() is exactly the user seeded below. Scheduler
        # jobs left by other areas in the shared e2e database no longer
        # need cleanup here: the due-job queries are formation scoped.
        store = overlord.user_channel_store
        if store._async_session_maker is not None:
            from sqlalchemy import delete  # noqa: E402

            from muxi.runtime.formation.proactive.user_channels import (  # noqa: E402
                UserChannelState,
            )

            async with store._async_session_maker() as session:
                await session.execute(
                    delete(UserChannelState).where(
                        UserChannelState.formation_id == store.formation_id
                    )
                )
                await session.commit()
        store._states.clear()
        store._loaded.clear()
        print("Cleared persisted channel state for a hermetic run")

        # Fresh user id per run: channel state and per-user memory persist
        # in the shared e2e database, and stale memories from earlier runs
        # would leak into the heartbeat context (same convention as 23A6).
        user_id = f"hb-default-{uuid.uuid4().hex[:8]}"
        await overlord.record_inbound_channel(user_id, "chan-a", {"room": "ROOM-DS"})

        # 2. Real run under the default SOP: nothing needs this user's
        #    attention, so the agent must follow the bundled SOP's reply
        #    rule (HEARTBEAT_OK) and the suppression must keep the
        #    channel silent.
        print(f"\nrun_once at {INSIDE_HOURS.isoformat()} (inside 09:00-18:00 UTC)...")
        notified = await heartbeat.run_once(INSIDE_HOURS)
        await asyncio.sleep(1)
        assert notified == [], (
            f"Default-SOP heartbeat was not suppressed: {notified}; "
            f"delivered payloads: {sink.requests}"
        )
        assert sink.requests == [], f"Suppressed heartbeat still delivered: {sink.requests}"
        print("Agent woke under the default SOP, replied HEARTBEAT_OK, nothing delivered")

        # 3. Active hours still gate the default-SOP heartbeat
        print(f"\nrun_once at {OUTSIDE_HOURS.isoformat()} (outside window)...")
        notified = await heartbeat.run_once(OUTSIDE_HOURS)
        assert notified == [], f"Heartbeat fired outside active hours: {notified}"
        assert sink.requests == [], f"Delivery outside active hours: {sink.requests}"
        print("Heartbeat suppressed outside active hours")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: Default heartbeat SOP fallback works end-to-end")
        print("  - Heartbeat enabled without `sop:` uses the bundled SOP")
        print("  - HEARTBEAT_OK suppression works under the default SOP")
        print("  - Active-hours gating unchanged")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f"\nUser: (bundled default heartbeat SOP) {prompt.splitlines()[0]}")
        print("System: HEARTBEAT_OK (suppressed, not delivered)")

        print("\nTest 23A7 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if "formation" in locals():
            try:
                await formation.stop_overlord()
            except Exception:
                pass
        await sink.stop()
        await asyncio.sleep(1)


if __name__ == "__main__":
    success = asyncio.run(main())
    import os

    os._exit(0 if success else 1)
