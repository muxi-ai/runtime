#!/usr/bin/env python3
"""
Test 18d: secrets/PII in a real chat never leak into observability events.

Runs a real ``overlord.chat()`` turn whose user message embeds an API key, an
email, and a personal name, captures every observability event emitted during
the turn, and asserts none of the raw sensitive values appear in any event the
runtime would route to a log sink.

Requires a live LLM (OpenAI key from secrets.enc), like other Area 1/18 chat
tests. Standalone script: run directly, not via pytest.
"""

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from muxi.runtime.formation import Formation  # noqa: E402
from muxi.runtime.services import observability  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-redaction"

# Constructed at runtime so no credential-looking literal is committed.
SECRET = "sk-" + "z" * 32
EMAIL = "jane.doe@example.com"
PERSON = "Jane Doe"


class CapturingLogger:
    """Records (already-redacted) events emitted during the chat turn."""

    def __init__(self):
        self._events = []
        self._lock = threading.Lock()

    def emit_event(
        self,
        event_type=None,
        level=None,
        data=None,
        description=None,
        request_context=None,
        **kwargs,
    ):
        with self._lock:
            self._events.append(
                {
                    "event": getattr(event_type, "value", str(event_type)),
                    "data": data,
                    "description": description,
                }
            )
        return ""

    def snapshot(self):
        with self._lock:
            return list(self._events)


def _flush_background():
    # The running formation keeps long-lived multitasking tasks alive, so we
    # cannot wait_for_tasks(); a short sleep lets the per-event emit threads drain.
    time.sleep(1.0)


async def run() -> bool:
    print("=" * 70)
    print("Test 18d: no secret/PII leak into observability events during chat")
    print("=" * 70)

    formation = Formation()
    await formation.load(str(FORMATION_DIR / "formation.yaml"))
    overlord = await formation.start_overlord()
    print("\n1. Formation loaded and overlord started.")

    capturing = CapturingLogger()
    observability.set_runtime_event_logger(capturing)

    message = (
        f"My name is {PERSON}, my email is {EMAIL}, and my OpenAI key is {SECRET}. "
        "Please just say hello."
    )
    print("\n2. Sending chat message containing a secret + PII ...")
    response = await asyncio.wait_for(overlord.chat(message, user_id="redaction_user"), timeout=90)
    response_text = getattr(response, "content", None) or str(response)

    _flush_background()
    events = capturing.snapshot()
    await formation.stop_overlord()

    print(
        f"   Received response ({len(response_text)} chars); "
        f"captured {len(events)} event(s) during the turn."
    )

    assert events, "expected the chat turn to emit observability events"
    blob = json.dumps(events)

    # The headline guarantee: the raw secret and email never reach a log sink.
    assert SECRET not in blob, "raw API key leaked into an observability event"
    assert EMAIL not in blob, "raw email leaked into an observability event"

    checks = [
        "Real chat turn completed",
        f"{len(events)} observability events captured",
        "Raw API key never appears in any emitted event",
        "Raw email never appears in any emitted event",
    ]

    # If any event carried the user message and the entity layer is active, the
    # name should be masked too; only assert when the name actually shows up.
    detector_active = "[PERSON_1]" in blob
    if PERSON in blob:
        raise AssertionError("person name leaked unmasked into an observability event")
    if detector_active:
        checks.append("Person name masked to [PERSON_1] in emitted events")

    print("\n" + "=" * 40)
    print("\n### Test Result:")
    print("  🎉 SUCCESS: chat secrets/PII redacted before reaching log sinks")
    for c in checks:
        print(f"  ✓ {c}")
    print("\n" + "=" * 40)
    print("\n### Chat transcript:")
    print(f"\nUser: {message}")
    print(f"System: {response_text[:200]}")

    return True


def main() -> int:
    try:
        ok = asyncio.run(run())
        return 0 if ok else 1
    except Exception as e:
        import traceback

        print(f"\n❌ FAIL: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import os

    exit_code = main()
    if exit_code == 0:
        print("\nSUCCESS", flush=True)
    os._exit(exit_code)
