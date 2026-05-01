"""MCP tool error translation — Layer 2 of the MCP param funnel.

When an upstream MCP server returns an error whose surface text is
misleading about the actual cause, this module annotates the result
with an agent-actionable hint. The hint reaches the agent on the next
turn via the tool message, giving the model a concrete correction
path instead of forcing it to reason from a confusing upstream error.

Concrete motivating case (Findings 4 and 6 from the 2026-04-29
scheduler/MS365 testing run): when an Excel endpoint receives a
driveItemId that points to a folder rather than a workbook, Microsoft
Graph returns ``"Could not obtain a WAC access token"``. Read at face
value, this looks like an auth failure — and the agent has been
observed surfacing it to the user as a permissions problem rather
than re-resolving the file ID. The runtime cannot disambiguate
folder-vs-file inside a generic list response (that's per-server
semantics), but it CAN spot the misleading error pattern after the
fact and tell the agent what likely happened.

Design notes:

* Pattern registry is a frozen tuple of dataclass instances. New
  patterns get appended to the registry; ordering matters
  (first-match-wins) but the file is small enough that the order is
  reviewable in one screen.
* Each pattern gates on three signals: a content regex (what the
  upstream said), a required-arg-key set (what the agent passed —
  prevents matching text from unrelated tools), and an optional
  server_id regex (when a pattern is server-specific).
* The translator never blocks the call. It only annotates an existing
  failure with extra context. This keeps the runtime agnostic about
  whether a particular pattern is a true positive — at worst, the
  agent reads an extra sentence and ignores it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Sequence


@dataclass(frozen=True)
class ErrorTranslation:
    """Outcome of a successful pattern match.

    ``category`` is a stable identifier suitable for grouping in
    observability dashboards; ``hint`` is the agent-readable
    correction text that gets appended to the upstream error content.
    """

    category: str
    hint: str


@dataclass(frozen=True)
class _ErrorPattern:
    """Internal pattern declaration. Not exported.

    Three signals, all of which must match for the pattern to fire:

    * ``content_regex`` — case-insensitive search across the upstream
      error text.
    * ``required_arg_keys`` — at least one of these argument keys
      must be present in the tool call. Empty tuple disables the
      gate. Prevents matching error text from unrelated tool calls.
    * ``server_id_regex`` — optional. When set, the pattern only
      fires for servers whose id matches. Default ``None`` means the
      pattern is server-agnostic.
    """

    category: str
    content_regex: re.Pattern[str]
    required_arg_keys: tuple[str, ...]
    hint: str
    server_id_regex: Optional[re.Pattern[str]] = None


_PATTERNS: Sequence[_ErrorPattern] = (
    _ErrorPattern(
        category="excel_wac_token_folder_id",
        content_regex=re.compile(r"could not obtain a wac access token", re.IGNORECASE),
        required_arg_keys=("driveItemId", "file_id"),
        hint=(
            "Likely cause: the supplied driveItemId/file_id refers to a folder "
            "rather than a workbook (.xlsx) file. Microsoft Graph Excel "
            "endpoints return this WAC error when the target item is a "
            "folder. Re-resolve the workbook ID via list-folder-files (or "
            "the equivalent listing tool) and select the item whose name "
            "ends in '.xlsx' — not a folder such as 'Attachments'."
        ),
    ),
)


def translate_tool_error(
    tool_name: str,
    arguments: Optional[Dict[str, object]],
    error_text: Optional[str],
    server_id: Optional[str] = None,
) -> Optional[ErrorTranslation]:
    """Match an MCP tool error against the registry.

    Returns the first matching :class:`ErrorTranslation`, or ``None``
    if no pattern fires. Always safe to call: empty/missing inputs
    short-circuit to ``None`` rather than raising.

    Callers should still gate invocation on the result actually being
    an error (``isError`` true or ``status == "error"``) so the
    translator never runs on a success body that happens to contain
    matching strings.

    Args:
        tool_name: Name of the upstream MCP tool. Currently unused
            for matching but reserved for future per-tool patterns.
            The calling site in ``service.py`` also emits ``tool_name``
            as part of the ``MCP_TOOL_CALL_COMPLETED`` event — that
            emission is independent of whether a translation fires
            and is not driven by this function.
        arguments: Arguments dict the agent passed to the tool. Used
            to gate patterns by required arg keys.
        error_text: Flattened content text from the upstream error
            response. Treated as a single haystack — pattern regexes
            run against this with ``IGNORECASE``.
        server_id: Optional MCP server id. Used to gate
            server-specific patterns.

    Returns:
        First matching translation, or ``None``.
    """
    if not error_text or not error_text.strip():
        return None

    arg_keys = set(arguments.keys()) if isinstance(arguments, dict) else set()

    for pattern in _PATTERNS:
        if pattern.server_id_regex is not None:
            if not server_id or not pattern.server_id_regex.search(server_id):
                continue
        if pattern.required_arg_keys and not arg_keys.intersection(pattern.required_arg_keys):
            continue
        if pattern.content_regex.search(error_text):
            return ErrorTranslation(category=pattern.category, hint=pattern.hint)

    return None
