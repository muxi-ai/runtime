"""Compatibility with real MCP 2 models and their protocol aliases."""

import pytest
from mcp.shared.message import SessionMessage
from mcp.types import (
    CallToolResult,
    EmbeddedResource,
    ErrorData,
    JSONRPCError,
    JSONRPCResponse,
    TextContent,
    TextResourceContents,
)

from muxi.runtime.services.mcp.protocol.message_handler import MCPMessageHandler
from muxi.runtime.services.mcp.transports.protocol_features import ModernProtocolFeatures


@pytest.mark.parametrize("wire_dict", [False, True])
def test_structured_output_preserves_error_metadata_and_ui_resource(wire_dict):
    result = CallToolResult(
        content=[
            TextContent(type="text", text="summary"),
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri="ui://test/panel", mime_type="text/html", text="<p>panel</p>"
                ),
            ),
        ],
        is_error=True,
        meta={"source": "test"},
        structured_content={"value": 42},
    )
    raw = result.model_dump(by_alias=True) if wire_dict else result

    processed = ModernProtocolFeatures.process_structured_output(raw)

    assert processed["content"] == "summary"
    assert processed["isError"] is True
    assert processed["_meta"] == {"source": "test"}
    assert processed["structured_content"] == {"value": 42}
    assert ModernProtocolFeatures.extract_ui_resources(raw) == [
        {
            "uri": "ui://test/panel",
            "data": "<p>panel</p>",
            "encoding": "text",
            "mime_type": "text/html",
        }
    ]


def test_session_message_response_uses_plain_union():
    message = SessionMessage(
        message=JSONRPCResponse(jsonrpc="2.0", id="request-1", result={"value": 42})
    )

    assert MCPMessageHandler().parse_response(message) == {
        "status": "success",
        "result": {"value": 42},
        "id": "request-1",
        "jsonrpc": "2.0",
    }


def test_session_message_error_uses_plain_union():
    message = SessionMessage(
        message=JSONRPCError(
            jsonrpc="2.0",
            id="request-1",
            error=ErrorData(code=-32601, message="Unknown method", data={"method": "test"}),
        )
    )

    assert MCPMessageHandler().parse_response(message) == {
        "status": "error",
        "error": {"code": -32601, "message": "Unknown method", "data": {"method": "test"}},
        "id": "request-1",
        "jsonrpc": "2.0",
    }
