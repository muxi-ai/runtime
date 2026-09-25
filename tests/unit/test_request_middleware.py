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
5. Identity hand-off -- chat, memory and trigger pipelines pass the
   caller's user_id to the middleware verbatim, except that an
   email-shaped id is lowercased first, and keep the resulting id
   verbatim (the middleware's, or the caller's without a middleware),
   with or without files. The runtime changes the case of no other id.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.formation.overlord.input_validation import InputValidator
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.formation.server.routes.client.memory import _run_request_pipeline
from muxi.runtime.formation.server.routes.client.triggers import TriggerRequest, execute_trigger
from muxi.runtime.services.gbac import enforcement as gbac_enforcement
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
        mw = RequestMiddleware.from_config({"command": "./middleware.py"}, base_dir=str(tmp_path))
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

    def __init__(self, response=None, exc=None, delay=0.0, connected=True):
        self.connected = connected
        self.response = response
        self.exc = exc
        self.delay = delay
        self.calls = []
        self.seen_timeouts = []
        self.disconnected = False

    async def execute_tool(self, tool_name, params, request_id=None, timeout=None):
        self.calls.append((tool_name, params))
        self.seen_timeouts.append(timeout)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc is not None:
            raise self.exc
        return self.response

    async def disconnect(self):
        self.disconnected = True
        self.connected = False
        return True


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

    async def test_transport_timeout_exception_labeled_timeout(self):
        """On exact integer timeouts the transport deadline can surface as
        an httpx timeout instead of asyncio.TimeoutError -- it must still
        be labeled reason="timeout", never a generic error."""
        import httpx

        mw = middleware_with(FakeClient(exc=httpx.ReadTimeout("read timed out")))
        mw.timeout_seconds = 2.0  # exact integer boundary
        with pytest.raises(MiddlewareRejectedError) as exc_info:
            await mw.transform(sent_payload())
        assert exc_info.value.reason == "timeout"

    async def test_inner_transport_timeout_is_padded(self):
        """The per-call transport deadline sits past the outer wait_for so
        the outer timeout always fires first (no mislabeled races)."""
        client = FakeClient(response=tool_success(sent_payload()))
        mw = middleware_with(client)
        mw.timeout_seconds = 2.0
        assert mw._inner_timeout == 3
        await mw.transform(sent_payload())
        assert client.seen_timeouts == [3]

    async def test_stale_client_torn_down_on_reconnect(self):
        """A disconnected client is disconnected (best effort) before its
        replacement is constructed -- no leaked stdio pipes."""
        from muxi.runtime.services.mcp.transports import MCPConnectionError

        stale = FakeClient(connected=False)
        mw = RequestMiddleware(command="/nonexistent/middleware-fixture", formation_id=FORMATION_ID)
        mw._client = stale
        with pytest.raises(MCPConnectionError):
            await mw._connect()  # replacement spawn fails; teardown already ran
        assert stale.disconnected is True
        assert mw._client is not stale

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
        _, params = client.calls[0]
        assert "groups" not in params


# ===================================================================
# 5. Identity hand-off: raw id in (emails lowercased), same id kept
# ===================================================================

# (caller's id, id the middleware receives and the pipeline keeps): an
# email-shaped id is lowercased; any other id passes byte-for-byte.
HAND_OFF_IDS = [
    ("U024BE7LH", "U024BE7LH"),
    ("eun_usr_ada", "eun_usr_ada"),
    ("Ada@Example.com", "ada@example.com"),
]
# Ids a middleware may return; the runtime keeps each verbatim, emails too.
RETURNED_IDS = ["Employee-42", "Ada@Example.com"]

RECORDING_MIDDLEWARE = Path(__file__).parent / "fixtures" / "recording_middleware.py"


@pytest.fixture
async def recording_middleware(tmp_path):
    """Start the shipped middleware template as a real stdio MCP server.

    Returns ``start(rewrite_user_id=None) -> (middleware, received)``:
    ``received()`` lists the user_ids the server was sent, verbatim.
    """
    started = []

    async def start(rewrite_user_id=None):
        record = tmp_path / f"received-{len(started)}.jsonl"
        args = [str(RECORDING_MIDDLEWARE), str(record)]
        if rewrite_user_id is not None:
            args.append(rewrite_user_id)
        mw = RequestMiddleware(command=sys.executable, args=tuple(args), formation_id=FORMATION_ID)
        # Tracked before start(): a start that fails after connecting still
        # leaves a subprocess for the teardown to stop.
        started.append(mw)
        await mw.start()

        def received():
            if not record.exists():
                return []
            return [json.loads(line) for line in record.read_text().splitlines()]

        return mw, received

    yield start
    for mw in started:
        await mw.stop()


@pytest.fixture
def clean_request_groups():
    """The pipelines record request groups in a ContextVar; reset after each test."""
    token = gbac_enforcement.set_request_groups(None)
    yield
    gbac_enforcement.reset_request_groups(token)


ATTACHMENT = {"filename": "note.txt", "size": 3, "content": b"abc"}


def make_chat_overlord(request_middleware):
    """An Overlord with only the state chat() reads before slash-command handling.

    ``_process_slash_command`` is the first step after the middleware + RBAC
    pre-check; replacing it records the user_id the pipeline settled on and
    ends the request there.
    """
    overlord = Overlord.__new__(Overlord)
    overlord.is_multi_user = True
    overlord.formation_id = FORMATION_ID
    overlord.input_validator = InputValidator()
    overlord.user_channel_store = None
    overlord._configured_services = (
        {"request_middleware": request_middleware} if request_middleware else {}
    )
    overlord.seen_user_ids = []

    async def record_user_id(message, user_id, session_id):
        overlord.seen_user_ids.append(user_id)
        return MuxiResponse(role="assistant", content="stop")

    overlord._process_slash_command = record_user_id
    return overlord


@pytest.mark.usefixtures("clean_request_groups")
class TestChatIdentityHandOff:
    @pytest.mark.parametrize("files", [None, [ATTACHMENT]], ids=["no-files", "files"])
    @pytest.mark.parametrize(("raw_id", "expected_id"), HAND_OFF_IDS)
    async def test_middleware_receives_user_id(
        self, recording_middleware, raw_id, expected_id, files
    ):
        mw, received = await recording_middleware()
        overlord = make_chat_overlord(mw)

        await overlord.chat("hello", user_id=raw_id, files=files)

        assert received() == [expected_id]
        assert overlord.seen_user_ids == [expected_id]

    @pytest.mark.parametrize("returned_id", RETURNED_IDS)
    async def test_middleware_returned_user_id_is_kept_verbatim(
        self, recording_middleware, returned_id
    ):
        mw, _ = await recording_middleware(rewrite_user_id=returned_id)
        overlord = make_chat_overlord(mw)

        await overlord.chat("hello", user_id="ada@example.com")

        assert overlord.seen_user_ids == [returned_id]

    @pytest.mark.parametrize("files", [None, [ATTACHMENT]], ids=["no-files", "files"])
    @pytest.mark.parametrize(("raw_id", "expected_id"), HAND_OFF_IDS)
    async def test_without_middleware_user_id(self, raw_id, expected_id, files):
        overlord = make_chat_overlord(None)

        await overlord.chat("hello", user_id=raw_id, files=files)

        assert overlord.seen_user_ids == [expected_id]


def memory_formation(request_middleware):
    return SimpleNamespace(
        formation_id=FORMATION_ID,
        request_middleware=request_middleware,
        permission_resolver=None,
    )


@pytest.mark.usefixtures("clean_request_groups")
class TestMemoryRouteIdentityHandOff:
    @pytest.mark.parametrize(("raw_id", "expected_id"), HAND_OFF_IDS)
    async def test_middleware_receives_user_id(self, recording_middleware, raw_id, expected_id):
        mw, received = await recording_middleware()

        user_id, _, error = await _run_request_pipeline(
            memory_formation(mw), raw_id, "req-1", "/v1/memories"
        )

        assert error is None
        assert received() == [expected_id]
        assert user_id == expected_id

    @pytest.mark.parametrize("returned_id", RETURNED_IDS)
    async def test_middleware_returned_user_id_is_kept_verbatim(
        self, recording_middleware, returned_id
    ):
        mw, _ = await recording_middleware(rewrite_user_id=returned_id)

        user_id, _, _ = await _run_request_pipeline(
            memory_formation(mw), "ada@example.com", "req-1", "/v1/memories"
        )

        assert user_id == returned_id

    @pytest.mark.parametrize(("raw_id", "expected_id"), HAND_OFF_IDS)
    async def test_without_middleware_user_id(self, raw_id, expected_id):
        user_id, _, _ = await _run_request_pipeline(
            memory_formation(None), raw_id, "req-1", "/v1/memories"
        )

        assert user_id == expected_id


async def fire_trigger(tmp_path, raw_id, request_middleware):
    """POST a trigger through the real route into a real Overlord.chat().

    Returns the user_id the chat pipeline settled on (see make_chat_overlord).
    """
    (tmp_path / "triggers").mkdir(exist_ok=True)
    (tmp_path / "triggers" / "report.md").write_text("Report\n")
    overlord = make_chat_overlord(None)
    formation = SimpleNamespace(
        formation_id=FORMATION_ID,
        request_middleware=request_middleware,
        permission_resolver=None,
        is_overlord_running=lambda: True,
        get_formation_path=lambda: str(tmp_path),
        _overlord=overlord,
    )
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/triggers/report",
            "raw_path": b"/v1/triggers/report",
            "query_string": b"",
            "headers": [(b"x-muxi-user-id", raw_id.encode())],
            "app": SimpleNamespace(state=SimpleNamespace(formation=formation)),
        }
    )
    await execute_trigger(
        "report", request, TriggerRequest(data={}, use_async=False), BackgroundTasks()
    )
    return overlord.seen_user_ids


@pytest.mark.usefixtures("clean_request_groups")
class TestTriggerRouteIdentityHandOff:
    @pytest.mark.parametrize(("raw_id", "expected_id"), HAND_OFF_IDS)
    async def test_middleware_receives_user_id(
        self, tmp_path, recording_middleware, raw_id, expected_id
    ):
        mw, received = await recording_middleware()

        seen = await fire_trigger(tmp_path, raw_id, mw)

        assert received() == [expected_id]
        assert seen == [expected_id]

    @pytest.mark.parametrize("returned_id", RETURNED_IDS)
    async def test_middleware_returned_user_id_is_kept_verbatim(
        self, tmp_path, recording_middleware, returned_id
    ):
        mw, _ = await recording_middleware(rewrite_user_id=returned_id)

        seen = await fire_trigger(tmp_path, "ada@example.com", mw)

        assert seen == [returned_id]

    @pytest.mark.parametrize(("raw_id", "expected_id"), HAND_OFF_IDS)
    async def test_without_middleware_user_id(self, tmp_path, raw_id, expected_id):
        seen = await fire_trigger(tmp_path, raw_id, None)

        assert seen == [expected_id]
