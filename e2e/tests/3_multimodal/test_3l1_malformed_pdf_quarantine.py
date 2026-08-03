#!/usr/bin/env python3
"""
Test 3L1: Malformed PDF attachment -> quarantine + graceful degradation.

Security regression test for the sandboxed document conversion service:
a hostile/malformed PDF attachment must NOT crash or hang the runtime.
The conversion runs out-of-process (pdf-inspector with MarkItDown fallback),
gets quarantined with a typed reason, a DOCUMENT_CONVERSION_QUARANTINED
event is emitted, and the chat request still completes normally.

Standalone script (per e2e conventions): run directly, not via pytest.
"""

import asyncio
import sys
import threading
import time
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402
from muxi.runtime.services import observability  # noqa: E402

QUARANTINE_EVENT = "document.conversion.quarantined"

# A "PDF" that neither pdf-inspector nor MarkItDown can parse: valid magic
# bytes followed by binary garbage. Routing sends it to pdf-inspector, which
# fails; the sandboxed MarkItDown fallback also fails; the file is quarantined
# with reason parser_error and the chat continues without the attachment.
MALFORMED_PDF = b"%PDF-1.7\n" + b"\x00\xff\xfe\x01" * 512 + b"\n%%EOF"


class CapturingLogger:
    """Event sink recording everything observe() emits (same shape as test 18c)."""

    def __init__(self):
        self._events = []
        self._lock = threading.Lock()

    def should_emit(self, event_type, level):
        return True

    def emit_event(self, event_type=None, level=None, data=None, description=None, **kwargs):
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


async def run() -> bool:
    print("=" * 70)
    print("Test 3L1: Malformed PDF attachment -> quarantine + graceful degradation")
    print("=" * 70)

    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    print("1. Overlord started")

    capturing = CapturingLogger()
    observability.set_runtime_event_logger(capturing)

    files = [
        {
            "filename": "malformed.pdf",
            "content": MALFORMED_PDF,
            "content_type": "application/pdf",
            "size": len(MALFORMED_PDF),
        }
    ]
    user_message = "Please summarize the attached document for me."

    print(f"2. Sending chat with malformed PDF attachment ({len(MALFORMED_PDF)} bytes)...")
    response = await overlord.chat(
        user_id="test_user",
        message=user_message,
        files=files,
        use_async=False,
        stream=False,
    )
    result = response.content if hasattr(response, "content") else str(response)
    print(f"3. Chat completed; response length: {len(result)} chars")
    print(f"   Response preview: {result[:200]}")

    # Graceful degradation: the runtime survived and the chat produced a reply.
    assert isinstance(result, str) and len(result) > 0, "chat did not return a response"

    # observe() emits on background threads; wait for the quarantine event.
    quarantine_events = []
    deadline = time.time() + 10
    while time.time() < deadline:
        quarantine_events = [e for e in capturing.snapshot() if e["event"] == QUARANTINE_EVENT]
        if quarantine_events:
            break
        await asyncio.sleep(0.25)

    assert quarantine_events, (
        f"no {QUARANTINE_EVENT} event was emitted; "
        f"captured events: {sorted({e['event'] for e in capturing.snapshot()})}"
    )
    event = quarantine_events[0]
    reason = (event["data"] or {}).get("quarantine_reason")
    filename = (event["data"] or {}).get("filename")
    print(f"4. Quarantine event captured: reason={reason} filename={filename}")
    assert reason == "parser_error", f"expected parser_error, got {reason}"
    assert filename == "malformed.pdf", f"unexpected filename in event: {filename}"

    await formation.stop_overlord()
    print("5. Overlord stopped cleanly")

    print("\n" + "=" * 40 + "\n")
    print("### Test Result:")
    print("  🎉 SUCCESS: Malformed PDF was quarantined and chat degraded gracefully")
    print("  ✓ Runtime survived a hostile PDF (no crash, no hang)")
    print("  ✓ document.conversion.quarantined emitted with reason parser_error")
    print("  ✓ Chat request completed with a normal response")
    print("\n" + "=" * 40 + "\n")
    print("### Chat transcript:")
    print(f"\nUser: {user_message} [attachment: malformed.pdf]")
    print(f"System: {result[:500]}")
    return True


if __name__ == "__main__":
    success = asyncio.run(run())
    sys.exit(0 if success else 1)
