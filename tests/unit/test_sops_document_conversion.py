"""
Unit tests for SOP attachment conversion (``SOPSystem.get_resource_content``).

The SOP ``[file:...]`` path used to instantiate ``MarkItDown()`` and parse
untrusted document bytes *in the runtime process* — no subprocess isolation,
no rlimits, no wall-clock kill, no ``QuarantineReason`` handling — while every
other document intake path (chat attachments, knowledge files) went through
the sandboxed ``convert_document()`` service built in PR #305.

Three layers of coverage:

1. **Sandbox guard** — the SOP path must call the out-of-process converter and
   must never construct ``MarkItDown`` in-process. A poisoned ``markitdown``
   module makes an in-process regression fail loudly instead of silently
   re-opening the hole.

2. **Graceful degradation** — a quarantined document (timeout / memory /
   oversize / parser_error / encrypted / unsupported) returns the existing
   placeholder string rather than raising into SOP execution.

3. **Extension gate** — the gate is the converter's own supported-extension
   set, not a hand-maintained list. The old list advertised ``.doc``/``.ppt``,
   which MarkItDown cannot read at all; anydoc (PR #318) does, so those files
   now convert instead of failing confusingly.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock

import pytest

from muxi.runtime.formation.workflow import sops as sops_module
from muxi.runtime.formation.workflow.sops import SOPSystem
from muxi.runtime.services.multimodal import document_converter
from muxi.runtime.services.multimodal.document_converter import (
    ConversionResult,
    QuarantineReason,
)


@pytest.fixture
def sop_system(tmp_path):
    """An SOPSystem with no ``sops/`` directory, so __init__ stays inert."""
    return SOPSystem(formation_path=tmp_path)


@pytest.fixture
def poisoned_markitdown(monkeypatch):
    """Make any in-process ``MarkItDown()`` construction fail the test."""

    class _Exploding:
        def __init__(self, *args, **kwargs):
            raise AssertionError(
                "MarkItDown was constructed in-process; document conversion must "
                "go through the sandboxed convert_document() service"
            )

    module = types.ModuleType("markitdown")
    module.MarkItDown = _Exploding
    monkeypatch.setitem(sys.modules, "markitdown", module)
    return module


def _register(sop_system: SOPSystem, tmp_path, name: str, payload: bytes = b"\x00binary"):
    """Write a fixture file and register it as a resolvable SOP resource."""
    path = tmp_path / name
    path.write_bytes(payload)
    sop_system.resource_map[name] = path
    return path


# ---------------------------------------------------------------------------
# Layer 1 — the SOP path uses the sandboxed converter, not MarkItDown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_resource_goes_through_sandboxed_converter(
    sop_system, tmp_path, monkeypatch, poisoned_markitdown
):
    """A PDF attachment is converted out-of-process, with its raw bytes."""
    path = _register(sop_system, tmp_path, "report.pdf", b"%PDF-1.7 fake")

    convert = AsyncMock(
        return_value=ConversionResult(ok=True, text="# Report", engine="pdf_inspector")
    )
    monkeypatch.setattr(sops_module, "convert_document_async", convert)

    assert await sop_system.get_resource_content("report.pdf") == "# Report"

    convert.assert_awaited_once()
    args, kwargs = convert.call_args
    assert args[0] == b"%PDF-1.7 fake"
    assert args[1] == "report.pdf"
    # The caller's size budget is handed to the sandbox's pre-spawn input cap.
    assert kwargs["max_input_bytes"] == 10 * 1024 * 1024
    # No path handle is leaked to the parser; only bytes cross the boundary.
    assert str(path) not in [a for a in args if isinstance(a, str)]


@pytest.mark.asyncio
async def test_max_file_size_mb_flows_into_converter_input_cap(sop_system, tmp_path, monkeypatch):
    """A caller-tightened size budget reaches the sandbox, not just the pre-check."""
    _register(sop_system, tmp_path, "small.docx")

    convert = AsyncMock(return_value=ConversionResult(ok=True, text="ok", engine="anydoc"))
    monkeypatch.setattr(sops_module, "convert_document_async", convert)

    await sop_system.get_resource_content("small.docx", max_file_size_mb=2)

    assert convert.call_args.kwargs["max_input_bytes"] == 2 * 1024 * 1024


@pytest.mark.asyncio
async def test_text_and_image_resources_never_reach_the_converter(
    sop_system, tmp_path, monkeypatch
):
    """Plain text is read directly and images stay references — no subprocess spawn."""
    (tmp_path / "notes.md").write_text("hello")
    sop_system.resource_map["notes.md"] = tmp_path / "notes.md"
    _register(sop_system, tmp_path, "shot.png")

    convert = AsyncMock()
    monkeypatch.setattr(sops_module, "convert_document_async", convert)

    assert await sop_system.get_resource_content("notes.md") == "hello"
    assert await sop_system.get_resource_content("shot.png") == "[Image file: shot.png]"
    convert.assert_not_awaited()


def test_sop_system_no_longer_holds_an_in_process_document_processor(sop_system):
    """The MarkItDown-holding lazy service is gone, not merely bypassed."""
    assert not hasattr(sop_system, "_get_document_processor")
    assert not hasattr(sop_system, "_document_processor")


# ---------------------------------------------------------------------------
# Layer 2 — quarantined documents degrade, never abort the SOP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        QuarantineReason.TIMEOUT,
        QuarantineReason.MEMORY,
        QuarantineReason.OVERSIZE,
        QuarantineReason.PARSER_ERROR,
        QuarantineReason.ENCRYPTED,
        QuarantineReason.UNSUPPORTED,
    ],
)
@pytest.mark.asyncio
async def test_quarantined_document_degrades_gracefully(sop_system, tmp_path, monkeypatch, reason):
    """Every quarantine reason yields the placeholder, not an exception."""
    _register(sop_system, tmp_path, "hostile.pdf")

    monkeypatch.setattr(
        sops_module,
        "convert_document_async",
        AsyncMock(
            return_value=ConversionResult(
                ok=False,
                engine="pdf_inspector",
                quarantine_reason=reason,
                detail="worker killed",
            )
        ),
    )

    assert (
        await sop_system.get_resource_content("hostile.pdf") == "[Unable to extract: hostile.pdf]"
    )


@pytest.mark.asyncio
async def test_quarantine_emits_observability_event(sop_system, tmp_path, monkeypatch):
    """The degradation is observable, carrying the quarantine reason."""
    _register(sop_system, tmp_path, "hostile.pdf")

    monkeypatch.setattr(
        sops_module,
        "convert_document_async",
        AsyncMock(
            return_value=ConversionResult(
                ok=False,
                engine="pdf_inspector",
                quarantine_reason=QuarantineReason.TIMEOUT,
                detail="conversion exceeded 60.0s wall-clock limit",
            )
        ),
    )

    events = []
    monkeypatch.setattr(
        sops_module.observability,
        "observe",
        lambda **kwargs: events.append(kwargs),
    )

    await sop_system.get_resource_content("hostile.pdf")

    quarantine_events = [e for e in events if e["data"].get("quarantine_reason")]
    assert len(quarantine_events) == 1
    assert quarantine_events[0]["data"]["quarantine_reason"] == "timeout"
    assert quarantine_events[0]["data"]["file_type"] == ".pdf"


@pytest.mark.asyncio
async def test_unreadable_file_degrades_instead_of_raising(sop_system, tmp_path, monkeypatch):
    """An unreadable resource degrades before any conversion is attempted."""
    path = _register(sop_system, tmp_path, "locked.docx")
    path.unlink()

    convert = AsyncMock()
    monkeypatch.setattr(sops_module, "convert_document_async", convert)

    assert await sop_system.get_resource_content("locked.docx") == "[Unable to read: locked.docx]"
    convert.assert_not_awaited()


# ---------------------------------------------------------------------------
# Layer 3 — the extension gate tracks the converter, not a hand-kept list
# ---------------------------------------------------------------------------


def test_gate_is_the_converters_own_supported_set(sop_system):
    """SOPs share the converter's constant, so the gate cannot drift from it."""
    assert (
        sops_module.ATTACHMENT_CONVERTIBLE_EXTENSIONS
        is document_converter.ATTACHMENT_CONVERTIBLE_EXTENSIONS
    )


@pytest.mark.parametrize("filename", ["legacy.doc", "deck.ppt", "book.xls"])
@pytest.mark.asyncio
async def test_legacy_binary_office_attachments_now_convert(
    sop_system, tmp_path, monkeypatch, filename
):
    """Legacy .doc/.ppt/.xls route to anydoc instead of failing on MarkItDown."""
    _register(sop_system, tmp_path, filename, b"\xd0\xcf\x11\xe0 ole2")

    convert = AsyncMock(
        return_value=ConversionResult(ok=True, text="converted body", engine="anydoc")
    )
    monkeypatch.setattr(sops_module, "convert_document_async", convert)

    assert await sop_system.get_resource_content(filename) == "converted body"
    assert convert.await_count == 1


@pytest.mark.parametrize("filename", ["notes.odt", "memo.rtf", "manual.epub", "page.html"])
@pytest.mark.asyncio
async def test_formats_the_old_gate_rejected_now_convert(
    sop_system, tmp_path, monkeypatch, filename
):
    """OpenDocument/RTF/EPUB/HTML were unreachable under the old hand-kept list."""
    _register(sop_system, tmp_path, filename)

    convert = AsyncMock(return_value=ConversionResult(ok=True, text="body", engine="anydoc"))
    monkeypatch.setattr(sops_module, "convert_document_async", convert)

    assert await sop_system.get_resource_content(filename) == "body"


@pytest.mark.asyncio
async def test_genuinely_unsupported_type_still_reports_unsupported(
    sop_system, tmp_path, monkeypatch
):
    """Formats no converter claims keep the pre-existing placeholder."""
    _register(sop_system, tmp_path, "archive.zip")

    convert = AsyncMock()
    monkeypatch.setattr(sops_module, "convert_document_async", convert)

    result = await sop_system.get_resource_content("archive.zip")
    assert result == "[Unsupported file type: archive.zip]"
    convert.assert_not_awaited()
