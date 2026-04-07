import asyncio

import pytest

from muxi.runtime.services.mcp.handler import MCPServerClient
from muxi.runtime.services.mcp.service import LiveConnection, MCPService
from muxi.runtime.services.mcp.transports import MCPTimeoutError
from muxi.runtime.services.mcp.transports.factory import MCPTransportFactory
from muxi.runtime.services.mcp.transports.http_sse import HTTPSSETransport
from muxi.runtime.services.mcp.transports.streamable import StreamableHTTPTransport


class SlowSession:
    async def call_tool(self, tool_name, arguments):
        await asyncio.sleep(0.05)


class DummyTransport:
    def __init__(self):
        self.connected = False

    async def connect(self):
        self.connected = True
        return True

    async def disconnect(self):
        self.connected = False
        return True


class TestHTTPTransports:
    @pytest.mark.asyncio
    async def test_streamable_transport_enforces_per_request_timeout(self):
        transport = StreamableHTTPTransport("https://example.com/mcp", request_timeout=0.01)
        transport.connected = True
        transport.session = SlowSession()

        with pytest.raises(MCPTimeoutError):
            await transport.send_request(
                {"method": "tools/call", "params": {"name": "profile", "arguments": {}}}
            )

    @pytest.mark.asyncio
    async def test_http_sse_transport_enforces_per_request_timeout(self):
        transport = HTTPSSETransport("https://example.com/sse", request_timeout=0.01)
        transport.connected = True
        transport.session = SlowSession()

        with pytest.raises(MCPTimeoutError):
            await transport.send_request(
                {"method": "tools/call", "params": {"name": "profile", "arguments": {}}}
            )


class TestTransportSelection:
    @pytest.mark.asyncio
    async def test_explicit_transport_type_uses_direct_transport(self, monkeypatch):
        created_transport_types = []

        def fake_create_transport(*, transport_type=None, **kwargs):
            created_transport_types.append(transport_type)
            return DummyTransport()

        async def fake_create_transport_with_fallback(**kwargs):
            raise AssertionError("Fallback transport creation should not be used")

        monkeypatch.setattr(
            MCPTransportFactory, "create_transport", staticmethod(fake_create_transport)
        )
        monkeypatch.setattr(
            MCPTransportFactory,
            "create_transport_with_fallback",
            staticmethod(fake_create_transport_with_fallback),
        )

        client = MCPServerClient(
            "ms365",
            url="https://example.com/mcp",
            request_timeout=30,
            transport_type=MCPTransportFactory.TRANSPORT_HTTP_SSE,
        )

        assert await client.connect() is True
        assert created_transport_types == [MCPTransportFactory.TRANSPORT_HTTP_SSE]


class TestMCPServiceRequestLifecycle:
    def _make_service(self):
        MCPService._instance = None
        return MCPService()

    @pytest.mark.asyncio
    async def test_invoke_tool_passes_request_tracking_to_execution(self, monkeypatch):
        service = self._make_service()
        service.server_configs["ms365"] = {"stored_credentials": {}, "request_timeout": 60}

        captured = {}

        async def fake_execute_tool_ephemeral(**kwargs):
            captured.update(kwargs)
            raise RuntimeError("boom")

        monkeypatch.setattr(service, "_execute_tool_ephemeral", fake_execute_tool_ephemeral)

        result = await service.invoke_tool(
            "ms365",
            "profile",
            {},
            request_id="req-123",
        )

        assert result["status"] == "error"
        assert captured["request_id"] == "req-123"
        assert captured["cancellation_token"] is not None

    @pytest.mark.asyncio
    async def test_cancel_requests_for_request_closes_live_connections(self):
        service = self._make_service()

        class FakeHandler:
            def __init__(self):
                self.cancelled = []
                self.disconnected = []

            def cancel_requests_by_overlord_id(self, request_id):
                self.cancelled.append(request_id)
                return 1

            async def disconnect_server(self, server_name):
                self.disconnected.append(server_name)

        handler = FakeHandler()
        service._live_connections["ms365:no_creds"] = LiveConnection(
            handler=handler, server_name="ms365"
        )

        cancelled = await service.cancel_requests_for_request("req-1")

        assert cancelled == 1
        assert handler.cancelled == ["req-1"]
        assert handler.disconnected == ["ms365"]
        assert service._live_connections == {}

    @pytest.mark.asyncio
    async def test_cancelled_live_request_closes_poisoned_connection(self):
        service = self._make_service()
        service.server_configs["ms365"] = {
            "url": "https://example.com/mcp",
            "request_timeout": 60,
            "transport_type": MCPTransportFactory.TRANSPORT_STREAMABLE_HTTP,
        }

        class FakeLiveHandler:
            def is_server_connected(self, server_name):
                return True

            async def execute_tool(self, **kwargs):
                raise asyncio.CancelledError

            async def disconnect_server(self, server_name):
                self.disconnected = server_name

        handler = FakeLiveHandler()
        key = "ms365:no_creds"
        service._live_connections[key] = LiveConnection(handler=handler, server_name="ms365")

        with pytest.raises(asyncio.CancelledError):
            await service._execute_tool_ephemeral(
                "ms365",
                "profile",
                {},
                request_id="req-2",
            )

        assert key not in service._live_connections
        assert handler.disconnected == "ms365"
