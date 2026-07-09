"""
Request Middleware service.

A formation-declared MCP server that transforms every request payload
after client-key auth and before any processing. This is the ONLY way
group memberships enter the runtime (see the request-middleware PRD):
the middleware receives the full request payload (``user_id``,
``message``, ``attachments``, ``metadata``, ``route_class``) and returns
the same-shaped payload, possibly modified -- attaching ``groups``,
rewriting identity, or applying payload policy in transit.

Fail-closed: middleware error, timeout, or a malformed response rejects
the request. ``rbac.fallback`` never applies to middleware errors.
"""

from .client import RequestMiddleware
from .contract import (
    MIDDLEWARE_TOOL_NAME,
    PAYLOAD_FIELDS,
    RESPONSE_FIELDS,
    MiddlewareConfigError,
    MiddlewareContractError,
    MiddlewareRejectedError,
    build_request_payload,
    decode_attachments,
    encode_attachments,
    validate_response_payload,
    validate_tool_contract,
)

__all__ = [
    "MIDDLEWARE_TOOL_NAME",
    "PAYLOAD_FIELDS",
    "RESPONSE_FIELDS",
    "MiddlewareConfigError",
    "MiddlewareContractError",
    "MiddlewareRejectedError",
    "RequestMiddleware",
    "build_request_payload",
    "decode_attachments",
    "encode_attachments",
    "validate_response_payload",
    "validate_tool_contract",
]
