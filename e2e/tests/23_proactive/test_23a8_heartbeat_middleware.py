#!/usr/bin/env python3
"""
Test 23A8: Heartbeat traverses the request middleware + RBAC pipeline

Internally-originated requests resolve groups through the exact same
pipeline as external traffic (request-middleware PRD). The formation
declares a stdio middleware that audits every call (route_class + user)
and attaches groups from a static map:

1. A mapped user's heartbeat runs: the middleware log shows a
   ``heartbeat`` route_class call for it, the request proceeds with the
   middleware-attached groups, and the report is delivered
2. An UN-mapped user's heartbeat is rejected by RBAC (fallback: false)
   -- the middleware log shows the call happened, but nothing is
   delivered and the failure is isolated per user
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

SINK_PORT = 18240
FORMATION_DIR = Path(__file__).parent / "formation-heartbeat-middleware"
CALLS_LOG = FORMATION_DIR / "middleware_calls.log"

RUN_AT = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)

MAPPED_USER = "heartbeat-user"  # in the middleware's map -> group "staff"
UNMAPPED_USER = "ghost-user"  # not in the map -> rejected (fallback: false)


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
    print("MUXI Runtime - Test 23A8: Heartbeat via Request Middleware")
    print("=" * 60)

    formation_path = FORMATION_DIR
    sink = SinkServer()
    CALLS_LOG.unlink(missing_ok=True)

    try:
        await sink.start()

        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print(f"Formation loaded: {formation.formation_id}")

        assert formation.request_middleware is not None, "middleware not constructed"
        assert formation.permission_resolver is not None, "resolver not constructed"
        print("Middleware connected; RBAC active with fallback: false")

        heartbeat = overlord.heartbeat_service
        assert heartbeat is not None, "Heartbeat service not initialized"

        # Hermetic setup: clear persisted channel state, then seed both
        # users with a last channel so the heartbeat runs for exactly them.
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

        await overlord.record_inbound_channel(MAPPED_USER, "chan-b", {"room": "ROOM-HB"})
        await overlord.record_inbound_channel(UNMAPPED_USER, "chan-b", {"room": "ROOM-GHOST"})
        print(f"Seeded channel state for {MAPPED_USER} and {UNMAPPED_USER}")

        # Run one heartbeat pass over both users
        print(f"\nrun_once at {RUN_AT.isoformat()}...")
        notified = await heartbeat.run_once(RUN_AT)

        # 1. The mapped user's heartbeat ran and delivered
        assert notified == [MAPPED_USER], f"Expected only {MAPPED_USER} notified: {notified}"
        assert len(sink.requests) == 1, f"Expected 1 delivery, got {sink.requests}"
        report_text = sink.requests[0]["json"]["text"]
        assert report_text.strip(), "Heartbeat delivered empty content"
        print(f"Mapped user's heartbeat delivered: {report_text[:60]}")

        # 2. Both heartbeats traversed the middleware with route_class
        #    "heartbeat" -- the un-mapped one was then rejected by RBAC
        calls = CALLS_LOG.read_text().strip().splitlines()
        heartbeat_calls = [line for line in calls if line.startswith("heartbeat ")]
        called_users = {line.split(" ", 1)[1] for line in heartbeat_calls}
        assert MAPPED_USER in called_users, f"middleware never saw {MAPPED_USER}: {calls}"
        assert UNMAPPED_USER in called_users, f"middleware never saw {UNMAPPED_USER}: {calls}"
        print(f"Middleware audited {len(heartbeat_calls)} heartbeat call(s): {called_users}")

        # 3. The un-mapped user produced no delivery (rejected fail-closed)
        assert all(
            r["json"].get("room") != "ROOM-GHOST" for r in sink.requests
        ), f"Rejected user's heartbeat was delivered: {sink.requests}"
        print("Un-mapped user's heartbeat rejected by RBAC (no delivery)")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: Heartbeat traverses the middleware + RBAC pipeline")
        print("  - Both heartbeats hit the middleware with route_class 'heartbeat'")
        print("  - Mapped user proceeded with middleware-attached groups and delivered")
        print("  - Un-mapped user rejected (fallback: false), isolated per user")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: (heartbeat SOP) respond with exactly E2E-HEARTBEAT-PING")
        print(f"System: {report_text}")

        print("\nTest 23A8 PASSED")
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
        CALLS_LOG.unlink(missing_ok=True)
        await asyncio.sleep(1)


if __name__ == "__main__":
    success = asyncio.run(main())
    import os

    os._exit(0 if success else 1)
