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
# native-text path runs locally and emits structured markdown. Everything else
# stays on MarkItDown - now inside the same sandbox. If pdf-inspector fails on
# a given PDF the worker falls back to sandboxed MarkItDown for that file, so
# PDFs never fail harder than they did before routing existed.
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

# Extensions the chat-attachment path converts (unchanged from the previous
# in-process MarkItDown gate in overlord.py).
ATTACHMENT_CONVERTIBLE_EXTENSIONS = [".pdf", ".docx", ".pptx", ".xlsx", ".html"]

ENGINE_PDF_INSPECTOR = "pdf_inspector"
ENGINE_MARKITDOWN = "markitdown"

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


def _select_engine(filename: str, media_type: Optional[str]) -> str:
    """Deterministic routing by media type / extension: PDFs to pdf-inspector."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf" or (media_type or "").lower().split(";")[0].strip() == "application/pdf":
        return ENGINE_PDF_INSPECTOR
    return ENGINE_MARKITDOWN


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

    fallback_used = payload.get("fallback_from") is not None
    if payload.get("ok"):
        return ConversionResult(
            ok=True,
            text=payload.get("text", ""),
            engine=payload.get("engine", engine),
            detail=payload.get("fallback_error") or "",
            fallback_used=fallback_used,
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
        media_type: Optional MIME type; application/pdf routes to pdf-inspector.
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
            )

            # If pdf-inspector crashed the worker outright (signal death, so the
            # in-worker MarkItDown fallback never ran), retry once with
            # MarkItDown - PDFs must never fail harder than before routing.
            if (
                not result.ok
                and engine == ENGINE_PDF_INSPECTOR
                and result.quarantine_reason == QuarantineReason.PARSER_ERROR
                and not os.path.exists(output_path)
            ):
                retry = _run_worker(
                    input_path,
                    output_path,
                    ENGINE_MARKITDOWN,
                    timeout,
                    memory_limit_bytes,
                    max_output_bytes,
                )
                retry.fallback_used = True
                retry.detail = f"pdf_inspector worker crashed ({result.detail}); {retry.detail}"
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
    """Emit the conversion outcome (and any pdf-inspector fallback) as events."""
    duration_ms = int((time.monotonic() - started) * 1000)
    base_data = {
        "filename": filename,
        "engine": result.engine,
        "input_bytes": input_bytes,
        "duration_ms": duration_ms,
    }

    if result.fallback_used:
        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_CONVERSION_FALLBACK,
            level=observability.EventLevel.WARNING,
            data={**base_data, "fallback_from": ENGINE_PDF_INSPECTOR, "error": result.detail},
            description=f"pdf-inspector failed for {filename}; fell back to MarkItDown",
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
