"""The MCP server FastMCP generates from the formation's FastAPI app.

Serves the production app (``FormationServer``) with uvicorn and connects
with the runtime's own streamable HTTP transport, so the generated server,
the client-key header forwarding into the REST routes, and the client
transport are all exercised for real.
"""

import asyncio
import json
import socket

import pytest
import pytest_asyncio
import uvicorn

from muxi.runtime.formation import Formation
from muxi.runtime.formation.server.server import FormationServer
from muxi.runtime.services.mcp.transports.streamable import StreamableHTTPTransport

CLIENT_KEY_AUTH = {"type": "headers", "headers": {"X-Muxi-Client-Key": "client-key"}}

# One served app per module: serving several FormationServer apps in one
# process intermittently makes the mounted /mcp app answer 500 "No response
# returned." (seen with both mcp 1/fastmcp 3 and mcp 2/fastmcp 4).
pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def mcp_url():
    formation = Formation()
    formation._api_keys = {"admin": "admin-key", "client": "client-key"}
    app = FormationServer(formation)._create_app()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            task.result()
        await asyncio.sleep(0.05)

    yield f"http://127.0.0.1:{port}/mcp/"

    server.should_exit = True
    await task


async def _call(url, auth, name):
    transport = StreamableHTTPTransport(url, request_timeout=10, auth=auth)
    await transport.connect()
    try:
        return await transport.send_request(
            {"method": "tools/call", "params": {"name": name, "arguments": {}}}
        )
    finally:
        await transport.disconnect()


async def test_client_routes_are_listed_as_tools(mcp_url):
    transport = StreamableHTTPTransport(mcp_url, request_timeout=10, auth=CLIENT_KEY_AUTH)
    await transport.connect()
    try:
        listed = await transport.send_request({"method": "tools/list", "params": {}})
    finally:
        await transport.disconnect()

    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {"chat", "list_sops", "search_memories"} <= names
    # FastAPI gives unannotated admin/health routes generated operation IDs.
    # FastMCP must exclude these, even though their names do not start with "admin".
    excluded_prefixes = (
        "get_formation_config",
        "get_formation_status",
        "health_check",
        "root_status",
        "v1_status",
    )
    assert not any(name.startswith(excluded_prefixes) for name in names)


async def test_tool_call_forwards_client_key(mcp_url):
    response = await _call(mcp_url, CLIENT_KEY_AUTH, "list_sops")

    result = response["result"]
    assert result["isError"] is False, result
    assert result["structuredContent"]["data"] == {"sops": [], "count": 0}


async def test_tool_call_without_client_key_is_rejected(mcp_url):
    response = await _call(mcp_url, None, "list_sops")

    result = response["result"]
    assert result["isError"] is True
    text = "".join(block["text"] for block in result["content"])
    assert "401" in text
    assert json.loads(text[text.index("{") :])["error"]["code"] == "UNAUTHORIZED"
