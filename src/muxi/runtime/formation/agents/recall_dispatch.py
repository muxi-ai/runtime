"""Dispatch handlers for the recall_history built-in tool.

Episodic memory (time-anchored retrieval): recall_history lets any agent
turn a date-anchored recall question ("what did we discuss last Tuesday?")
into a date-ranged query over the user's captain's log entries -- the
narrative digests the daily tick, buffer-pressure flush, and session-end
sweep already persist. The tool is only registered when the overlord
carries an enabled CaptainsLogService -- formations without the captain's
log see no tool at all.

Read-only and user-scoped: handlers only ever see the calling user's log
entries (the same per-request user identity the memory routes resolve),
and every failure returns a friendly ``{"success": False, "error": ...}``
the model can act on instead of raising into the turn.
"""

from typing import Any, Dict, List, Optional

from ...services import observability

_RECALL_LIMIT_DEFAULT = 10
_RECALL_LIMIT_MAX = 30

# Keyword-filtered recalls apply their predicate in Python, so they scan at
# most this many of the newest in-range entries (artifact_dispatch idiom).
_RECALL_SCAN_CAP = 100


def recall_tools_available(overlord: Any) -> bool:
    """Whether the recall_history tool should exist for this formation."""
    service = getattr(overlord, "captains_log", None)
    return service is not None and bool(getattr(service, "enabled", False))


def build_recall_tools() -> List[Dict[str, Any]]:
    """Tool definition for the recall_history built-in."""
    return [
        {
            "type": "function",
            "function": {
                "name": "recall_history",
                "description": (
                    "Recall what was previously discussed with this user by date. "
                    "Returns dated summaries of past conversations (decisions, "
                    "projects, context) from the user's conversation journal, "
                    "newest first. Use this for time-anchored recall questions "
                    "like 'what did we discuss last Tuesday' or 'what did we "
                    "decide in March' -- resolve relative phrases to ISO dates "
                    "(YYYY-MM-DD) first and pass them as date_from/date_to "
                    "(use the same date for both to recall a single day)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date_from": {
                            "type": "string",
                            "description": "Earliest entry date, ISO format (YYYY-MM-DD)",
                        },
                        "date_to": {
                            "type": "string",
                            "description": "Latest entry date, ISO format (YYYY-MM-DD)",
                        },
                        "query": {
                            "type": "string",
                            "description": (
                                "Optional keyword filter matched against the "
                                "entries' summaries, decisions, and projects"
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum entries returned (default 10, max 30)",
                        },
                    },
                },
            },
        },
    ]


def _service_or_none(overlord: Any):
    """The enabled captain's log service, or None."""
    service = getattr(overlord, "captains_log", None)
    if service is None or not getattr(service, "enabled", False):
        return None
    return service


def _effective_user(user_id: Optional[str]) -> str:
    """Normalize the calling user id (single-user runtimes pass None)."""
    return str(user_id) if user_id is not None else "0"


def _parse_iso_date_strict(value: Any, field: str) -> Optional[str]:
    """Validate an ISO date parameter; raises ValueError with the field name.

    Unlike the service's lenient parser (which silently drops invalid
    dates), the tool rejects malformed input so the model can correct
    itself instead of receiving a silently unfiltered result.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    from datetime import date

    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}")


def _tool_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The entry subset a model needs (no storage internals)."""
    return {
        "date": entry["date"],
        "summary": entry["summary"],
        "decisions": entry["decisions"] or [],
        "projects": entry["projects"] or [],
        "context": entry["context"],
    }


def _matches_query(entry: Dict[str, Any], query: str) -> bool:
    """Lexical match over an entry's narrative fields."""
    haystack = " ".join(
        [entry.get("summary") or "", entry.get("context") or ""]
        + [str(item) for item in (entry.get("decisions") or [])]
        + [str(item) for item in (entry.get("projects") or [])]
    ).lower()
    return query in haystack


async def handle_recall_history(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle the recall_history tool call (date-ranged log retrieval)."""
    service = _service_or_none(overlord)
    if service is None:
        return {"success": False, "error": "Conversation history is not available"}
    user_id = _effective_user(user_id)

    try:
        date_from = _parse_iso_date_strict(parameters.get("date_from"), "date_from")
        date_to = _parse_iso_date_strict(parameters.get("date_to"), "date_to")
    except ValueError as e:
        return {"success": False, "error": str(e)}
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    query = (parameters.get("query") or "").strip().lower()
    try:
        limit = int(parameters.get("limit") or _RECALL_LIMIT_DEFAULT)
    except (TypeError, ValueError):
        limit = _RECALL_LIMIT_DEFAULT
    limit = max(1, min(limit, _RECALL_LIMIT_MAX))

    try:
        # Unfiltered recalls need exactly ``limit`` rows; the keyword
        # filter is applied in Python, so filtered recalls scan a bounded
        # window of the newest in-range entries.
        fetch_limit = limit if not query else _RECALL_SCAN_CAP
        entries = await service.get_history(
            user_id, limit=fetch_limit, date_from=date_from, date_to=date_to
        )
        matches = []
        for entry in entries:
            if query and not _matches_query(entry, query):
                continue
            matches.append(_tool_entry(entry))
            if len(matches) >= limit:
                break

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
            level=observability.EventLevel.DEBUG,
            data={
                "agent_id": agent_id,
                "user_id": user_id,
                "tool_name": "recall_history",
                "component": "captains_log",
                "date_from": date_from,
                "date_to": date_to,
                "matched": len(matches),
            },
            description=f"Recalled {len(matches)} log entrie(s) via recall_history",
        )
        result = {"success": True, "entries": matches, "count": len(matches)}
        if not matches:
            result["message"] = (
                "No conversation history recorded for this date range; "
                "try widening the range or dropping the query filter"
            )
        return result
    except Exception as e:
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVAL_FAILED,
            level=observability.EventLevel.WARNING,
            data={
                "agent_id": agent_id,
                "user_id": user_id,
                "tool_name": "recall_history",
                "component": "captains_log",
                "error": str(e),
                "error_type": type(e).__name__,
            },
            description=f"recall_history retrieval failed: {e}",
        )
        return {"success": False, "error": f"History recall failed: {e}"}
