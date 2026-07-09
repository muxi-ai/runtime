"""Dispatch handlers for the artifact retrieval built-in tools.

Artifact Memory Phase 2 ("use the data"): get_artifact, get_artifact_content,
and get_artifact_history let any agent discover and retrieve the produced
work Phase 1 captures, scoped to the calling user. The tools are only
registered when the overlord carries an enabled ArtifactMemoryService
(persistent memory configured, artifacts not disabled) -- formations
without artifact memory see no tools at all.

Failure isolation: handlers never raise into a turn; every failure returns
a friendly ``{"success": False, "error": ...}`` the model can act on.

Semantic search over artifact summaries is deferred to the embedding
platform phase (capture-time summaries are deterministic and unembedded);
``get_artifact``'s ``query`` parameter does lexical matching over name,
summary, and tags until then.
"""

from typing import Any, Dict, List, Optional

from ...services import observability

# Content preview length for get_artifact id lookups (PRD 2.2).
PREVIEW_CHARS = 500

# Hard cap on content returned into model context by get_artifact_content.
# Larger artifacts are truncated with a marker; full content stays
# available through the REST read endpoint.
MAX_CONTENT_CHARS = 50_000

# MIME types (beyond text/*) whose content is safe to render as text.
_TEXTUAL_MIME_TYPES = {
    "application/json",
    "application/x-yaml",
    "application/xml",
    "application/javascript",
    "application/sql",
}

_SEARCH_LIMIT_DEFAULT = 5
_SEARCH_LIMIT_MAX = 20


def artifact_tools_available(overlord: Any) -> bool:
    """Whether the artifact retrieval tools should exist for this formation."""
    service = getattr(overlord, "artifact_memory", None)
    return service is not None and bool(getattr(service, "enabled", False))


def build_artifact_tools() -> List[Dict[str, Any]]:
    """Tool definitions for the three artifact retrieval built-ins."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_artifact",
                "description": (
                    "Look up stored artifacts (files and documents previously produced "
                    "in this formation). Pass 'id' to fetch one artifact's metadata plus "
                    "a content preview, or use 'query'/'category' to search the user's "
                    "artifacts by name, summary, or tags. Use get_artifact_content for "
                    "the full content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Artifact id (from the artifact manifest or a search)",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search text matched against name, summary, and tags",
                        },
                        "category": {
                            "type": "string",
                            "description": (
                                "Filter by category (e.g. text, document, image, data)"
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum search results (default 5, max 20)",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_artifact_content",
                "description": (
                    "Retrieve the full content of a stored artifact by id. Optionally "
                    "pass 'version' to read a specific version from the artifact's "
                    "history instead of the version the id points at."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Artifact id",
                        },
                        "version": {
                            "type": "integer",
                            "description": "Specific version number (default: the id's version)",
                        },
                    },
                    "required": ["id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_artifact_history",
                "description": (
                    "List the full version history of a stored artifact (any version's "
                    "id resolves the whole chain): version numbers, summaries, creation "
                    "times, and the agent that produced each version."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Artifact id (any version in the chain)",
                        },
                    },
                    "required": ["id"],
                },
            },
        },
    ]


def _service_or_none(overlord: Any):
    """The enabled artifact memory service, or None."""
    service = getattr(overlord, "artifact_memory", None)
    if service is None or not getattr(service, "enabled", False):
        return None
    return service


def _effective_user(user_id: Optional[str]) -> str:
    """Normalize the calling user id (single-user runtimes pass None)."""
    return str(user_id) if user_id is not None else "0"


def _tool_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """The metadata subset a model needs (no storage internals)."""
    return {
        "id": row["public_id"],
        "name": row["name"],
        "version": row["version"],
        "is_latest": row["is_latest"],
        "content_type": row["content_type"],
        "category": row["category"],
        "summary": row["summary"],
        "tags": row.get("tags") or [],
        "agent": row["agent_id"] or "overlord",
        "size_bytes": row["size_bytes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _is_textual(content_type: str) -> bool:
    """Whether a MIME type's content renders as text in model context."""
    if content_type.startswith("text/"):
        return True
    if content_type in _TEXTUAL_MIME_TYPES:
        return True
    return content_type.endswith("+json") or content_type.endswith("+xml")


def _decode_text(content: bytes, content_type: str) -> Optional[str]:
    """Decode artifact bytes to text, or None when it is binary content."""
    if not _is_textual(content_type):
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _observe_retrieved(agent_id: str, user_id: str, tool_name: str, **data: Any) -> None:
    observability.observe(
        event_type=observability.ConversationEvents.MEMORY_ARTIFACT_RETRIEVED,
        level=observability.EventLevel.INFO,
        data={"agent_id": agent_id, "user_id": user_id, "tool_name": tool_name, **data},
        description=f"Artifact retrieval via {tool_name} for agent '{agent_id}'",
    )


def _observe_failed(agent_id: str, user_id: str, tool_name: str, error: Exception) -> None:
    observability.observe(
        event_type=observability.ConversationEvents.MEMORY_ARTIFACT_RETRIEVAL_FAILED,
        level=observability.EventLevel.WARNING,
        data={
            "agent_id": agent_id,
            "user_id": user_id,
            "tool_name": tool_name,
            "error": str(error),
            "error_type": type(error).__name__,
        },
        description=f"Artifact retrieval via {tool_name} failed: {error}",
    )


async def handle_get_artifact(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle the get_artifact tool call (id lookup or lexical search)."""
    service = _service_or_none(overlord)
    if service is None:
        return {"success": False, "error": "Artifact memory is not available in this formation"}
    user_id = _effective_user(user_id)

    try:
        artifact_id = (parameters.get("id") or "").strip()
        if artifact_id:
            return await _get_one_artifact(service, agent_id, user_id, artifact_id)
        return await _search_artifacts(service, agent_id, user_id, parameters)
    except Exception as e:
        _observe_failed(agent_id, user_id, "get_artifact", e)
        return {"success": False, "error": f"Artifact lookup failed: {e}"}


async def _get_one_artifact(
    service: Any, agent_id: str, user_id: str, artifact_id: str
) -> Dict[str, Any]:
    """Single-id lookup: metadata plus a content preview when textual."""
    row = await service.get_metadata(user_id, artifact_id)
    if row is None:
        return {
            "success": False,
            "error": f"No artifact with id '{artifact_id}' found for this user",
        }

    result = {"success": True, "artifact": _tool_row(row)}
    try:
        # Content preview counts as access: read_content refreshes
        # last_accessed_at (and the last_accessed retention expiry).
        content = await service.read_content(user_id, artifact_id)
        text = _decode_text(content, row["content_type"])
        if text is None:
            result["content_preview"] = None
            result["note"] = (
                "Binary content; use get_artifact_content metadata or the "
                "/v1/artifacts REST endpoint to deliver the file itself"
            )
        else:
            result["content_preview"] = text[:PREVIEW_CHARS]
    except Exception:
        # Metadata alone is still useful; a preview failure is not fatal.
        result["content_preview"] = None
        result["note"] = "Content preview unavailable"

    _observe_retrieved(agent_id, user_id, "get_artifact", artifact_id=artifact_id)
    return result


async def _search_artifacts(
    service: Any, agent_id: str, user_id: str, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Lexical search over the user's latest artifacts."""
    query = (parameters.get("query") or "").strip().lower()
    category = (parameters.get("category") or "").strip().lower()
    try:
        limit = int(parameters.get("limit") or _SEARCH_LIMIT_DEFAULT)
    except (TypeError, ValueError):
        limit = _SEARCH_LIMIT_DEFAULT
    limit = max(1, min(limit, _SEARCH_LIMIT_MAX))

    rows = await service.list_artifacts(user_id, order_by_last_accessed=True)
    matches = []
    for row in rows:
        if category and (row.get("category") or "").lower() != category:
            continue
        if query:
            haystack = " ".join(
                [row.get("name") or "", row.get("summary") or ""]
                + [str(tag) for tag in (row.get("tags") or [])]
            ).lower()
            if query not in haystack:
                continue
        matches.append(_tool_row(row))
        if len(matches) >= limit:
            break

    _observe_retrieved(agent_id, user_id, "get_artifact", matched=len(matches))
    result = {"success": True, "artifacts": matches, "count": len(matches)}
    if not matches:
        result["message"] = "No artifacts matched; try get_artifact without filters to list all"
    return result


async def handle_get_artifact_content(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle the get_artifact_content tool call (full decrypted content)."""
    service = _service_or_none(overlord)
    if service is None:
        return {"success": False, "error": "Artifact memory is not available in this formation"}
    user_id = _effective_user(user_id)

    artifact_id = (parameters.get("id") or "").strip()
    if not artifact_id:
        return {"success": False, "error": "get_artifact_content requires an artifact id"}
    version = parameters.get("version")
    if version is not None:
        try:
            version = int(version)
        except (TypeError, ValueError):
            return {"success": False, "error": "version must be an integer"}

    try:
        row = await service.resolve_version(user_id, artifact_id, version)
        if row is None:
            missing = (
                f"No artifact with id '{artifact_id}' found for this user"
                if version is None
                else f"Artifact '{artifact_id}' has no version {version} for this user"
            )
            return {"success": False, "error": missing}

        # read_content decrypts + decompresses and refreshes
        # last_accessed_at on the exact version row being read.
        content = await service.read_content(user_id, row["public_id"])
        result = {"success": True, "metadata": _tool_row(row)}
        text = _decode_text(content, row["content_type"])
        if text is None:
            result["content"] = None
            result["note"] = (
                f"Binary artifact ({row['content_type']}, {row['size_bytes']} bytes); "
                "binary content cannot be rendered into context. Deliver it via the "
                "/v1/artifacts/{id}/content REST endpoint or regenerate it."
            )
        elif len(text) > MAX_CONTENT_CHARS:
            result["content"] = text[:MAX_CONTENT_CHARS]
            result["truncated"] = True
            result["note"] = (
                f"Content truncated at {MAX_CONTENT_CHARS} characters "
                f"(full size: {row['size_bytes']} bytes)"
            )
        else:
            result["content"] = text

        _observe_retrieved(
            agent_id,
            user_id,
            "get_artifact_content",
            artifact_id=row["public_id"],
            version=row["version"],
        )
        return result
    except Exception as e:
        _observe_failed(agent_id, user_id, "get_artifact_content", e)
        return {"success": False, "error": f"Artifact content retrieval failed: {e}"}


async def handle_get_artifact_history(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle the get_artifact_history tool call (version chain)."""
    service = _service_or_none(overlord)
    if service is None:
        return {"success": False, "error": "Artifact memory is not available in this formation"}
    user_id = _effective_user(user_id)

    artifact_id = (parameters.get("id") or "").strip()
    if not artifact_id:
        return {"success": False, "error": "get_artifact_history requires an artifact id"}

    try:
        chain = await service.get_history(user_id, artifact_id)
        if not chain:
            return {
                "success": False,
                "error": f"No artifact with id '{artifact_id}' found for this user",
            }
        versions = [
            {
                "id": row["public_id"],
                "version": row["version"],
                "is_latest": row["is_latest"],
                "summary": row["summary"],
                "created_at": row["created_at"],
                "agent": row["agent_id"] or "overlord",
                "size_bytes": row["size_bytes"],
            }
            for row in chain
        ]
        _observe_retrieved(
            agent_id,
            user_id,
            "get_artifact_history",
            artifact_id=artifact_id,
            versions=len(versions),
        )
        return {
            "success": True,
            "name": chain[0]["name"],
            "versions": versions,
            "count": len(versions),
        }
    except Exception as e:
        _observe_failed(agent_id, user_id, "get_artifact_history", e)
        return {"success": False, "error": f"Artifact history retrieval failed: {e}"}
