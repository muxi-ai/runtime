#!/usr/bin/env python3
"""
Test 25A4: Response Envelope UI - no-widget regression pin (CRITICAL)

The zero-behavior-change discipline: responses without widgets must be
byte-identical to the pre-feature envelope, over the real HTTP surface.

1. POST /v1/chat (stream=false): data.message carries exactly the
   pre-feature key set {role, content, artifacts, metadata} — no `ui`
   key anywhere in the response
2. POST /v1/chat (stream=true): the SSE stream carries no `ui` event and
   terminates with the existing `done` event
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

SERVER_PORT = 18251
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}/v1"
HEADERS = {"X-Muxi-Client-Key": "envelope-client-key", "X-Muxi-User-Id": "regression-user"}


def assert_no_ui_key(node, path="$"):
    """Recursively assert no 'ui' key exists anywhere in the JSON tree."""
    if isinstance(node, dict):
        assert "ui" not in node, f"Unexpected 'ui' key at {path}"
        for key, value in node.items():
            assert_no_ui_key(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            assert_no_ui_key(item, f"{path}[{i}]")


async def main() -> int:
    print("MUXI Runtime - Test 25A4: no-widget envelope regression pin")
    print("=" * 70)

    formation_path = Path(__file__).parent / "formations" / "formation-envelope"
    formation = Formation()
    await formation.load(str(formation_path))
    await formation.start_server(block=False)
    await asyncio.sleep(2)

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            # ---------------------------------------------------------
            # Part 1: non-streaming JSON envelope
            # ---------------------------------------------------------
            print("\n[1] POST /v1/chat (stream=false) with a plain question...")
            response = await client.post(
                f"{BASE_URL}/chat",
                headers=HEADERS,
                json={
                    "message": "Say hello in exactly two words.",
                    "session_id": "sess-25a4-json",
                    "stream": False,
                },
            )
            assert response.status_code == 200, f"chat failed: {response.text[:300]}"
            body = response.json()

            message = body["data"]["message"]
            assert set(message.keys()) == {
                "role",
                "content",
                "artifacts",
                "metadata",
            }, f"Envelope key drift: {sorted(message.keys())}"
            assert_no_ui_key(body)
            assert message["content"].strip(), "Expected a text response"
            print(f"    Envelope keys pinned: {sorted(message.keys())}")
            print("    No 'ui' key anywhere in the response JSON")

            # ---------------------------------------------------------
            # Part 2: SSE stream vocabulary unchanged
            # ---------------------------------------------------------
            print("\n[2] POST /v1/chat (stream=true) and scanning the SSE stream...")
            event_names = []
            async with client.stream(
                "POST",
                f"{BASE_URL}/chat",
                headers=HEADERS,
                json={
                    "message": "Say hello in exactly two words.",
                    "session_id": "sess-25a4-sse",
                    "stream": True,
                },
            ) as sse:
                assert sse.status_code == 200, f"stream failed: {sse.status_code}"
                async for line in sse.aiter_lines():
                    if line.startswith("event:"):
                        event_names.append(line.split(":", 1)[1].strip())

            assert "ui" not in event_names, f"Unexpected ui event without widgets: {event_names}"
            assert "done" in event_names, f"Missing terminal done event: {event_names}"
            print(f"    SSE named events observed: {event_names}")
            print("    No 'ui' event; terminal 'done' present")

        print("\n" + "=" * 70)
        print("SUCCESS: no-widget responses are byte-identical to the")
        print("         pre-feature envelope on both transports")
        return 0

    finally:
        try:
            formation.stop()
        except Exception:
            pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    os._exit(exit_code)
