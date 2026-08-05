# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Document Converter - Out-of-Process Document Conversion Service
# Description:  Converts untrusted documents (PDF/Office/HTML/...) to markdown text
# Role:         Security boundary between untrusted document bytes and the runtime
# Usage:        result = convert_document(content, filename) / await convert_document_async(...)
# Author:       Muxi Framework Team
#
# Untrusted documents (chat attachments, knowledge source files) were previously
# parsed in-process by MarkItDown: a malformed or hostile file could crash, hang,
# or balloon the runtime process. This service moves every conversion into a
# spawned subprocess (conversion_worker.py) with:
#
#   - bounded input size, checked BEFORE spawning anything
#   - resource.setrlimit in the worker: CPU seconds, address space (Linux only),
#     and output file size (all platforms)
#   - a hard wall-clock timeout; on expiry the whole process group is killed
#   - typed QuarantineReason outcomes - callers NEVER see an unhandled parser
#     exception, they get a ConversionResult and degrade gracefully
#
# Honest limits (v1): there is no network namespace or seccomp on a plain POSIX
# host. Proxy environment variables are stripped from the worker env as a
# best-effort measure, but the subprocess boundary + rlimits + timeout is the
# actual containment win; egress control is not claimed. On Windows the
# resource module does not exist, so only the process boundary, the pre-spawn
# input cap, the wall-clock timeout (plain kill - no process groups), and the
# explicit output-size check apply.
#
# Routing: application/pdf (or a .pdf extension) goes to pdf-inspector, whose
# native-text path runs locally, emits structured markdown, AND classifies
# native-text vs scanned pages - anydoc's Python API returns only a markdown
# string for PDFs (its to_document() explicitly rejects them), so the direct
# pdf-inspector route stays. Office/OpenDocument/RTF/EPUB/CSV formats go to
# anydoc (Firecrawl's Rust converter, which also covers legacy .doc/.ppt/.xls
# and macro variants MarkItDown never handled). Everything else convertible
# (HTML, ...) stays on MarkItDown - all inside the same sandbox.
#
# Fallbacks (per file, inside the worker): when the primary converter fails,
# the worker retries with sandboxed MarkItDown for the formats MarkItDown
# supports, so no format fails harder than it did before anydoc was primary.
# Formats only anydoc can read (odt/ods/odp, rtf, legacy .doc/.ppt, macro
# variants) have no fallback: a failure quarantines as parser_error and the
# events say so honestly.
# =============================================================================

import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .. import observability

# Wall-clock ceiling for a single conversion (parent-enforced; the worker also
# gets an RLIMIT_CPU backstop derived from it).
DEFAULT_TIMEOUT_SECONDS = 60.0
# Rejected before spawning: nothing this large belongs in a chat attachment or
# knowledge file, and refusing pre-spawn keeps hostile inputs cheap.
DEFAULT_MAX_INPUT_BYTES = 50 * 1024 * 1024
# Cap on converted text; protects against decompression bombs whose tiny input
# passes the pre-spawn check but expands enormously.
DEFAULT_MAX_OUTPUT_BYTES = 10 * 1024 * 1024
# Address-space limit for the worker (enforced on Linux only; matches the
# artifact sandbox's 2GB figure - parsers map a lot of virtual memory).
DEFAULT_MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024

_WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conversion_worker.py")

ENGINE_PDF_INSPECTOR = "pdf_inspector"
ENGINE_MARKITDOWN = "markitdown"
ENGINE_ANYDOC = "anydoc"

# Extensions anydoc converts (its full claimed surface minus PDF, which keeps
# the dedicated pdf-inspector route below).
ANYDOC_EXTENSIONS = frozenset(
    {
        # Word
        ".doc",
        ".docx",
        ".docm",
        # PowerPoint
        ".ppt",
        ".pps",
        ".pot",
        ".pptx",
        ".pptm",
        ".ppsx",
        ".ppsm",
        # Excel
        ".xls",
        ".xlsx",
        ".xlsm",
        ".xlsb",
        # OpenDocument
        ".odt",
        ".ods",
        ".odp",
        # Rich Text Format
        ".rtf",
        # E-books
        ".epub",
        # Data
        ".csv",
    }
)

# MIME types that route to anydoc (compared lowercased, parameters stripped).
_ANYDOC_MEDIA_TYPES = frozenset(
    {
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-word.document.macroenabled.12",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
        "application/vnd.ms-powerpoint.presentation.macroenabled.12",
        "application/vnd.ms-powerpoint.slideshow.macroenabled.12",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroenabled.12",
        "application/vnd.ms-excel.sheet.binary.macroenabled.12",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
        "application/rtf",
        "text/rtf",
        "application/epub+zip",
        "text/csv",
    }
)

# The subset of anydoc's surface that sandboxed MarkItDown can also read
# (verified against the markitdown[docx,pdf,pptx,xls,xlsx] extras actually
# installed: its CSV and EPUB converters are built in, so both keep the
# fallback they effectively had when MarkItDown was primary). Legacy .doc/.ppt,
# macro variants, .xlsb, OpenDocument, and RTF are anydoc-only: no fallback.
_MARKITDOWN_FALLBACK_EXTENSIONS = frozenset({".docx", ".pptx", ".xlsx", ".xls", ".csv", ".epub"})
_MARKITDOWN_FALLBACK_MEDIA_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "text/csv",
        "application/epub+zip",
    }
)

# Extensions the chat-attachment path converts: the previous MarkItDown gate
# (.pdf/.docx/.pptx/.xlsx/.html) widened to anydoc's full claimed surface.
ATTACHMENT_CONVERTIBLE_EXTENSIONS = [".pdf", ".html"] + sorted(ANYDOC_EXTENSIONS)

# Environment variables stripped from the worker (best-effort network hygiene).
_PROXY_ENV_VARS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
)


class QuarantineReason(str, Enum):
    """Why a document conversion was refused or killed instead of completing."""

    TIMEOUT = "timeout"  # wall-clock or CPU limit exceeded
    MEMORY = "memory"  # memory limit exhausted
    OVERSIZE = "oversize"  # input too large (pre-spawn) or output too large
    PARSER_ERROR = "parser_error"  # parser raised or crashed on malformed input
    ENCRYPTED = "encrypted"  # password-protected document
    UNSUPPORTED = "unsupported"  # format the converters cannot handle


@dataclass
class ConversionResult:
    """Outcome of one sandboxed document conversion."""

    ok: bool
    text: Optional[str] = None
    engine: Optional[str] = None
    quarantine_reason: Optional[QuarantineReason] = None
    detail: str = ""
    fallback_used: bool = False
    fallback_from: Optional[str] = None  # primary engine that failed, when fallback_used


def _normalized_media_type(media_type: Optional[str]) -> str:
    """Lowercased MIME type with parameters stripped ('' when absent)."""
    return (media_type or "").lower().split(";")[0].strip()


def _select_engine(filename: str, media_type: Optional[str]) -> str:
    """Deterministic routing by media type / extension.

    PDFs go to pdf-inspector (which classifies native-text vs scanned pages -
    a signal anydoc's PDF path does not expose), anydoc's claimed formats go
    to anydoc, and everything else stays on MarkItDown.
    """
    ext = os.path.splitext(filename)[1].lower()
    media = _normalized_media_type(media_type)
    if ext == ".pdf" or media == "application/pdf":
        return ENGINE_PDF_INSPECTOR
    if ext in ANYDOC_EXTENSIONS or media in _ANYDOC_MEDIA_TYPES:
        return ENGINE_ANYDOC
    return ENGINE_MARKITDOWN


def _select_fallback_engine(engine: str, filename: str, media_type: Optional[str]) -> Optional[str]:
    """The converter to retry with when the primary fails, or None.

    pdf-inspector always falls back to MarkItDown (PDFs must never fail harder
    than before routing existed). anydoc falls back to MarkItDown only for the
    formats MarkItDown supports; anydoc-only formats quarantine honestly.
    """
    if engine == ENGINE_PDF_INSPECTOR:
        return ENGINE_MARKITDOWN
    if engine == ENGINE_ANYDOC:
        ext = os.path.splitext(filename)[1].lower()
        media = _normalized_media_type(media_type)
        if ext in _MARKITDOWN_FALLBACK_EXTENSIONS or media in _MARKITDOWN_FALLBACK_MEDIA_TYPES:
            return ENGINE_MARKITDOWN
    return None


def _safe_suffix(filename: str) -> str:
    """Extension for the temp input file (parsers key off it); sanitized."""
    ext = os.path.splitext(filename)[1].lower()
    if ext and len(ext) <= 10 and all(c.isalnum() or c == "." for c in ext[1:]):
        return ext
    return ".bin"


def _worker_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _PROXY_ENV_VARS}
    # Best-effort: libraries that honor no_proxy will not tunnel through one.
    env["no_proxy"] = "*"
    env["NO_PROXY"] = "*"
    return env


def _classify_signal(sig: int) -> QuarantineReason:
    """Classify a worker killed by a signal (rlimit kills and parser crashes)."""
    # getattr: SIGXCPU/SIGKILL/SIGXFSZ do not exist on Windows, where negative
    # return codes cannot occur anyway (no signal deaths).
    if sig == getattr(signal, "SIGXCPU", -1):
        return QuarantineReason.TIMEOUT
    if sig == getattr(signal, "SIGKILL", -1):
        # RLIMIT_AS hard kill / OOM killer.
        return QuarantineReason.MEMORY
    if sig == getattr(signal, "SIGXFSZ", -1):
        return QuarantineReason.OVERSIZE
    # SIGSEGV/SIGABRT/SIGBUS/...: the parser crashed on hostile input.
    return QuarantineReason.PARSER_ERROR


def _run_worker(
    input_path: str,
    output_path: str,
    engine: str,
    timeout: float,
    memory_limit_bytes: int,
    max_output_bytes: int,
    fallback_engine: Optional[str] = None,
) -> ConversionResult:
    """Spawn one worker process and classify its outcome. Never raises."""
    cmd = [
        sys.executable,
        _WORKER_PATH,
        input_path,
        output_path,
        "--engine",
        engine,
        "--cpu-seconds",
        str(max(1, int(timeout))),
        "--memory-bytes",
        str(memory_limit_bytes),
        "--max-output-bytes",
        str(max_output_bytes),
    ]
    if fallback_engine:
        cmd += ["--fallback-engine", fallback_engine]
    # POSIX: give the worker its own process group so the timeout kill also
    # reaps any helpers it spawned. Windows has neither start_new_session nor
    # os.killpg; a plain kill() of the worker is the fallback there.
    posix = os.name == "posix"
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=_worker_env(),
        cwd=os.path.dirname(input_path),
        start_new_session=posix,
    )
    try:
        _, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill the entire process group where available; the worker may have
        # spawned helpers. Fall back to killing just the worker.
        if posix:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
        else:
            process.kill()
        process.wait()
        return ConversionResult(
            ok=False,
            engine=engine,
            quarantine_reason=QuarantineReason.TIMEOUT,
            detail=f"conversion exceeded {timeout}s wall-clock limit",
        )

    if process.returncode < 0:
        sig = -process.returncode
        return ConversionResult(
            ok=False,
            engine=engine,
            quarantine_reason=_classify_signal(sig),
            detail=f"worker killed by signal {sig}",
        )

    stderr_text = (stderr or b"").decode("utf-8", errors="replace")[-1000:]
    if process.returncode != 0 or not os.path.exists(output_path):
        return ConversionResult(
            ok=False,
            engine=engine,
            quarantine_reason=QuarantineReason.PARSER_ERROR,
            detail=f"worker exited {process.returncode} without a result: {stderr_text}",
        )

    try:
        with open(output_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        return ConversionResult(
            ok=False,
            engine=engine,
            quarantine_reason=QuarantineReason.PARSER_ERROR,
            detail=f"unreadable worker result: {exc}",
        )

    fallback_from = payload.get("fallback_from")
    fallback_used = fallback_from is not None
    if payload.get("ok"):
        return ConversionResult(
            ok=True,
            text=payload.get("text", ""),
            engine=payload.get("engine", engine),
            detail=payload.get("fallback_error") or "",
            fallback_used=fallback_used,
            fallback_from=fallback_from,
        )

    try:
        reason = QuarantineReason(payload.get("reason", "parser_error"))
    except ValueError:
        reason = QuarantineReason.PARSER_ERROR
    return ConversionResult(
        ok=False,
        engine=payload.get("engine", engine),
        quarantine_reason=reason,
        detail=payload.get("detail", ""),
        fallback_used=fallback_used,
        fallback_from=fallback_from,
    )


def convert_document(
    content: bytes,
    filename: str,
    media_type: Optional[str] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES,
) -> ConversionResult:
    """
    Convert an untrusted document to markdown-ish text in a sandboxed subprocess.

    Never raises for bad input: every failure mode is returned as a
    ConversionResult with a QuarantineReason so callers keep their existing
    graceful-degradation behavior.

    Args:
        content: Raw document bytes (untrusted).
        filename: Original filename; its extension drives parser selection.
        media_type: Optional MIME type; application/pdf routes to pdf-inspector,
            office/OpenDocument/RTF/EPUB/CSV types route to anydoc.
        timeout: Wall-clock ceiling for the conversion.
        max_input_bytes: Inputs larger than this are rejected before spawning.
        max_output_bytes: Converted text larger than this is quarantined.
        memory_limit_bytes: Worker address-space limit (enforced on Linux).

    Returns:
        ConversionResult with the converted text or a quarantine reason.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")

    started = time.monotonic()
    if len(content) > max_input_bytes:
        result = ConversionResult(
            ok=False,
            engine=None,
            quarantine_reason=QuarantineReason.OVERSIZE,
            detail=f"input is {len(content)} bytes; limit is {max_input_bytes}",
        )
        _observe_outcome(result, filename, len(content), started)
        return result

    engine = _select_engine(filename, media_type)
    fallback_engine = _select_fallback_engine(engine, filename, media_type)

    try:
        with tempfile.TemporaryDirectory(prefix="muxi_docconv_") as workdir:
            input_path = os.path.join(workdir, f"input{_safe_suffix(filename)}")
            output_path = os.path.join(workdir, "result.json")
            with open(input_path, "wb") as handle:
                handle.write(content)

            result = _run_worker(
                input_path,
                output_path,
                engine,
                timeout,
                memory_limit_bytes,
                max_output_bytes,
                fallback_engine=fallback_engine,
            )

            # If the primary converter crashed the worker outright (signal
            # death, so the in-worker fallback never ran), retry once with the
            # fallback engine - the file must never fail harder than it did
            # when that engine was primary.
            if (
                not result.ok
                and fallback_engine
                and result.quarantine_reason == QuarantineReason.PARSER_ERROR
                and not os.path.exists(output_path)
            ):
                crash_detail = result.detail
                retry = _run_worker(
                    input_path,
                    output_path,
                    fallback_engine,
                    timeout,
                    memory_limit_bytes,
                    max_output_bytes,
                )
                retry.fallback_used = True
                retry.fallback_from = engine
                retry.detail = f"{engine} worker crashed ({crash_detail}); {retry.detail}"
                result = retry
    except Exception as exc:  # noqa: BLE001 - service must never leak exceptions
        result = ConversionResult(
            ok=False,
            engine=engine,
            quarantine_reason=QuarantineReason.PARSER_ERROR,
            detail=f"conversion service error: {type(exc).__name__}: {exc}",
        )

    _observe_outcome(result, filename, len(content), started)
    return result


async def convert_document_async(
    content: bytes,
    filename: str,
    media_type: Optional[str] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES,
) -> ConversionResult:
    """Async wrapper around convert_document; runs the blocking wait off-loop."""
    return await asyncio.to_thread(
        convert_document,
        content,
        filename,
        media_type,
        timeout=timeout,
        max_input_bytes=max_input_bytes,
        max_output_bytes=max_output_bytes,
        memory_limit_bytes=memory_limit_bytes,
    )


def _observe_outcome(
    result: ConversionResult, filename: str, input_bytes: int, started: float
) -> None:
    """Emit the conversion outcome (and any primary-converter fallback) as events."""
    duration_ms = int((time.monotonic() - started) * 1000)
    base_data = {
        "filename": filename,
        "engine": result.engine,
        "input_bytes": input_bytes,
        "duration_ms": duration_ms,
    }

    if result.fallback_used:
        primary = result.fallback_from or ENGINE_PDF_INSPECTOR
        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_CONVERSION_FALLBACK,
            level=observability.EventLevel.WARNING,
            data={
                **base_data,
                # fallback_from predates primary/fallback; kept for consumers.
                "fallback_from": primary,
                "primary": primary,
                "fallback": result.engine,
                "error": result.detail,
            },
            description=f"{primary} failed for {filename}; fell back to {result.engine}",
        )

    if result.ok:
        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_CONVERSION_COMPLETED,
            level=observability.EventLevel.INFO,
            data={**base_data, "output_chars": len(result.text or "")},
            description=f"Converted {filename} via {result.engine}",
        )
    else:
        reason = result.quarantine_reason.value if result.quarantine_reason else "unknown"
        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_CONVERSION_QUARANTINED,
            level=observability.EventLevel.WARNING,
            data={**base_data, "quarantine_reason": reason, "detail": result.detail},
            description=f"Quarantined {filename} ({reason})",
        )
