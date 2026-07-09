# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Request Middleware Client - formation middleware over MCP
# Description:  Connects to the formation's declared ``middleware:`` MCP
#               server (http or stdio) with the existing MCP client, checks
#               the tool contract at startup (fail fast), and transforms
#               request payloads per request (fail closed).
# Role:         The single choke point through which every request payload
#               -- external routes and internal origins alike -- travels
#               before RBAC resolution and any processing.
# Usage:        ``RequestMiddleware.from_config(config, base_dir)`` parses
#               and validates the formation block; ``await start()`` connects
#               and enforces the contract; ``await transform(payload)``
#               returns the (validated) transformed payload plus attached
#               groups, raising MiddlewareRejectedError on any failure.
# Author:       MUXI Framework Team
#
# Design constraints (request-middleware PRD):
#   * Exactly one transport: url (+ optional headers) XOR command
#     (+ optional args). Secrets interpolation happens upstream in the
#     formation config loader like any other MCP declaration.
#   * NO runtime-side caching: the middleware is called on every request
#     with full transformation rights. ``timeout`` is the only knob.
#   * Fail closed: error, timeout, or malformed response rejects the
#     request. rbac.fallback does not apply to middleware errors.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from typing import Any, Dict, Optional, Tuple

import httpx

from .. import observability
from ..mcp.handler import MCPServerClient
from ..mcp.transports.protocol_features import ModernProtocolFeatures
from .contract import (
    MIDDLEWARE_TOOL_NAME,
    MiddlewareConfigError,
    MiddlewareRejectedError,
    validate_response_payload,
    validate_tool_contract,
)

DEFAULT_TIMEOUT_SECONDS = 10.0

_ALLOWED_CONFIG_KEYS = frozenset({"url", "headers", "command", "args", "timeout"})
_DURATION_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m)?\s*$")
_DURATION_FACTORS = {"ms": 0.001, "s": 1.0, "m": 60.0, None: 1.0}


def parse_timeout(value: Any) -> float:
    """Parse the middleware ``timeout`` knob into seconds.

    Accepts numbers (seconds) or duration strings (``500ms``, ``2s``,
    ``1m``; a bare number string means seconds).
    """
    if isinstance(value, bool):
        raise MiddlewareConfigError(f"middleware timeout must be a duration, got: {value!r}")
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        match = _DURATION_PATTERN.match(value)
        if not match:
            raise MiddlewareConfigError(
                f"middleware timeout must be a number of seconds or a duration "
                f"string like '500ms', '2s', or '1m', got: {value!r}"
            )
        seconds = float(match.group(1)) * _DURATION_FACTORS[match.group(2)]
    else:
        raise MiddlewareConfigError(
            f"middleware timeout must be a number or duration string, "
            f"got: {type(value).__name__}"
        )
    if not math.isfinite(seconds) or seconds <= 0:
        raise MiddlewareConfigError(f"middleware timeout must be positive, got: {value!r}")
    return seconds


class RequestMiddleware:
    """The formation's request middleware: one MCP server, one tool."""

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        command: Optional[str] = None,
        args: Optional[Tuple[str, ...]] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        formation_id: str = "",
    ):
        self.url = url
        self.headers = dict(headers) if headers else None
        self.command = command
        self.args = list(args) if args else None
        self.timeout_seconds = timeout_seconds
        self.formation_id = formation_id
        self._client: Optional[MCPServerClient] = None
        self._connect_lock = asyncio.Lock()

    # -----------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------

    @classmethod
    def from_config(
        cls, config: Any, *, base_dir: Optional[str] = None, formation_id: str = ""
    ) -> "RequestMiddleware":
        """Parse and validate a formation ``middleware:`` block.

        Raises:
            MiddlewareConfigError: The block is structurally invalid
                (load-time, fail fast).
        """
        if not isinstance(config, dict) or not config:
            raise MiddlewareConfigError(
                "middleware must be a mapping declaring exactly one MCP "
                "transport: url (+ optional headers) or command (+ optional "
                "args), plus an optional timeout"
            )
        unknown = sorted(set(config) - _ALLOWED_CONFIG_KEYS)
        if unknown:
            raise MiddlewareConfigError(
                f"middleware has unknown key(s) {unknown}; supported keys are "
                f"{sorted(_ALLOWED_CONFIG_KEYS)}"
            )

        url = config.get("url")
        command = config.get("command")
        if (url is None) == (command is None):
            raise MiddlewareConfigError(
                "middleware must declare exactly one transport: 'url' "
                "(http) or 'command' (stdio)"
            )

        headers: Optional[Dict[str, str]] = None
        args: Optional[Tuple[str, ...]] = None

        if url is not None:
            if not isinstance(url, str) or not url.strip():
                raise MiddlewareConfigError("middleware url must be a non-empty string")
            if "args" in config:
                raise MiddlewareConfigError(
                    "middleware 'args' only applies to the stdio transport ('command')"
                )
            raw_headers = config.get("headers")
            if raw_headers is not None:
                if not isinstance(raw_headers, dict) or not raw_headers:
                    raise MiddlewareConfigError(
                        "middleware headers must be a non-empty mapping of " "header name to value"
                    )
                for name, value in raw_headers.items():
                    if not isinstance(name, str) or not name.strip():
                        raise MiddlewareConfigError(
                            f"middleware header names must be non-empty strings, got: {name!r}"
                        )
                    if not isinstance(value, str):
                        raise MiddlewareConfigError(
                            f"middleware header {name!r} must be a string value"
                        )
                headers = dict(raw_headers)
        else:
            if not isinstance(command, str) or not command.strip():
                raise MiddlewareConfigError("middleware command must be a non-empty string")
            if "headers" in config:
                raise MiddlewareConfigError(
                    "middleware 'headers' only applies to the http transport ('url')"
                )
            raw_args = config.get("args")
            if raw_args is not None:
                if not isinstance(raw_args, list) or any(not isinstance(a, str) for a in raw_args):
                    raise MiddlewareConfigError("middleware args must be a list of strings")
                args = tuple(raw_args)
            # A stdio middleware is typically a one-file script in the
            # formation directory (command: ./middleware.py); resolve
            # relative paths against it so the subprocess spawn does not
            # depend on the runtime's working directory.
            if base_dir and not os.path.isabs(command):
                candidate = os.path.normpath(os.path.join(base_dir, command))
                if os.path.exists(candidate):
                    command = candidate

        timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        if "timeout" in config:
            timeout_seconds = parse_timeout(config["timeout"])

        return cls(
            url=url,
            headers=headers,
            command=command,
            args=args,
            timeout_seconds=timeout_seconds,
            formation_id=formation_id,
        )

    @property
    def transport_description(self) -> str:
        """Human-readable transport summary for logs and events."""
        if self.url:
            return f"http:{self.url}"
        return f"stdio:{self.command}"

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------

    async def start(self) -> None:
        """Connect and enforce the tool contract. Fails fast.

        Raises:
            MiddlewareContractError: The ``middleware`` tool is absent or
                its declared schema does not match the contract.
            Exception: Connection failures propagate -- a formation that
                declares middleware it cannot reach must not start.
        """
        client = await self._connect()
        response = await client.send_message("tools/list", {})
        tools = self._extract_tools(response)
        tool = validate_tool_contract(tools)
        observability.observe(
            event_type=observability.SystemEvents.MIDDLEWARE_CONNECTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "request_middleware",
                "formation_id": self.formation_id,
                "transport": self.transport_description,
                "timeout_seconds": self.timeout_seconds,
                "tool_description": tool.get("description"),
            },
            description=(
                f"Request middleware connected ({self.transport_description}); "
                f"'{MIDDLEWARE_TOOL_NAME}' tool contract verified"
            ),
        )

    async def stop(self) -> None:
        """Disconnect from the middleware server (best effort)."""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    @property
    def _inner_timeout(self) -> int:
        """The MCP client's own timeout, padded past the outer wait_for.

        The outer ``asyncio.wait_for(self.timeout_seconds)`` must always
        fire first so timeouts surface as asyncio.TimeoutError and get
        labeled ``reason: "timeout"`` -- on exact integer timeouts the
        transport's own deadline could otherwise race it and surface as
        a transport-specific exception instead.
        """
        return max(1, math.ceil(self.timeout_seconds)) + 1

    async def _connect(self) -> MCPServerClient:
        """Return a connected client, (re)connecting when needed."""
        async with self._connect_lock:
            if self._client is not None and self._client.connected:
                return self._client
            if self._client is not None:
                # Tear down the stale client before replacing it so stdio
                # pipes / background tasks don't linger until GC on flaky
                # connections. Best effort, like stop().
                stale, self._client = self._client, None
                try:
                    await stale.disconnect()
                except Exception:
                    pass
            credentials = None
            if self.headers:
                credentials = {"type": "headers", "headers": dict(self.headers)}
            client = MCPServerClient(
                name="request-middleware",
                url=self.url,
                command=self.command,
                args=list(self.args) if self.args else None,
                credentials=credentials,
                request_timeout=self._inner_timeout,
            )
            await client.connect()
            self._client = client
            return client

    # -----------------------------------------------------------------
    # Per-request transformation
    # -----------------------------------------------------------------

    async def transform(
        self, payload: Dict[str, Any], request_id: Optional[str] = None
    ) -> Tuple[Dict[str, Any], Tuple[str, ...]]:
        """Run one request payload through the middleware.

        Args:
            payload: The canonical request payload (from
                :func:`~muxi.runtime.services.middleware.contract.build_request_payload`).
            request_id: Overlord request id for MCP lifecycle tracking.

        Returns:
            ``(payload, groups)`` -- the validated transformed payload
            and the group ids the middleware attached.

        Raises:
            MiddlewareRejectedError: Error, timeout, or malformed
                response. The request MUST be rejected (fail-closed).
                An ``error.middleware.failed`` event is emitted before
                the raise.
        """
        try:
            return await self._transform(payload, request_id)
        except MiddlewareRejectedError as e:
            observability.observe(
                event_type=observability.ErrorEvents.MIDDLEWARE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "request_middleware",
                    "formation_id": self.formation_id,
                    "request_id": request_id,
                    "route_class": payload.get("route_class"),
                    "user_id": payload.get("user_id"),
                    "reason": e.reason,
                    "detail": e.detail,
                    "transport": self.transport_description,
                },
                description=(
                    f"Request middleware failed ({e.reason}); request rejected "
                    f"fail-closed: {e.detail}"
                ),
            )
            raise

    async def _transform(
        self, payload: Dict[str, Any], request_id: Optional[str] = None
    ) -> Tuple[Dict[str, Any], Tuple[str, ...]]:
        """The un-instrumented transform body (see :meth:`transform`)."""
        try:
            client = await self._connect()
            # The outer wait_for owns the timeout; the per-call transport
            # deadline is padded (_inner_timeout) so it can never fire
            # first and mislabel a timeout as a transport error.
            response = await asyncio.wait_for(
                client.execute_tool(
                    MIDDLEWARE_TOOL_NAME,
                    payload,
                    request_id=request_id,
                    timeout=self._inner_timeout,
                ),
                timeout=self.timeout_seconds,
            )
        except MiddlewareRejectedError:
            raise
        except (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException) as e:
            raise MiddlewareRejectedError(
                "timeout", f"middleware did not answer within {self.timeout_seconds}s"
            ) from e
        except Exception as e:
            raise MiddlewareRejectedError("error", str(e)) from e

        returned = self._extract_tool_payload(response)
        validated, groups = validate_response_payload(returned, payload)

        observability.observe(
            event_type=observability.SystemEvents.MIDDLEWARE_APPLIED,
            level=observability.EventLevel.DEBUG,
            data={
                "service": "request_middleware",
                "formation_id": self.formation_id,
                "request_id": request_id,
                "route_class": payload.get("route_class"),
                "groups": list(groups),
                "identity_rewritten": validated["user_id"] != payload["user_id"],
                "message_rewritten": validated["message"] != payload["message"],
            },
            description=(
                f"Request middleware transformed a {payload.get('route_class')!r} "
                f"request (groups: {list(groups)})"
            ),
        )
        return validated, groups

    # -----------------------------------------------------------------
    # MCP response plumbing
    # -----------------------------------------------------------------

    @staticmethod
    def _unwrap_result(response: Any) -> Dict[str, Any]:
        """Unwrap the transport envelope down to the tool-call result."""
        if not isinstance(response, dict):
            raise MiddlewareRejectedError(
                "error", f"unexpected middleware transport response: {type(response).__name__}"
            )
        if response.get("status") == "error":
            error_info = response.get("error", {})
            detail = (
                error_info.get("message", str(error_info))
                if isinstance(error_info, dict)
                else str(error_info)
            )
            raise MiddlewareRejectedError("error", detail or "middleware call failed")
        result = response.get("result", response)
        # Nested JSON-RPC envelope: {"jsonrpc": ..., "result": {...}}
        if (
            isinstance(result, dict)
            and isinstance(result.get("result"), dict)
            and ("jsonrpc" in result or "id" in result)
        ):
            result = result["result"]
        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            raise MiddlewareRejectedError(
                "error", result["error"].get("message", "middleware call failed")
            )
        if not isinstance(result, dict):
            raise MiddlewareRejectedError(
                "malformed_response", f"unexpected tool result type: {type(result).__name__}"
            )
        return result

    def _extract_tools(self, response: Any) -> list:
        """Extract the tool list from a ``tools/list`` response."""
        result = self._unwrap_result(response)
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []

    def _extract_tool_payload(self, response: Any) -> Any:
        """Extract the returned request payload from a tool-call result."""
        result = self._unwrap_result(response)
        processed = ModernProtocolFeatures.process_structured_output(result)
        if processed.get("isError"):
            raise MiddlewareRejectedError(
                "error", str(processed.get("content", "middleware tool returned an error"))
            )
        structured = processed.get("structured_content")
        if isinstance(structured, dict) and structured:
            return structured
        content = processed.get("content")
        if isinstance(content, str) and content.strip():
            try:
                return json.loads(content)
            except (ValueError, TypeError) as e:
                raise MiddlewareRejectedError(
                    "malformed_response",
                    f"middleware returned non-JSON content: {e}",
                ) from e
        raise MiddlewareRejectedError("malformed_response", "middleware returned an empty result")
