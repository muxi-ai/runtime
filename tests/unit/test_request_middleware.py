"""Unit tests for the request middleware service (request-middleware PRD).

Covers:

1. Config -- the ``middleware:`` block parser: exactly one transport,
   headers/args exclusivity, timeout parsing, unknown keys.
2. Tool contract -- load-time validation of the discovered ``middleware``
   tool's input/output schemas (fail fast).
3. Response validation -- per-request validation of the returned payload
   (fail closed): shape, unknown fields, groups typing, route_class
   pinning, attachment round-tripping.
4. Transform -- the MCP plumbing: structured/text results, tool errors,
   timeouts, and transport failures all reject fail-closed.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from muxi.runtime.services.middleware import (
    MiddlewareConfigError,
    MiddlewareContractError,
    MiddlewareRejectedError,
    RequestMiddleware,
    build_request_payload,
    decode_attachments,
    encode_attachments,
    validate_response_payload,
    validate_tool_contract,
)
from muxi.runtime.services.middleware.client import parse_timeout

FORMATION_ID = "middleware-test"


# ===================================================================
# 1. Config parsing
# ===================================================================


class TestMiddlewareConfig:
    def test_http_transport(self):
        mw = RequestMiddleware.from_config(
            {"url": "https://resolver.example/mcp", "timeout": "2s"},
            formation_id=FORMATION_ID,
        )
        assert mw.url == "https://resolver.example/mcp"
        assert mw.command is None
        assert mw.timeout_seconds == 2.0

    def test_http_transport_with_headers(self):
        mw = RequestMiddleware.from_config(
            {"url": "https://x", "headers": {"Authorization": "Bearer tok"}},
        )
        assert mw.headers == {"Authorization": "Bearer tok"}

    def test_stdio_transport_with_args(self):
        mw = RequestMiddleware.from_config(
            {"command": "/usr/bin/resolver", "args": ["--formation", "acme"]},
        )
        assert mw.command == "/usr/bin/resolver"
        assert mw.args == ["--formation", "acme"]

    def test_stdio_relative_command_resolves_against_base_dir(self, tmp_path):
        script = tmp_path / "middleware.py"
        script.write_text("#!/usr/bin/env python3\n")
        mw = RequestMiddleware.from_config(
            {"command": "./middleware.py"}, base_dir=str(tmp_path)
        )
        assert mw.command == str(script)

    def test_both_transports_rejected(self):
        with pytest.raises(MiddlewareConfigError, match="exactly one transport"):
            RequestMiddleware.from_config({"url": "https://x", "command": "./y"})

    def test_neither_transport_rejected(self):
        with pytest.raises(MiddlewareConfigError, match="exactly one transport"):
            RequestMiddleware.from_config({"timeout": "2s"})

    def test_empty_block_rejected(self):
        with pytest.raises(MiddlewareConfigError):
            RequestMiddleware.from_config({})
        with pytest.raises(MiddlewareConfigError):
            RequestMiddleware.from_config(None)

    def test_headers_only_valid_for_http(self):
        with pytest.raises(MiddlewareConfigError, match="headers"):
            RequestMiddleware.from_config({"command": "./x", "headers": {"A": "b"}})

    def test_args_only_valid_for_stdio(self):
        with pytest.raises(MiddlewareConfigError, match="args"):
            RequestMiddleware.from_config({"url": "https://x", "args": ["--y"]})

    def test_unknown_keys_rejected(self):
        with pytest.raises(MiddlewareConfigError, match="unknown key"):
            RequestMiddleware.from_config({"url": "https://x", "cache": True})

    def test_default_timeout(self):
        mw = RequestMiddleware.from_config({"url": "https://x"})
        assert mw.timeout_seconds == 10.0

    @pytest.mark.parametrize(
        "value,expected",
        [("500ms", 0.5), ("2s", 2.0), ("1m", 60.0), ("1.5s", 1.5), (3, 3.0), (0.25, 0.25)],
    )
    def test_timeout_parsing(self, value, expected):
        assert parse_timeout(value) == expected

    @pytest.mark.parametrize("value", ["fast", "-1s", "0", 0, -2, True, None, "2h"])
    def test_invalid_timeouts_rejected(self, value):
        with pytest.raises(MiddlewareConfigError):
            parse_timeout(value)


# ===================================================================
# 2. Tool contract (load-time, fail fast)
# ===================================================================


def contract_tool(input_props=None, output_props=None, name="middleware"):
    tool = {
        "name": name,
        "description": "test middleware",
        "inputSchema": {
            "type": "object",
            "properties": {
                key: {}
                for key in (
                    input_props
                    if input_props is not None
                    else ["user_id", "message", "attachments", "metadata", "route_class"]
                )
            },
        },
    }
    if output_props is not None:
        tool["outputSchema"] = {
            "type": "object",
            "properties": {key: {} for key in output_props},
        }
    return tool


class TestToolContract:
    def test_valid_tool_accepted(self):
        tool = validate_tool_contract([contract_tool()])
        assert tool["name"] == "middleware"

    def test_valid_tool_with_output_schema_accepted(self):
        tool = contract_tool(
            output_props=["user_id", "message", "attachments", "metadata", "route_class", "groups"]
        )
        assert validate_tool_contract([tool])["name"] == "middleware"

    def test_missing_tool_fails(self):
        with pytest.raises(MiddlewareContractError, match="no tool named"):
            validate_tool_contract([contract_tool(name="transform")])

    def test_empty_catalog_fails(self):
        with pytest.raises(MiddlewareContractError, match="no tool named"):
            validate_tool_contract([])

    def test_missing_input_property_fails(self):
        tool = contract_tool(input_props=["user_id", "message"])
        with pytest.raises(MiddlewareContractError, match="missing required"):
            validate_tool_contract([tool])

    def test_groups_in_input_schema_fails(self):
        """groups is NEVER part of the inbound payload."""
        tool = contract_tool(
            input_props=["user_id", "message", "attachments", "metadata", "route_class", "groups"]
        )
        with pytest.raises(MiddlewareContractError, match="groups"):
            validate_tool_contract([tool])

    def test_extra_input_property_fails(self):
        tool = contract_tool(
            input_props=["user_id", "message", "attachments", "metadata", "route_class", "tenant"]
        )
        with pytest.raises(MiddlewareContractError, match="unknown"):
            validate_tool_contract([tool])

    def test_no_input_schema_fails(self):
        tool = {"name": "middleware"}
        with pytest.raises(MiddlewareContractError, match="input schema"):
            validate_tool_contract([tool])

    def test_bad_output_schema_fails(self):
        tool = contract_tool(output_props=["user_id", "message", "route_class", "verdict"])
        with pytest.raises(MiddlewareContractError, match="unknown"):
            validate_tool_contract([tool])

    def test_output_schema_missing_payload_fields_fails(self):
        tool = contract_tool(output_props=["groups"])
        with pytest.raises(MiddlewareContractError, match="missing payload"):
            validate_tool_contract([tool])


# ===================================================================
# 3. Response payload validation (per request, fail closed)
# ===================================================================


def sent_payload(**overrides):
    payload = build_request_payload(
        user_id="alice@example.com",
        message="hello",
        attachments=[],
        metadata={"session_id": "s1"},
        route_class="chat",
    )
    payload.update(overrides)
    return payload


class TestResponseValidation:
    def test_passthrough_response(self):
        sent = sent_payload()
        validated, groups = validate_response_payload(dict(sent), sent)
        assert validated == sent
        assert groups == ()

    def test_groups_attached(self):
        sent = sent_payload()
        returned = {**sent, "groups": ["hr", "analyst", "hr"]}
        validated, groups = validate_response_payload(returned, sent)
        assert groups == ("hr", "analyst")  # deduplicated, order kept
        assert "groups" not in validated

    def test_identity_rewrite_allowed(self):
        sent = sent_payload()
        returned = {**sent, "user_id": "employee-42"}
        validated, _ = validate_response_payload(returned, sent)
        assert validated["user_id"] == "employee-42"

    def test_non_dict_rejected(self):
        with pytest.raises(MiddlewareRejectedError, match="malformed_response"):
            validate_response_payload("ok", sent_payload())

    def test_missing_field_rejected(self):
        sent = sent_payload()
        returned = {k: v for k, v in sent.items() if k != "message"}
        with pytest.raises(MiddlewareRejectedError, match="missing required"):
            validate_response_payload(returned, sent)

    def test_unknown_field_rejected(self):
        sent = sent_payload()
        with pytest.raises(MiddlewareRejectedError, match="unknown field"):
            validate_response_payload({**sent, "verdict": "allow"}, sent)

    def test_route_class_must_be_echoed(self):
        sent = sent_payload()
        with pytest.raises(MiddlewareRejectedError, match="route_class"):
            validate_response_payload({**sent, "route_class": "chat2"}, sent)

    def test_empty_user_id_rejected(self):
        sent = sent_payload()
        with pytest.raises(MiddlewareRejectedError, match="user_id"):
            validate_response_payload({**sent, "user_id": "  "}, sent)

    @pytest.mark.parametrize("bad_groups", ["hr", {"hr": True}, [1], [""], [None]])
    def test_bad_groups_rejected(self, bad_groups):
        sent = sent_payload()
        with pytest.raises(MiddlewareRejectedError):
            validate_response_payload({**sent, "groups": bad_groups}, sent)

    def test_bad_attachments_rejected(self):
        sent = sent_payload()
        with pytest.raises(MiddlewareRejectedError, match="attachments"):
            validate_response_payload({**sent, "attachments": ["x"]}, sent)

    def test_bad_metadata_rejected(self):
        sent = sent_payload()
        with pytest.raises(MiddlewareRejectedError, match="metadata"):
            validate_response_payload({**sent, "metadata": []}, sent)


class TestAttachmentRoundTrip:
    def test_bytes_content_round_trips(self):
        files = [{"filename": "a.bin", "content": b"\x00\x01", "size": 2}]
        encoded = encode_attachments(files)
        assert encoded[0]["content_encoding"] == "base64"
        json.dumps(encoded)  # JSON-safe
        decoded = decode_attachments(encoded)
        assert decoded[0]["content"] == b"\x00\x01"
        assert "content_encoding" not in decoded[0]

    def test_text_content_passes_through(self):
        files = [{"filename": "a.txt", "content": "hello"}]
        assert encode_attachments(files) == files
        assert decode_attachments(files) == files

    def test_empty_and_none(self):
        assert encode_attachments(None) == []
        assert decode_attachments(None) == []

    def test_invalid_base64_rejected(self):
        bad = [{"filename": "a", "content": "%%%", "content_encoding": "base64"}]
        with pytest.raises(MiddlewareRejectedError):
            decode_attachments(bad)


# ===================================================================
# 4. Transform plumbing (fail closed)
# ===================================================================


class FakeClient:
    """Stands in for MCPServerClient in transform tests."""

    def __init__(self, response=None, exc=None, delay=0.0):
        self.connected = True
        self.response = response
        self.exc = exc
        self.delay = delay
        self.calls = []

    async def execute_tool(self, tool_name, params, request_id=None, timeout=None):
        self.calls.append((tool_name, params))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc is not None:
            raise self.exc
        return self.response


def middleware_with(client) -> RequestMiddleware:
    mw = RequestMiddleware(command="./middleware.py", formation_id=FORMATION_ID)
    mw._client = client
    return mw


def tool_success(payload, structured=True):
    result = {"isError": False}
    if structured:
        result["structuredContent"] = payload
        result["content"] = [{"type": "text", "text": json.dumps(payload)}]
    else:
        result["content"] = [{"type": "text", "text": json.dumps(payload)}]
    return {"status": "success", "result": result}


class TestTransform:
    async def test_structured_content_response(self):
        sent = sent_payload()
        returned = {**sent, "groups": ["hr"]}
        mw = middleware_with(FakeClient(response=tool_success(returned)))

        validated, groups = await mw.transform(sent)
        assert groups == ("hr",)
        assert validated["user_id"] == sent["user_id"]

    async def test_text_content_json_response(self):
        sent = sent_payload()
        returned = {**sent, "groups": ["eng"]}
        mw = middleware_with(FakeClient(response=tool_success(returned, structured=False)))

        _, groups = await mw.transform(sent)
        assert groups == ("eng",)

    async def test_nested_jsonrpc_envelope(self):
        sent = sent_payload()
        returned = {**sent, "groups": ["hr"]}
        response = {
            "status": "success",
            "result": {
                "jsonrpc": "2.0",
                "id": "rpc_1",
                "result": {"isError": False, "structuredContent": returned, "content": []},
            },
        }
        mw = middleware_with(FakeClient(response=response))
        _, groups = await mw.transform(sent)
        assert groups == ("hr",)

    async def test_transport_error_rejects(self):
        mw = middleware_with(FakeClient(exc=RuntimeError("boom")))
        with pytest.raises(MiddlewareRejectedError) as exc_info:
            await mw.transform(sent_payload())
        assert exc_info.value.reason == "error"

    async def test_timeout_rejects(self):
        mw = middleware_with(FakeClient(response=tool_success(sent_payload()), delay=0.2))
        mw.timeout_seconds = 0.05
        with pytest.raises(MiddlewareRejectedError) as exc_info:
            await mw.transform(sent_payload())
        assert exc_info.value.reason == "timeout"

    async def test_tool_error_rejects(self):
        response = {
            "status": "success",
            "result": {"isError": True, "content": [{"type": "text", "text": "denied"}]},
        }
        mw = middleware_with(FakeClient(response=response))
        with pytest.raises(MiddlewareRejectedError) as exc_info:
            await mw.transform(sent_payload())
        assert exc_info.value.reason == "error"

    async def test_transport_error_status_rejects(self):
        response = {"status": "error", "error": {"message": "connection reset"}}
        mw = middleware_with(FakeClient(response=response))
        with pytest.raises(MiddlewareRejectedError):
            await mw.transform(sent_payload())

    async def test_non_json_content_rejects(self):
        response = {
            "status": "success",
            "result": {"isError": False, "content": [{"type": "text", "text": "not json"}]},
        }
        mw = middleware_with(FakeClient(response=response))
        with pytest.raises(MiddlewareRejectedError) as exc_info:
            await mw.transform(sent_payload())
        assert exc_info.value.reason == "malformed_response"

    async def test_empty_result_rejects(self):
        response = {"status": "success", "result": {"isError": False, "content": []}}
        mw = middleware_with(FakeClient(response=response))
        with pytest.raises(MiddlewareRejectedError):
            await mw.transform(sent_payload())

    async def test_schema_invalid_response_rejects(self):
        sent = sent_payload()
        returned = {**sent, "groups": "hr"}  # not a list
        mw = middleware_with(FakeClient(response=tool_success(returned)))
        with pytest.raises(MiddlewareRejectedError):
            await mw.transform(sent)

    async def test_payload_never_contains_groups_inbound(self):
        sent = sent_payload()
        client = FakeClient(response=tool_success(sent))
        mw = middleware_with(client)
        await mw.transform(sent)
        (_, params) = client.calls[0]
        assert "groups" not in params
