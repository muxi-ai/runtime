# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Document Conversion Worker - Sandboxed Subprocess Entry Point
# Description:  Converts one untrusted document inside a resource-limited process
# Role:         Executed by document_converter.py in a spawned subprocess
# Usage:        python conversion_worker.py <input> <output> --engine ... (internal)
# Author:       Muxi Framework Team
#
# This script is the *only* code that touches untrusted document bytes with a
# parser (anydoc, pdf-inspector, or MarkItDown). It is executed by file path
# (never imported) so the muxi package import chain is skipped and the process
# stays small and fast to spawn.
#
# Isolation model (v1, honest limits):
#   - Process boundary: parser crashes/hangs kill this process, not the runtime.
#   - resource.setrlimit (POSIX only): CPU seconds, address space (Linux only -
#     RLIMIT_AS is unreliable on macOS), and output file size (RLIMIT_FSIZE).
#     On Windows the resource module does not exist, so no rlimits apply; the
#     parent's wall-clock timeout and the explicit output-length check are the
#     enforced limits there.
#   - The parent enforces a hard wall-clock timeout and kills the process group
#     (plain kill on platforms without process groups).
#   - Network isolation is best-effort only: proxy env vars are stripped by the
#     parent, but there is no network namespace/seccomp on a plain POSIX host.
#     The subprocess CAN technically open sockets; the win at this layer is
#     crash/hang/memory containment, not egress control.
#
# Every handled outcome - success or quarantine - is written as JSON to the
# output path and the process exits 0. Unhandled deaths (signals, rlimit kills)
# are classified by the parent from the exit status.
#
# IMPORTANT: stdlib-only imports at module level. Parser libraries are imported
# lazily so import failures are reported as structured quarantine results.
# =============================================================================

import argparse
import json
import sys

try:
    import resource  # POSIX only; unavailable on Windows
except ImportError:  # pragma: no cover - Windows
    resource = None

ENGINE_PDF_INSPECTOR = "pdf_inspector"
ENGINE_MARKITDOWN = "markitdown"
ENGINE_ANYDOC = "anydoc"

# QuarantineReason values (mirrored from document_converter.QuarantineReason;
# this file cannot import muxi modules).
REASON_MEMORY = "memory"
REASON_OVERSIZE = "oversize"
REASON_PARSER_ERROR = "parser_error"
REASON_ENCRYPTED = "encrypted"
REASON_UNSUPPORTED = "unsupported"


def _apply_rlimits(cpu_seconds: int, memory_bytes: int, max_output_bytes: int) -> None:
    """Apply resource limits to this process before any parsing happens."""
    if resource is None:
        # Windows: no rlimits available. The parent's wall-clock timeout and
        # the explicit output-length check below are the only limits enforced.
        return
    # CPU time: hard backstop against parser infinite loops even if the parent
    # dies before its wall-clock timeout fires. SIGXCPU at soft, SIGKILL at hard.
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
    except (ValueError, OSError):
        pass
    # Address space: Linux only. On macOS RLIMIT_AS is not reliably enforced,
    # and the artifact sandbox learned the hard way that pretending otherwise
    # just produces confusing hangs (see AGENTS.md troubleshooting notes).
    if sys.platform.startswith("linux"):
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except (ValueError, OSError):
            pass
    # Output file size: enforced on all platforms. A decompression bomb that
    # slips past the explicit length check below dies on SIGXFSZ.
    try:
        fsize = max_output_bytes * 2  # JSON escaping overhead
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
    except (ValueError, OSError):
        pass


def _classify_exception(exc: Exception) -> str:
    """Map a parser exception to a quarantine reason string."""
    text = f"{type(exc).__name__}: {exc}".lower()
    if "encrypt" in text or "password" in text:
        return REASON_ENCRYPTED
    if "unsupported" in text:
        return REASON_UNSUPPORTED
    return REASON_PARSER_ERROR


def _convert_with_markitdown(input_path: str) -> str:
    from markitdown import MarkItDown

    return MarkItDown().convert(input_path).text_content


def _convert_with_pdf_inspector(input_path: str) -> str:
    import pdf_inspector

    return pdf_inspector.process_pdf(input_path).markdown


def _convert_with_anydoc(input_path: str) -> str:
    import anydoc

    # Format is detected from the file content; the temp file's sanitized
    # extension is the fallback for signature-less formats (CSV).
    return anydoc.to_markdown(input_path)


_CONVERTERS = {
    ENGINE_PDF_INSPECTOR: _convert_with_pdf_inspector,
    ENGINE_MARKITDOWN: _convert_with_markitdown,
    ENGINE_ANYDOC: _convert_with_anydoc,
}


def _has_text(value) -> bool:
    """True when a converter actually extracted something usable.

    Converters signal an unreadable file either by raising or by returning
    nothing at all; this collapses the second form to a single predicate.
    """
    return value is not None and str(value).strip() != ""


def _convert(engine: str, fallback_engine, input_path: str, max_output_bytes: int) -> dict:
    """Run the conversion, returning a result dict (never raising for parser errors)."""
    fallback_from = None
    fallback_error = None
    engine_used = engine

    try:
        try:
            text = _CONVERTERS[engine](input_path)
        except MemoryError:
            raise
        except Exception as primary_exc:  # noqa: BLE001 - untrusted input boundary
            if not fallback_engine:
                # No converter can retry this format; classify the primary
                # failure honestly instead of pretending a fallback ran.
                raise
            # The primary converter could not handle this file; fall back to
            # the sandboxed secondary so we never fail harder than before.
            fallback_from = engine
            fallback_error = f"{type(primary_exc).__name__}: {primary_exc}"
            engine_used = fallback_engine
            text = _CONVERTERS[fallback_engine](input_path)
        else:
            # A raised exception is not the only way a converter reports that
            # it cannot read a file: pdf-inspector >= 0.2.7 and anydoc >= 0.2.3
            # return empty output instead. Treat "succeeded but produced
            # nothing" as a primary failure too, so it still reaches the
            # fallback -- otherwise a file that used to convert (via the
            # fallback) starts quarantining as parser_error, which is exactly
            # the "never fail harder than before" guarantee this path exists
            # to keep.
            if not _has_text(text) and fallback_engine:
                fallback_from = engine
                fallback_error = "primary converter produced no text"
                engine_used = fallback_engine
                text = _CONVERTERS[fallback_engine](input_path)
    except MemoryError:
        return {
            "ok": False,
            "reason": REASON_MEMORY,
            "detail": "parser exhausted the memory limit",
            "engine": engine_used,
            "fallback_from": fallback_from,
            "fallback_error": fallback_error,
        }
    except Exception as exc:  # noqa: BLE001 - untrusted input boundary
        return {
            "ok": False,
            "reason": _classify_exception(exc),
            "detail": f"{type(exc).__name__}: {exc}"[:2000],
            "engine": engine_used,
            "fallback_from": fallback_from,
            "fallback_error": fallback_error,
        }

    if not _has_text(text):
        # Converters report "I could not read this" by returning nothing --
        # MarkItDown as None text_content, pdf-inspector/anydoc as empty
        # output. Either way nothing was extracted, and by this point the
        # fallback (if any) has already had its turn.
        return {
            "ok": False,
            "reason": REASON_PARSER_ERROR,
            "detail": "converter produced no text",
            "engine": engine_used,
            "fallback_from": fallback_from,
            "fallback_error": fallback_error,
        }
    text = text if isinstance(text, str) else str(text)
    if len(text.encode("utf-8", errors="replace")) > max_output_bytes:
        return {
            "ok": False,
            "reason": REASON_OVERSIZE,
            "detail": f"converted output exceeds {max_output_bytes} bytes",
            "engine": engine_used,
            "fallback_from": fallback_from,
            "fallback_error": fallback_error,
        }

    return {
        "ok": True,
        "text": text,
        "engine": engine_used,
        "fallback_from": fallback_from,
        "fallback_error": fallback_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sandboxed document conversion worker")
    parser.add_argument("input_path")
    parser.add_argument("output_path")
    parser.add_argument("--engine", choices=sorted(_CONVERTERS), required=True)
    parser.add_argument(
        "--fallback-engine",
        choices=sorted(_CONVERTERS),
        default=None,
        help="Converter to retry with in-process when the primary engine raises",
    )
    parser.add_argument("--cpu-seconds", type=int, required=True)
    parser.add_argument("--memory-bytes", type=int, required=True)
    parser.add_argument("--max-output-bytes", type=int, required=True)
    args = parser.parse_args()

    _apply_rlimits(args.cpu_seconds, args.memory_bytes, args.max_output_bytes)
    result = _convert(args.engine, args.fallback_engine, args.input_path, args.max_output_bytes)

    with open(args.output_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
