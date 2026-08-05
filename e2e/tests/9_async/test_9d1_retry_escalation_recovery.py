#!/usr/bin/env python3
"""Test 9d1: Async retry escalation -- sync failure escalates, retry succeeds.

Flow under test (PRD: async-retry-escalation):
1. A sync chat turn fails terminally: the request decomposes into a
   workflow whose only tool (system_status_report) stalls past the
   formation's task_timeout -- deterministic failure injection via a
   control file, no randomness.
2. The waiting caller receives the fixed escalation message ("This has
   failed. I'm going to retry...") with ``escalated: true`` + request_id
   in the envelope metadata, and the tracker entry stays PROCESSING with
   the escalated marker.
3. The test "recovers" the tool (creates the control file); the
   background attempt replans, executes, succeeds, and the tracker ends
   COMPLETED.
4. The terminal webhook lands on a local HTTP sink run by this test:
   payload {request_id, state, result, attempts, timestamp} with a valid
   HMAC-SHA256 signature over the raw body, verifiable with the
   formation's client key.

All assertions are structural/deterministic -- no LLM-judged checks.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

# Run from the area directory regardless of how the script was invoked
# (the formation's MCP server config uses area-relative paths).
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiohttp import web  # noqa: E402
from common.base import BaseE2ETest  # noqa: E402

CONTROL_FLAG = Path("/tmp/muxi_e2e_retry_escalation.flag")
SINK_PORT = 8766


class WebhookSink:
    """Tiny local HTTP sink capturing raw webhook bodies + headers."""

    def __init__(self, port: int = SINK_PORT):
        self.port = port
        self.received = []
        self._runner = None

    async def start(self):
        async def handle(request):
            body = await request.read()
            self.received.append({"headers": dict(request.headers), "body": body})
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_post("/{tail:.*}", handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()


def verify_signature(entry, client_key: str) -> bool:
    """Verify X-Muxi-Signature (t=<ts>,v1=<hex>) over '{ts}.{raw body}'."""
    signature_header = entry["headers"].get("X-Muxi-Signature", "")
    parts = dict(item.split("=", 1) for item in signature_header.split(",") if "=" in item)
    if "t" not in parts or "v1" not in parts:
        return False
    message = f"{parts['t']}.".encode() + entry["body"]
    expected = hmac.new(client_key.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(parts["v1"], expected)


async def run_test(test: BaseE2ETest) -> bool:
    checks = []

    def check(name: str, passed: bool, detail: str = ""):
        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] {name}" + (f" -- {detail}" if detail else ""), flush=True)
        checks.append(passed)
        return passed

    CONTROL_FLAG.unlink(missing_ok=True)
    sink = WebhookSink()
    await sink.start()

    try:
        formation_path = Path(__file__).parent / "formations" / "formation-retry-escalation"
        await test.setup_formation(formation_path=str(formation_path))
        overlord = test.overlord

        # --- 1. Sync attempt fails terminally and escalates -------------
        print("Step 1: sync turn (tool stalled -> deterministic failure)", flush=True)
        response = await overlord.chat(
            message=(
                "Please fetch the current system status report with your status "
                "report tool, then write a two-line summary of its contents "
                "and note whether all services are operational."
            ),
            user_id="e2e",
            session_id="sess_9d1",
            webhook_url=f"http://127.0.0.1:{SINK_PORT}/retry-hook",
            stream=False,
        )

        content = getattr(response, "content", str(response))
        metadata = getattr(response, "metadata", None) or {}
        request_id = metadata.get("request_id")

        check(
            "escalation message delivered to waiting caller",
            isinstance(content, str) and content.startswith("This has failed."),
            content[:120],
        )
        check("envelope carries escalated: true", metadata.get("escalated") is True)
        check("envelope carries request_id", bool(request_id), str(request_id))
        if not request_id:
            return False

        status = await overlord.get_request_status(request_id)
        check(
            "tracker stays PROCESSING while the chain runs",
            status.get("status") == "processing",
            str(status),
        )
        state = await overlord.request_tracker.get_request(request_id)
        check("tracker entry carries the escalated marker", bool(state and state.escalated))

        # --- 2. Recover the tool; background attempt succeeds -----------
        print("Step 2: recover the tool; wait for the background retry", flush=True)
        CONTROL_FLAG.write_text("recovered")

        final_status = None
        deadline = time.time() + 180
        while time.time() < deadline:
            status = await overlord.get_request_status(request_id)
            if status.get("status") in ("completed", "failed", "cancelled"):
                final_status = status.get("status")
                break
            await asyncio.sleep(2)

        check("chain reached a terminal state", final_status is not None, str(final_status))
        check("chain terminal is COMPLETED (achieved)", final_status == "completed")

        state = await overlord.request_tracker.get_request(request_id)
        result_text = str(getattr(state, "result", "") or "")
        check("tracker carries the retry result", bool(result_text), result_text[:120])

        # --- 3. Webhook delivery with valid HMAC ------------------------
        print("Step 3: verify the terminal webhook on the local sink", flush=True)
        deadline = time.time() + 30
        while time.time() < deadline and not sink.received:
            await asyncio.sleep(1)

        if not check("webhook received by local sink", bool(sink.received)):
            return all(checks)

        entry = sink.received[0]
        payload = json.loads(entry["body"])
        check("webhook payload request_id matches", payload.get("request_id") == request_id)
        check("webhook payload state is 'achieved'", payload.get("state") == "achieved")
        check("webhook payload carries the result", bool(payload.get("result")))
        check(
            "webhook payload counts attempts (sync + async)",
            isinstance(payload.get("attempts"), int) and payload["attempts"] >= 2,
            str(payload.get("attempts")),
        )
        check("webhook payload carries a timestamp", "timestamp" in payload)
        check(
            "HMAC signature verifies with the formation client key",
            verify_signature(entry, overlord.client_api_key),
        )

        return all(checks)
    finally:
        CONTROL_FLAG.unlink(missing_ok=True)
        await sink.stop()
        await test.cleanup_formation()


def main():
    test = BaseE2ETest(
        "9d1_retry_escalation_recovery",
        "Sync failure escalates to async retry; background attempt succeeds; webhook verified",
        "9_async",
    )
    success = asyncio.run(run_test(test))
    print("=" * 70, flush=True)
    if success:
        print("Test 9d1 PASSED", flush=True)
        print("SUCCESS", flush=True)
        os._exit(0)
    print("Test 9d1 FAILED", flush=True)
    os._exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Test 9d1 crashed: {e}", flush=True)
        import traceback

        traceback.print_exc()
        os._exit(1)
