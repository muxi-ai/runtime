#!/usr/bin/env python3
"""
Test 18c: PII/secret redaction in the observability pipeline.

Exercises the real runtime path end-to-end (no LLM required):
  - A real formation is loaded and the overlord is started, which registers the
    entity detector from ``logging.redaction.entities`` before observability is
    enabled.
  - Events are emitted through the real ``observe()`` -> EventLogger pipeline and
    captured, proving secrets and PII are redacted before they reach any sink.
  - Both flag states are verified: with ``entities: true`` names/orgs are masked;
    with ``entities: false`` the entity layer is off but the always-on regex layer
    still masks secrets.

Standalone script (per e2e conventions): run directly, not via pytest.
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
from muxi.runtime.services.observability import ConversationEvents, EventLevel  # noqa: E402
from muxi.runtime.utils.redaction import get_entity_detector  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-redaction"

# Build secret-like values at runtime so no real-looking credential literal is
# committed to source (keeps secret scanners quiet); they still match the
# redactor's patterns.
SECRET = "sk-" + "z" * 32
CARD = "4111" + "1111" * 3  # Luhn-valid Visa test number
EMAIL = "jane.doe@example.com"
SSN = "123-45-6789"
PERSON = "Jane Doe"
ORG = "Microsoft"


class CapturingLogger:
    """Drop-in event sink that records the (already-redacted) events observe() emits."""

    def __init__(self):
        self._events = []
        self._lock = threading.Lock()

    def should_emit(self, event_type, level):
        """Pre-check observe() calls before redaction/emission; capture everything."""
        return True

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
    """observe() emits on a short-lived background thread; give it time to drain.

    We deliberately do not call ``multitasking.wait_for_tasks()`` here: the
    running formation keeps long-lived background tasks alive, so that call
    would block indefinitely.
    """
    time.sleep(1.0)


async def _emit_and_capture(formation_file: str, payload: dict):
    """Load a formation, start the overlord, emit one event, and capture it."""
    formation = Formation()
    await formation.load(str(FORMATION_DIR / formation_file))
    await formation.start_overlord()

    detector = get_entity_detector()

    capturing = CapturingLogger()
    observability.set_runtime_event_logger(capturing)
    observability.observe(
        ConversationEvents.REQUEST_RECEIVED,
        level=EventLevel.INFO,
        data=payload,
        description=f"request from {PERSON}: key {payload.get('secret', '')}",
    )
    _flush_background()
    events = capturing.snapshot()

    await formation.stop_overlord()
    return detector, events


async def run() -> bool:
    print("=" * 70)
    print("Test 18c: PII/secret redaction in the observability pipeline")
    print("=" * 70)

    checks = []

    # ------------------------------------------------------------------
    # Case 1: entity redaction enabled (default)
    # ------------------------------------------------------------------
    print("\n1. Loading formation with logging.redaction.entities: true ...")
    payload = {
        "secret": SECRET,
        "email": EMAIL,
        "card": CARD,
        "ssn": SSN,
        "note": f"Contact {PERSON} at {ORG} regarding the account.",
    }
    detector, events = await _emit_and_capture("formation.yaml", payload)
    assert events, "no events were captured from the observe() pipeline"
    blob = json.dumps(events)
    print(f"   Captured {len(events)} event(s); entity detector active: {detector is not None}")

    # Always-on regex layer: secrets/PII must never appear raw.
    assert SECRET not in blob, "raw API key leaked into emitted event"
    assert CARD not in blob, "raw credit card leaked into emitted event"
    assert EMAIL not in blob, "raw email leaked into emitted event"
    assert SSN not in blob, "raw SSN leaked into emitted event"
    assert "***" in blob, "expected redaction markers in emitted event"
    checks.append("Regex layer masks secret/card/email/SSN in emitted events")
    print("   Secret, card, email, SSN all redacted (regex layer)")

    # Entity layer (only when the spaCy model + presidio are available).
    if detector is not None:
        assert PERSON not in blob, "person name leaked despite entity redaction enabled"
        assert ORG not in blob, "organization leaked despite entity redaction enabled"
        assert "[PERSON_1]" in blob, "expected [PERSON_1] entity token"
        assert "[ORG_1]" in blob, "expected [ORG_1] entity token"
        checks.append("Entity layer masks PERSON/ORG with indexed tokens")
        print(f"   '{PERSON}' -> [PERSON_1], '{ORG}' -> [ORG_1] (entity layer)")
    else:
        checks.append("Entity detector unavailable; regex layer verified (model not installed)")
        print("   NOTE: entity detector not registered (presidio/model unavailable);")
        print("         regex redaction still verified.")

    # ------------------------------------------------------------------
    # Case 2: entity redaction disabled - flag actually turns the layer off,
    # but the regex layer stays active.
    # ------------------------------------------------------------------
    print("\n2. Loading formation with logging.redaction.entities: false ...")
    secret2 = "sk-" + "q" * 32
    payload2 = {"secret": secret2, "note": f"Contact {PERSON} at {ORG}."}
    detector2, events2 = await _emit_and_capture("formation-no-entities.yaml", payload2)
    assert events2, "no events were captured in the disabled case"
    blob2 = json.dumps(events2)
    print(f"   Captured {len(events2)} event(s); entity detector active: {detector2 is not None}")

    assert detector2 is None, "entity detector should be unregistered when entities: false"
    assert secret2 not in blob2, "raw secret leaked even though regex layer is always on"
    assert PERSON in blob2, "person name should be preserved when entity layer is disabled"
    checks.append("entities: false disables entity layer but regex layer still masks secrets")
    print(f"   Detector off; secret redacted; '{PERSON}' preserved (entity layer disabled)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 40)
    print("\n### Test Result:")
    print("  🎉 SUCCESS: PII/secret redaction verified end-to-end")
    for c in checks:
        print(f"  ✓ {c}")
    print("\n" + "=" * 40)
    print("\n### Chat transcript:")
    print(f"\nUser: Contact {PERSON} at {ORG}; key {SECRET}; card {CARD}")
    print("System (emitted event, redacted): " f"{json.dumps(events[0]['data'])}")
    print(f"\nUser (entities off): Contact {PERSON} at {ORG}; key {secret2}")
    print("System (emitted event, redacted): " f"{json.dumps(events2[0]['data'])}")

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
