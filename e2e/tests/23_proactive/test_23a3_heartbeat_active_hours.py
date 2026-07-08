#!/usr/bin/env python3
"""
Test 23A3: Heartbeat firing inside active hours / suppressed outside

Loads a formation with `proactive.heartbeat` (scheduler-backed) and
verifies, with fixed reference times against the formation's 09:00-18:00
UTC window:
1. The heartbeat registered with the scheduler's periodic-task loop
   (no second scheduler)
2. run_once at 12:00 UTC runs the heartbeat SOP through the agent and
   delivers the report to the user's last channel via its transformer
3. run_once at 23:00 UTC is suppressed by active hours (no agent call,
   no delivery)
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

SINK_PORT = 18239

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
    print("MUXI Runtime - Test 23A3: Heartbeat Active Hours")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-proactive"
    sink = SinkServer()

    try:
        await sink.start()

        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print(f"Formation loaded: {formation.formation_id}")

        heartbeat = overlord.heartbeat_service
        assert heartbeat is not None, "Heartbeat service not initialized"

        # 1. Heartbeat rides the existing scheduler loop
        assert overlord.scheduler_service is not None, "Scheduler not running"
        assert (
            heartbeat in overlord.scheduler_service._periodic_tasks
        ), "Heartbeat not registered with the scheduler's periodic tasks"
        print("Heartbeat registered with the scheduler's worker loop")

        # Give the user a last channel so target: last resolves
        await overlord.record_inbound_channel("heartbeat-user", "chan-b", {"room": "ROOM-HB"})

        # 2. Inside active hours: heartbeat runs and delivers
        print(f"\nrun_once at {INSIDE_HOURS.isoformat()} (inside 09:00-18:00 UTC)...")
        notified = await heartbeat.run_once(INSIDE_HOURS)
        assert notified == ["heartbeat-user"], f"Heartbeat did not notify: {notified}"

        assert len(sink.requests) == 1, f"Expected 1 delivery, got {sink.requests}"
        delivered = sink.requests[0]
        assert delivered["path"] == "/b", f"Heartbeat ignored 'last' channel: {delivered}"
        report_text = delivered["json"]["text"]
        assert report_text.strip(), "Heartbeat delivered empty content"
        assert delivered["json"]["room"] == "ROOM-HB", delivered
        print(f"Heartbeat delivered to chan-b: {report_text[:60]}")

        # 3. Outside active hours: suppressed before any agent work
        print(f"\nrun_once at {OUTSIDE_HOURS.isoformat()} (outside window)...")
        notified = await heartbeat.run_once(OUTSIDE_HOURS)
        assert notified == [], f"Heartbeat fired outside active hours: {notified}"
        await asyncio.sleep(1)
        assert len(sink.requests) == 1, f"Suppressed heartbeat still delivered: {sink.requests[1:]}"
        print("Heartbeat suppressed outside active hours (no delivery)")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: Heartbeat active-hours gating works end-to-end")
        print("  - Heartbeat registered on the scheduler loop (no second loop)")
        print("  - Fired inside active hours and delivered to the last channel")
        print("  - Suppressed outside active hours")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: (heartbeat SOP) respond with exactly E2E-HEARTBEAT-PING")
        print(f"System: {report_text}")

        print("\nTest 23A3 PASSED")
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
