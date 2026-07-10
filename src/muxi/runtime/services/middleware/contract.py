# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Request Middleware Contract - payload schema + tool validation
# Description:  Defines the request-in/request-out contract every formation
#               middleware MUST implement, and the validation helpers the
#               runtime uses to enforce it (fail-fast at load, fail-closed
#               per request).
# Role:         Single source of truth for the ``middleware`` tool contract:
#               the payload fields, the load-time tool schema check, and the
#               per-request response validation.
# Usage:        ``build_request_payload`` assembles the outbound payload,
#               ``validate_tool_contract`` runs at formation load against the
#               discovered tool definition, ``validate_response_payload``
#               runs on every middleware response before the runtime
#               continues processing with it.
# Author:       MUXI Framework Team
#
# The contract (request-middleware PRD):
#   * Exactly one tool named ``middleware``.
#   * Input schema: an object whose properties are exactly the request
#     payload fields (user_id, message, attachments, metadata,
#     route_class). ``groups`` is NEVER part of the inbound payload --
#     a middleware declaring it as input fails the load.
#   * Output: the same-shaped payload, possibly modified, plus an
#     optional ``groups`` list -- the only channel through which group
#     memberships enter the runtime. When the tool declares an output
#     schema it must match; an absent output schema is accepted (every
#     response is validated at runtime regardless).
#   * route_class identifies the origin of the request: external routes
#     ("chat", "audiochat", "trigger", "api") and internal origins
#     ("heartbeat", "scheduler", "delegation") traverse the middleware
#     identically. The middleware must echo route_class unchanged.
# =============================================================================

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Sequence, Tuple

MIDDLEWARE_TOOL_NAME = "middleware"

# The request payload fields, in canonical order. This is both the
# runtime->middleware payload shape and the required input schema.
PAYLOAD_FIELDS: Tuple[str, ...] = (
    "user_id",
    "message",
    "attachments",
    "metadata",
    "route_class",
)

# The middleware->runtime response shape: same payload, plus the one
# field only the middleware may attach.
RESPONSE_FIELDS: Tuple[str, ...] = (*PAYLOAD_FIELDS, "groups")


class MiddlewareConfigError(ValueError):
    """The ``middleware:`` formation block is malformed (load-time)."""


class MiddlewareContractError(ValueError):
    """The middleware server does not honor the tool contract (load-time)."""


class MiddlewareRejectedError(Exception):
    """A request was rejected fail-closed by the middleware step.

    Raised for middleware errors, timeouts, and malformed or
    schema-invalid responses. ``rbac.fallback`` NEVER applies here -- a
    fallback on error would let an identity-provider outage silently
    reassign users to the fallback group.
    """

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def build_request_payload(
    user_id: str,
    message: str,
    attachments: Optional[Sequence[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    route_class: str = "chat",
) -> Dict[str, Any]:
    """Assemble the canonical request payload sent to the middleware.

    The inbound payload never contains ``groups`` -- it can only be
    attached by the middleware on the way out, so it can never arrive
    as a caller's claim.
    """
    return {
        "user_id": str(user_id),
        "message": message if isinstance(message, str) else str(message),
        "attachments": list(attachments) if attachments else [],
        "metadata": dict(metadata) if metadata else {},
        "route_class": route_class,
    }


def encode_attachments(
    files: Optional[Sequence[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Make file attachments JSON-safe for the middleware payload.

    Binary ``content`` is base64-encoded with a ``content_encoding``
    marker so :func:`decode_attachments` can restore the exact bytes
    after the round-trip. Everything else passes through unchanged.
    """
    encoded: List[Dict[str, Any]] = []
    for item in files or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("content"), bytes):
            item = {
                **item,
                "content": base64.b64encode(item["content"]).decode("ascii"),
                "content_encoding": "base64",
            }
        encoded.append(item)
    return encoded


def decode_attachments(
    attachments: Optional[Sequence[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Reverse :func:`encode_attachments` on a middleware response."""
    decoded: List[Dict[str, Any]] = []
    for item in attachments or []:
        if not isinstance(item, dict):
            continue
        if item.get("content_encoding") == "base64" and isinstance(item.get("content"), str):
            item = {k: v for k, v in item.items() if k != "content_encoding"}
            try:
                item["content"] = base64.b64decode(item["content"], validate=True)
            except (ValueError, TypeError) as e:
                raise MiddlewareRejectedError(
                    "malformed_response", f"attachment content is not valid base64: {e}"
                ) from e
        decoded.append(item)
    return decoded


def _schema_properties(schema: Any) -> Optional[Dict[str, Any]]:
    """Extract the properties mapping from a JSON schema, or None."""
    if not isinstance(schema, dict):
        return None
    if schema.get("type") not in (None, "object"):
        return None
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None
    return properties


def validate_tool_contract(tools: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate the discovered tool catalog against the middleware contract.

    Args:
        tools: Tool definitions from ``tools/list``.

    Returns:
        The validated ``middleware`` tool definition.

    Raises:
        MiddlewareContractError: No ``middleware`` tool, or its declared
            input/output schema does not match the contract.
    """
    tool = next(
        (t for t in tools if isinstance(t, dict) and t.get("name") == MIDDLEWARE_TOOL_NAME),
        None,
    )
    if tool is None:
        names = sorted(t.get("name", "?") for t in tools if isinstance(t, dict))
        raise MiddlewareContractError(
            f"middleware server exposes no tool named {MIDDLEWARE_TOOL_NAME!r} "
            f"(found: {names or 'no tools'})"
        )

    input_schema = tool.get("inputSchema") or tool.get("input_schema")
    properties = _schema_properties(input_schema)
    if properties is None:
        raise MiddlewareContractError(
            "middleware tool must declare an object input schema with "
            f"properties {sorted(PAYLOAD_FIELDS)}"
        )
    declared = set(properties)
    required = set(PAYLOAD_FIELDS)
    if "groups" in declared:
        raise MiddlewareContractError(
            "middleware tool input schema declares 'groups' -- groups are "
            "never part of the inbound request payload; they can only be "
            "attached by the middleware in its response"
        )
    missing = sorted(required - declared)
    if missing:
        raise MiddlewareContractError(
            f"middleware tool input schema is missing required "
            f"propert{'ies' if len(missing) != 1 else 'y'} {missing}"
        )
    extra = sorted(declared - required)
    if extra:
        raise MiddlewareContractError(
            f"middleware tool input schema declares unknown "
            f"propert{'ies' if len(extra) != 1 else 'y'} {extra}; the "
            f"contract payload is exactly {sorted(PAYLOAD_FIELDS)}"
        )

    output_schema = tool.get("outputSchema") or tool.get("output_schema")
    if output_schema is not None:
        out_properties = _schema_properties(output_schema)
        if out_properties is None:
            raise MiddlewareContractError(
                "middleware tool output schema must be an object schema "
                f"with properties drawn from {sorted(RESPONSE_FIELDS)}"
            )
        out_declared = set(out_properties)
        out_extra = sorted(out_declared - set(RESPONSE_FIELDS))
        if out_extra:
            raise MiddlewareContractError(
                f"middleware tool output schema declares unknown "
                f"propert{'ies' if len(out_extra) != 1 else 'y'} {out_extra}; "
                f"the response payload is {sorted(RESPONSE_FIELDS)}"
            )
        out_missing = sorted(set(PAYLOAD_FIELDS) - out_declared)
        if out_missing:
            raise MiddlewareContractError(
                f"middleware tool output schema is missing payload "
                f"propert{'ies' if len(out_missing) != 1 else 'y'} {out_missing}"
            )

    return tool


def validate_response_payload(
    returned: Any, sent: Dict[str, Any]
) -> Tuple[Dict[str, Any], Tuple[str, ...]]:
    """Validate a middleware response against the request schema.

    Args:
        returned: The payload the middleware returned.
        sent: The payload the runtime sent (for route_class pinning).

    Returns:
        ``(payload, groups)`` -- the validated same-shaped payload (no
        ``groups`` key) and the attached group ids as a tuple.

    Raises:
        MiddlewareRejectedError: The response is malformed or
            schema-invalid; the request must be rejected (fail-closed).
    """

    def _reject(detail: str) -> None:
        raise MiddlewareRejectedError("malformed_response", detail)

    if not isinstance(returned, dict):
        _reject(f"middleware must return a payload object, got {type(returned).__name__}")

    unknown = sorted(set(returned) - set(RESPONSE_FIELDS))
    if unknown:
        _reject(f"response contains unknown field(s) {unknown}")

    missing = sorted(set(PAYLOAD_FIELDS) - set(returned))
    if missing:
        _reject(f"response is missing required field(s) {missing}")

    user_id = returned["user_id"]
    if not isinstance(user_id, str) or not user_id.strip():
        _reject("user_id must be a non-empty string")

    message = returned["message"]
    if not isinstance(message, str):
        _reject(f"message must be a string, got {type(message).__name__}")

    attachments = returned["attachments"]
    if not isinstance(attachments, list) or any(not isinstance(item, dict) for item in attachments):
        _reject("attachments must be a list of objects")

    metadata = returned["metadata"]
    if not isinstance(metadata, dict):
        _reject(f"metadata must be an object, got {type(metadata).__name__}")

    route_class = returned["route_class"]
    if route_class != sent.get("route_class"):
        _reject(
            f"route_class must be echoed unchanged "
            f"(sent {sent.get('route_class')!r}, got {route_class!r})"
        )

    groups: List[str] = []
    if "groups" in returned:
        raw_groups = returned["groups"]
        if not isinstance(raw_groups, list):
            _reject(f"groups must be a list of strings, got {type(raw_groups).__name__}")
        for i, group_id in enumerate(raw_groups):
            if not isinstance(group_id, str) or not group_id.strip():
                _reject(f"groups entry {i} must be a non-empty string, got {group_id!r}")
            if group_id not in groups:
                groups.append(group_id)

    payload = {field: returned[field] for field in PAYLOAD_FIELDS}
    return payload, tuple(groups)
