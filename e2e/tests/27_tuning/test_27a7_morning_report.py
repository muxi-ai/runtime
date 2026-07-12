#!/usr/bin/env python3
"""
Test 27A7: morning report delivery + apply/dismiss widget round-trip.

A tuning pass under auto_apply: false delivers its report to the
formation's declared channel (local sink standing in for the channel
bridge) with the apply/dismiss options widget rendered as native
buttons -- and a button press (the channel's ui_response path) applies
the pending suggestion without any session correlation.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from aiohttp import web
from tuning_common import (
    build_formation,
    chat,
    load_formation,
    plant_tool_failures,
    run_tuning_pass,
    spool_dir_for,
    teardown,
    unique_formation_id,
    wait_for_segments,
)

HAND_WRITTEN = "# Operational learnings\n\n- Keep replies terse.\n"
USER = "morning-report-user"


class Sink:
    """Local aiohttp server standing in for the channel bridge."""

    def __init__(self):
        self.requests = []
        self.runner = None
        self.port = None

    async def _handle(self, request):
        self.requests.append(await request.json())
        return web.Response(status=200)

    async def start(self):
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()


async def main():
    print("MUXI Runtime - Test 27A7: morning report + widget round-trip")
    print("=" * 60)

    formation = None
    sink = None
    formation_id = unique_formation_id("report")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a7-"))
    transcript = []
    try:
        sink = await Sink().start()
        formation_dir = build_formation(
            tmp,
            formation_id,
            muxi_md=HAND_WRITTEN,
            manual_tuning=True,
            proactive_url=f"http://127.0.0.1:{sink.port}/report",
        )
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation_id} (sink on port {sink.port})")

        # 1. Traffic + planted pattern -> pass suggests and reports.
        task = "What is 6 + 1? Digits only."
        reply = await chat(overlord, task, USER, "report-session")
        transcript.append((task, reply))
        print(f"User: {task}\nSystem: {reply}")
        plant_tool_failures(count=30, tool="jira")
        wait_for_segments(spool_dir_for(formation_id))

        result = await run_tuning_pass(overlord)
        print(f"Tuning pass: {result}")
        assert result["muxi_md_suggested"] is True, f"no suggestion was written: {result}"
        assert result["report_delivered"] is True, f"the report was not delivered: {result}"
        suggestion = overlord.muxi_md.read_pending()
        assert suggestion, "PENDING-MUXI.md is missing"

        # 2. The report landed on the declared channel with the widget
        #    rendered as native buttons (P3 template machinery).
        assert sink.requests, "the channel sink received nothing"
        payload = sink.requests[-1]
        print(f"Channel payload:\n{json.dumps(payload, indent=2)[:800]}")
        assert "Tuning report" in payload["text"]
        assert "PENDING-MUXI.md" in payload["text"]
        assert "/learnings apply" in payload["text"], "text fallback instructions are missing"
        buttons = payload["reply_markup"]["inline_keyboard"]
        callbacks = [button["callback_data"] for row in buttons for button in row]
        labels = [button["text"] for row in buttons for button in row]
        assert labels == ["Apply", "Dismiss"], f"unexpected buttons: {labels}"
        widget_id = callbacks[0].split("#")[0]
        assert callbacks == [f"{widget_id}#0", f"{widget_id}#1"]
        print(f"Report delivered with apply/dismiss buttons (widget {widget_id})")

        # 3. A button press rides the ui_response path: the channel posts
        #    the callback data, the runtime decodes it to {id, index},
        #    and the tuning intercept applies the suggestion -- on a
        #    session that never saw the report.
        response = await overlord.chat(
            message="[button press]",
            user_id=USER,
            session_id="a-completely-different-session",
            use_async=False,
            stream=False,
            ui_response={"id": widget_id, "index": 0},
        )
        transcript.append((f"[button press {callbacks[0]}]", response.content))
        print(f"Button press reply: {response.content}")
        assert "Applied" in response.content, f"the press did not apply: {response.content!r}"
        assert overlord.muxi_md.read() == suggestion, "pending was not promoted to live"
        assert overlord.muxi_md.read_pending() is None

        # 4. A stale press after resolution falls through to normal chat
        #    (the widget is gone; the message stands alone).
        response = await overlord.chat(
            message="What is 2 + 2? Digits only.",
            user_id=USER,
            session_id="report-session",
            use_async=False,
            stream=False,
            ui_response={"id": widget_id, "index": 0},
        )
        transcript.append(("stale press + question", response.content))
        print(f"Stale press reply: {response.content}")
        assert "4" in response.content, f"stale press broke the normal turn: {response.content!r}"

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: the morning report works end-to-end")
        print("  - the tuning pass delivered its report to the declared channel")
        print("  - the apply/dismiss widget rendered as native channel buttons")
        print("  - a button press applied the suggestion from an unrelated session")
        print("  - a stale press fell through to a normal chat turn")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        for task, reply in transcript:
            print(f"\nUser: {task}")
            print(f"System: {reply}")

        print("\nTest 27A7 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if formation is not None:
            await teardown(formation, formation_id)
        if sink is not None:
            await sink.stop()
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
