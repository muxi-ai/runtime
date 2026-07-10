"""
Coding-CLI command assembly and output parsing.

Command assembly is an exec array, never a shell -- there is no injection
surface. Assembly order (PRD): command + args.base + args.model (when a
model value is set) + session fragment + extra_args + args.prompt (unless
``prompt: stdin``, in which case the prompt is written to the subprocess's
stdin -- required for long prompts past argv limits).

Output parsing reuses the triggers ``parse:`` idiom: the ``output:`` enum
selects the parser, and the adapter's ``parse.result``/``parse.session_id``
selectors (``extract_path``) pull values from the vendor's JSON.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ...formation.background.transformers import extract_path
from .config import AdapterConfig

# Cost metadata key captured onto the job record when the vendor reports it
# (claude-code's terminal result event carries total_cost_usd).
_COST_KEYS = ("total_cost_usd", "cost_usd")


def _substitute(fragment: List[str], placeholder: str, value: str) -> List[str]:
    return [part.replace(placeholder, value) for part in fragment]


def build_command(
    adapter: AdapterConfig,
    *,
    prompt: str,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
    resume: bool = False,
    extra_args: Optional[List[str]] = None,
) -> Tuple[List[str], Optional[str]]:
    """
    Assemble the exec array for one delegation.

    Returns ``(argv, stdin_payload)``; ``stdin_payload`` is the prompt when
    the adapter declares ``prompt: stdin``, else None.

    Session fragment selection:
    - idempotent ``session``: used for create AND resume (same flag)
    - ``session_new``/``session_resume`` pair: picked by ``resume``
    - ``session_resume`` only (tool-assigned ids): the first delegation runs
      with NO session flag (``session_id`` is None); resume applies the flag
      with the captured id
    """
    argv: List[str] = [adapter.command]
    argv.extend(adapter.base)

    if model:
        if adapter.model is None:
            raise ValueError("adapter defines no args.model fragment but a model was supplied")
        argv.extend(_substitute(adapter.model, "{model}", model))

    if session_id:
        if adapter.session is not None:
            fragment = adapter.session
        elif resume:
            fragment = adapter.session_resume
        else:
            fragment = adapter.session_new
        if fragment:
            argv.extend(_substitute(fragment, "{id}", session_id))

    if extra_args:
        argv.extend(extra_args)

    stdin_payload: Optional[str] = None
    if adapter.prompt == "stdin":
        stdin_payload = prompt
    else:
        argv.extend(_substitute(list(adapter.prompt), "{prompt}", prompt))

    return argv, stdin_payload


@dataclass
class ParsedOutput:
    """What the runtime extracts from a finished CLI run."""

    result: str = ""
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    event_count: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)


def _extract_cost(document: Dict[str, Any]) -> Optional[float]:
    for key in _COST_KEYS:
        value = document.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _apply_selectors(adapter: AdapterConfig, document: Dict[str, Any], parsed: ParsedOutput):
    """Apply the adapter's parse selectors to one JSON document (last wins)."""
    if adapter.parse_result:
        value = extract_path(document, adapter.parse_result)
        if value is not None:
            parsed.result = value if isinstance(value, str) else json.dumps(value)
    if adapter.parse_session_id:
        value = extract_path(document, adapter.parse_session_id)
        if isinstance(value, str) and value.strip():
            parsed.session_id = value.strip()
    cost = _extract_cost(document)
    if cost is not None:
        parsed.cost_usd = cost


def parse_stream_json_line(line: str) -> Optional[Dict[str, Any]]:
    """One JSONL event, or None for blank/unparseable lines (skipped)."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        document = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def parse_output(adapter: AdapterConfig, stdout: str) -> ParsedOutput:
    """
    Parse the full stdout of a finished run according to the output mode.

    - ``stream-json``: JSONL -- every parseable event is retained (the
      service also observes them incrementally as DELEGATION_PROGRESS);
      selectors apply to each event, last non-empty extraction wins (the
      terminal event carries the result).
    - ``json``: a single document on exit; selectors apply to it. Defensive
      fallback: when the whole stdout is not one document, the last
      parseable line wins (some CLIs prepend informational lines).
    - ``text``: opaque -- full stdout is the result; no session capture.

    When a selector extracts nothing, the raw stdout is kept as the result
    so a completed run never reports an empty outcome.
    """
    parsed = ParsedOutput()

    if adapter.output == "text":
        parsed.result = stdout
        return parsed

    if adapter.output == "stream-json":
        for line in stdout.splitlines():
            document = parse_stream_json_line(line)
            if document is None:
                continue
            parsed.events.append(document)
            parsed.event_count += 1
            _apply_selectors(adapter, document, parsed)
        if not parsed.result:
            parsed.result = stdout
        return parsed

    # output == "json": one document, with a last-parseable-line fallback.
    document: Optional[Dict[str, Any]] = None
    try:
        candidate = json.loads(stdout.strip())
        if isinstance(candidate, dict):
            document = candidate
    except (json.JSONDecodeError, ValueError):
        for line in reversed(stdout.splitlines()):
            candidate = parse_stream_json_line(line)
            if candidate is not None:
                document = candidate
                break
    if document is not None:
        parsed.events.append(document)
        parsed.event_count = 1
        _apply_selectors(adapter, document, parsed)
    if not parsed.result:
        parsed.result = stdout
    return parsed
