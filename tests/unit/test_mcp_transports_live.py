"""MCP transports against a real FastMCP server (no mocks).

Each transport connects to ``fixtures/mcp_tool_server.py`` -- over
streamable HTTP, SSE, or stdio -- lists its tools, calls one, and checks
that auth headers reach the server and that request timeouts surface as
MCPTimeoutError.
"""

import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from muxi.runtime.services.mcp.transports import (
    MCPConnectionError,
    MCPRequestError,
    MCPTimeoutError,
)
from muxi.runtime.services.mcp.transports.command import CommandLineTransport
from muxi.runtime.services.mcp.transports.http_sse import HTTPSSETransport
from muxi.runtime.services.mcp.transports.streamable import StreamableHTTPTransport

SERVER = Path(__file__).parent / "fixtures" / "mcp_tool_server.py"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_for_port(port: int, process: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"MCP test server exited early with code {process.returncode}")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise RuntimeError(f"MCP test server did not listen on port {port} within {timeout}s")


@pytest.fixture
async def http_server():
    """Start the test server over a network transport; yields its base URL."""
    processes = []

    async def start(transport: str) -> str:
        port = _free_port()
        process = subprocess.Popen(
            [sys.executable, str(SERVER), transport, str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(process)
        await _wait_for_port(port, process)
        return f"http://127.0.0.1:{port}"

    yield start
    for process in processes:
        process.terminate()
        process.wait(timeout=10)


def _text(response: dict) -> str:
    assert response["status"] == "success", response
    return "".join(block["text"] for block in response["result"]["content"])


async def _exercise(transport) -> None:
    """List tools, call one, and time out a slow one on a connected transport."""
    listed = await transport.send_request({"method": "tools/list", "params": {}})
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert {"echo", "request_auth", "sleep"} <= set(tools)
    # Wire-format (camelCase) keys, as the tool discovery layer reads them
    assert tools["echo"]["inputSchema"]["properties"]["text"]["type"] == "string"

    called = await transport.send_request(
        {"method": "tools/call", "params": {"name": "echo", "arguments": {"text": "hello"}}}
    )
    assert _text(called) == "hello"
    assert called["result"]["isError"] is False

    with pytest.raises(MCPTimeoutError):
        await transport.send_request(
            {"method": "tools/call", "params": {"name": "sleep", "arguments": {"seconds": 5}}},
            timeout=0.5,
        )


async def _received_auth(transport) -> dict:
    response = await transport.send_request(
        {"method": "tools/call", "params": {"name": "request_auth", "arguments": {}}}
    )
    assert response["status"] == "success", response
    return response["result"]["structuredContent"]


class TestStreamableHTTPTransport:
    async def test_lists_calls_and_times_out(self, http_server):
        url = await http_server("http")
        transport = StreamableHTTPTransport(f"{url}/mcp", request_timeout=10)
        await transport.connect()
        try:
            await _exercise(transport)
        finally:
            await transport.disconnect()
        assert not transport.is_connected

    async def test_bearer_auth_reaches_server(self, http_server):
        url = await http_server("http")
        transport = StreamableHTTPTransport(
            f"{url}/mcp", request_timeout=10, auth={"type": "bearer", "token": "s3cret"}
        )
        await transport.connect()
        try:
            assert (await _received_auth(transport))["authorization"] == "Bearer s3cret"
        finally:
            await transport.disconnect()


HTTP_TRANSPORTS = [
    pytest.param(StreamableHTTPTransport, "http", "mcp", id="streamable_http"),
    pytest.param(HTTPSSETransport, "sse", "sse", id="http_sse"),
]


def _assert_caller_not_cancelled() -> None:
    # Since Python 3.12 a failure inside the SDK's task group could cancel the
    # task that entered it; the caller must come out with no pending cancel.
    assert asyncio.current_task().cancelling() == 0


class TestHTTPSessionLifecycle:
    @pytest.mark.parametrize("transport_cls, server_kind, path", HTTP_TRANSPORTS)
    async def test_unreachable_server_raises_connection_error(
        self, transport_cls, server_kind, path
    ):
        transport = transport_cls(f"http://127.0.0.1:{_free_port()}/{path}", request_timeout=3)
        with pytest.raises(MCPConnectionError, match="All connection attempts failed"):
            await transport.connect()
        _assert_caller_not_cancelled()
        await asyncio.sleep(0)
        assert not transport.is_connected

    @pytest.mark.parametrize("transport_cls, server_kind, path", HTTP_TRANSPORTS)
    async def test_server_exit_mid_session_leaves_caller_running(
        self, transport_cls, server_kind, path
    ):
        port = _free_port()
        process = subprocess.Popen(
            [sys.executable, str(SERVER), server_kind, str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            await _wait_for_port(port, process)
            transport = transport_cls(f"http://127.0.0.1:{port}/{path}", request_timeout=10)
            await transport.connect()
            process.terminate()
            process.wait(timeout=10)

            with pytest.raises((MCPRequestError, MCPTimeoutError)):
                await transport.send_request({"method": "tools/list", "params": {}}, timeout=3)
            _assert_caller_not_cancelled()
            await asyncio.sleep(0)
            await transport.disconnect()
            assert not transport.is_connected
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)

    @pytest.mark.parametrize("transport_cls, server_kind, path", HTTP_TRANSPORTS)
    async def test_disconnect_from_another_task(
        self, http_server, transport_cls, server_kind, path
    ):
        url = await http_server(server_kind)
        transport = transport_cls(f"{url}/{path}", request_timeout=10)
        await asyncio.create_task(transport.connect())
        assert transport.is_connected
        await asyncio.create_task(transport.disconnect())
        assert not transport.is_connected
        _assert_caller_not_cancelled()


class TestHTTPSSETransport:
    async def test_lists_calls_and_times_out(self, http_server):
        url = await http_server("sse")
        transport = HTTPSSETransport(f"{url}/sse", request_timeout=10)
        await transport.connect()
        try:
            await _exercise(transport)
        finally:
            await transport.disconnect()
        assert not transport.is_connected

    async def test_api_key_auth_reaches_server(self, http_server):
        url = await http_server("sse")
        transport = HTTPSSETransport(
            f"{url}/sse", request_timeout=10, auth={"type": "api_key", "key": "k-123"}
        )
        await transport.connect()
        try:
            assert (await _received_auth(transport))["x-api-key"] == "k-123"
        finally:
            await transport.disconnect()


class TestCommandLineTransport:
    async def test_lists_calls_and_times_out(self):
        transport = CommandLineTransport(
            sys.executable, args=[str(SERVER), "stdio"], request_timeout=10
        )
        await transport.connect()
        try:
            await _exercise(transport)
        finally:
            await transport.disconnect()
        assert not transport.connected
