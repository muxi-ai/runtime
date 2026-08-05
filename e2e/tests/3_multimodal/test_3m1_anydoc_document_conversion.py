#!/usr/bin/env python3
"""
Test 3M1: anydoc document conversion -> RTF/ODT/CSV/DOCX attachments convert,
corrupt anydoc-only file quarantines.

Feature test for the anydoc-primary document conversion routing: office,
OpenDocument, RTF, EPUB, and CSV attachments are converted out-of-process by
anydoc (Firecrawl's Rust converter) inside the same sandbox that previously
ran MarkItDown, with DOCUMENT_CONVERSION_COMPLETED events naming the engine.
A deliberately-corrupt ODT (an anydoc-only format, so no MarkItDown fallback
exists) must quarantine as parser_error while the chat degrades gracefully.

Standalone script (per e2e conventions): run directly, not via pytest.
"""

import asyncio
import io
import sys
import threading
import time
import zipfile
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402
from muxi.runtime.services import observability  # noqa: E402

COMPLETED_EVENT = "document.conversion.completed"
QUARANTINE_EVENT = "document.conversion.quarantined"

# --- Real fixtures, built from scratch (no binary blobs in the repo) --------

RTF_FIXTURE = (
    rb"{\rtf1\ansi\deff0 {\fonttbl {\f0 Times New Roman;}}"
    rb"\f0\fs24 Quarterly revenue grew {\b fourteen percent} in Q3.\par}"
)

CSV_FIXTURE = b"product,units\nwidget,3\ngadget,7\n"


def make_odt_bytes(text: str) -> bytes:
    """A minimal but valid ODT: a zip with the ODF mimetype and content.xml."""
    content_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<office:document-content"
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' office:version="1.2">'
        f"<office:body><office:text><text:p>{text}</text:p></office:text></office:body>"
        "</office:document-content>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "mimetype",
            "application/vnd.oasis.opendocument.text",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr("content.xml", content_xml)
    return buffer.getvalue()


def make_docx_bytes(text: str) -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# Zip local-file magic followed by garbage: anydoc detects the ODT route but
# cannot read the archive. ODT is anydoc-only (MarkItDown has no ODF support),
# so there is no fallback and the file must quarantine as parser_error.
CORRUPT_ODT = b"PK\x03\x04" + b"\x00\xff\xfe\x01" * 128


class CapturingLogger:
    """Event sink recording everything observe() emits (same shape as test 3L1)."""

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


async def wait_for_events(capturing, predicate, timeout=10):
    deadline = time.time() + timeout
    matches = []
    while time.time() < deadline:
        matches = [e for e in capturing.snapshot() if predicate(e)]
        if matches:
            break
        await asyncio.sleep(0.25)
    return matches


async def run() -> bool:
    print("=" * 70)
    print("Test 3M1: anydoc document conversion (RTF/ODT/CSV/DOCX + corrupt quarantine)")
    print("=" * 70)

    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    print("1. Overlord started")

    capturing = CapturingLogger()
    observability.set_runtime_event_logger(capturing)

    good_files = [
        {
            "filename": "report.rtf",
            "content": RTF_FIXTURE,
            "content_type": "application/rtf",
            "size": len(RTF_FIXTURE),
        },
        {
            "filename": "letter.odt",
            "content": make_odt_bytes("The onboarding letter mentions a purple giraffe."),
            "content_type": "application/vnd.oasis.opendocument.text",
            "size": 0,
        },
        {
            "filename": "inventory.csv",
            "content": CSV_FIXTURE,
            "content_type": "text/csv",
            "size": len(CSV_FIXTURE),
        },
        {
            "filename": "memo.docx",
            "content": make_docx_bytes("The memo approves the anydoc rollout."),
            "content_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "size": 0,
        },
    ]
    for f in good_files:
        f["size"] = len(f["content"])

    print(f"2. Sending chat with {len(good_files)} attachments (rtf/odt/csv/docx)...")
    response = await overlord.chat(
        user_id="test_user",
        message="Please summarize the attached documents for me.",
        files=good_files,
        use_async=False,
        stream=False,
    )
    result = response.content if hasattr(response, "content") else str(response)
    print(f"3. Chat completed; response length: {len(result)} chars")
    assert isinstance(result, str) and len(result) > 0, "chat did not return a response"

    expected = {f["filename"] for f in good_files}
    completed = await wait_for_events(
        capturing,
        lambda e: e["event"] == COMPLETED_EVENT and (e["data"] or {}).get("filename") in expected,
    )
    # Wait until all four completions arrive (events emit on background threads).
    deadline = time.time() + 10
    while time.time() < deadline:
        completed = [
            e
            for e in capturing.snapshot()
            if e["event"] == COMPLETED_EVENT and (e["data"] or {}).get("filename") in expected
        ]
        if {(e["data"] or {}).get("filename") for e in completed} == expected:
            break
        await asyncio.sleep(0.25)

    seen = {(e["data"] or {}).get("filename"): (e["data"] or {}).get("engine") for e in completed}
    print(f"4. Conversion events captured: {seen}")
    assert set(seen) == expected, f"missing conversion events; got {set(seen)}"
    for filename, engine in seen.items():
        assert engine == "anydoc", f"{filename} converted by {engine}, expected anydoc"

    # --- Corrupt anydoc-only format: quarantine, no fallback, graceful chat ---
    corrupt_file = [
        {
            "filename": "broken.odt",
            "content": CORRUPT_ODT,
            "content_type": "application/vnd.oasis.opendocument.text",
            "size": len(CORRUPT_ODT),
        }
    ]
    print(f"5. Sending chat with corrupt ODT attachment ({len(CORRUPT_ODT)} bytes)...")
    response = await overlord.chat(
        user_id="test_user",
        message="Please summarize the attached document for me.",
        files=corrupt_file,
        use_async=False,
        stream=False,
    )
    result = response.content if hasattr(response, "content") else str(response)
    print(f"6. Chat completed; response length: {len(result)} chars")
    assert isinstance(result, str) and len(result) > 0, "chat did not return a response"

    quarantined = await wait_for_events(
        capturing,
        lambda e: e["event"] == QUARANTINE_EVENT
        and (e["data"] or {}).get("filename") == "broken.odt",
    )
    assert quarantined, (
        f"no {QUARANTINE_EVENT} event for broken.odt; "
        f"captured events: {sorted({e['event'] for e in capturing.snapshot()})}"
    )
    data = quarantined[0]["data"] or {}
    print(f"7. Quarantine event captured: reason={data.get('quarantine_reason')}")
    assert data.get("quarantine_reason") == "parser_error", data
    assert data.get("engine") == "anydoc", data

    await formation.stop_overlord()
    print("8. Overlord stopped cleanly")

    print("\n" + "=" * 40 + "\n")
    print("### Test Result:")
    print("  🎉 SUCCESS: anydoc converted rtf/odt/csv/docx attachments end to end")
    print("  ✓ document.conversion.completed emitted with engine=anydoc for all four")
    print("  ✓ Corrupt ODT (anydoc-only, no fallback) quarantined as parser_error")
    print("  ✓ Both chat requests completed with normal responses")
    return True


if __name__ == "__main__":
    success = asyncio.run(run())
    sys.exit(0 if success else 1)
