"""
Real MCP Integration Tests using actual test servers.

This test suite validates that MUXI's MCP implementation works correctly
with real MCP servers across all transport protocols.
"""

import pytest
import asyncio
import os
from typing import Dict, Any

from tests.mcp.test_server_manager import MCPTestServerManager
from src.muxi.runtime.services.mcp.transports.factory import MCPTransportFactory
from src.muxi.runtime.services.mcp.tools.discovery import MCPToolDiscovery
from src.muxi.runtime.services.mcp.tools.executor import MCPToolExecutor
from src.muxi.runtime.services.mcp.protocol.message_handler import MCPMessageHandler


@pytest.mark.asyncio
class TestRealMCPIntegration:
    """Test MUXI integration with real MCP test servers."""

    @pytest.fixture(scope="class")
    async def server_manager(self):
        """Set up MCP test servers."""
        async with MCPTestServerManager() as manager:
            # Start all MCP servers
            for server_type in manager.get_all_server_types():
                success = await manager.start_server(server_type, auth_enabled=False)
                assert success, f"Failed to start {server_type} server"

                # Verify health
                health_ok = await manager.health_check(server_type)
                assert health_ok, f"{server_type} server health check failed"

            yield manager

    @pytest.fixture
    def transport_factory(self):
        """Create transport factory."""
        return MCPTransportFactory()

    @pytest.fixture
    def tool_discovery(self):
        """Create tool discovery instance."""
        return MCPToolDiscovery()

    @pytest.fixture
    def tool_executor(self):
        """Create tool executor instance."""
        return MCPToolExecutor()

    @pytest.fixture
    def message_handler(self):
        """Create message handler instance."""
        return MCPMessageHandler()

    async def test_stdio_server_integration(
        self,
        server_manager: MCPTestServerManager,
        transport_factory: MCPTransportFactory,
        tool_discovery: MCPToolDiscovery,
        tool_executor: MCPToolExecutor
    ):
        """Test integration with stdio MCP server."""
        # Create stdio transport
        transport = transport_factory.create_transport("command", {
            "command": "python",
            "args": ["mcp-testing-servers/stdio.py"],
            "env": {
                "MCP_STDIO_AUTH_ENABLED": "false"
            }
        })

        try:
            # Connect to server
            success = await transport.connect()
            assert success, "Failed to connect to stdio server"

            # Test tool discovery
            tools = await tool_discovery.discover_tools(transport)
            assert len(tools) > 0, "No tools discovered"

            tool_names = [tool["name"] for tool in tools]
            expected_tools = ["fs_ops", "sys_info", "text_completion"]
            for expected_tool in expected_tools:
                assert expected_tool in tool_names, f"Missing expected tool: {expected_tool}"

            # Test tool execution - sys_info
            result = await tool_executor.execute_tool(
                transport,
                "sys_info",
                {"info_type": "platform"}
            )
            assert result["status"] == "success", f"Tool execution failed: {result}"
            assert len(result["content"]) > 0, "Empty tool result"

            # Test tool execution - fs_ops (list current directory)
            result = await tool_executor.execute_tool(
                transport,
                "fs_ops",
                {"operation": "list", "path": "."}
            )
            assert result["status"] == "success", f"Tool execution failed: {result}"

            # Test text completion
            result = await tool_executor.execute_tool(
                transport,
                "text_completion",
                {"prompt": "Write a simple Python function", "max_tokens": 50}
            )
            assert result["status"] == "success", f"Text completion failed: {result}"

        finally:
            await transport.disconnect()

    async def test_http_sse_server_integration(
        self,
        server_manager: MCPTestServerManager,
        transport_factory: MCPTransportFactory,
        tool_discovery: MCPToolDiscovery,
        tool_executor: MCPToolExecutor
    ):
        """Test integration with HTTP + SSE MCP server."""
        # Ensure server is running
        assert server_manager.is_server_running("http_sse"), "HTTP SSE server not running"

        # Create HTTP SSE transport
        transport = transport_factory.create_transport("http", {
            "url": "http://localhost:8001"
        })

        try:
            # Connect to server
            success = await transport.connect()
            assert success, "Failed to connect to HTTP SSE server"

            # Test tool discovery
            tools = await tool_discovery.discover_tools(transport)
            assert len(tools) > 0, "No tools discovered"

            tool_names = [tool["name"] for tool in tools]
            expected_tools = ["data_proc", "http_client"]
            for expected_tool in expected_tools:
                assert expected_tool in tool_names, f"Missing expected tool: {expected_tool}"

            # Test data processing tool
            test_data = [
                {"name": "alice", "age": 30},
                {"name": "bob", "age": 25}
            ]
            result = await tool_executor.execute_tool(
                transport,
                "data_proc",
                {
                    "operation": "sort",
                    "data": test_data,
                    "field": "name"
                }
            )
            assert result["status"] == "success", f"Data processing failed: {result}"

            # Test HTTP client tool (simple GET request)
            result = await tool_executor.execute_tool(
                transport,
                "http_client",
                {
                    "method": "GET",
                    "url": "https://httpbin.org/status/200"
                }
            )
            assert result["status"] == "success", f"HTTP client failed: {result}"

        finally:
            await transport.disconnect()

    async def test_streamable_http_server_integration(
        self,
        server_manager: MCPTestServerManager,
        transport_factory: MCPTransportFactory,
        tool_discovery: MCPToolDiscovery,
        tool_executor: MCPToolExecutor
    ):
        """Test integration with Streamable HTTP MCP server."""
        # Ensure server is running
        assert server_manager.is_server_running("streamable_http"), "Streamable HTTP server not running"

        # Create streamable HTTP transport
        transport = transport_factory.create_transport("http", {
            "url": "http://localhost:8002"
        })

        try:
            # Connect to server
            success = await transport.connect()
            assert success, "Failed to connect to Streamable HTTP server"

            # Test tool discovery
            tools = await tool_discovery.discover_tools(transport)
            assert len(tools) > 0, "No tools discovered"

            tool_names = [tool["name"] for tool in tools]
            expected_tools = ["rt_data_gen", "async_tasks", "text_completion"]
            for expected_tool in expected_tools:
                assert expected_tool in tool_names, f"Missing expected tool: {expected_tool}"

            # Test real-time data generation (non-streaming)
            result = await tool_executor.execute_tool(
                transport,
                "rt_data_gen",
                {
                    "data_type": "metrics",
                    "count": 3
                }
            )
            assert result["status"] == "success", f"Real-time data generation failed: {result}"

            # Test async task management
            result = await tool_executor.execute_tool(
                transport,
                "async_tasks",
                {
                    "action": "list"
                }
            )
            assert result["status"] == "success", f"Async task management failed: {result}"

            # Test text completion
            result = await tool_executor.execute_tool(
                transport,
                "text_completion",
                {
                    "prompt": "Explain async programming in Python",
                    "max_tokens": 100
                }
            )
            assert result["status"] == "success", f"Text completion failed: {result}"

        finally:
            await transport.disconnect()

    async def test_mcp_protocol_compliance(
        self,
        server_manager: MCPTestServerManager,
        transport_factory: MCPTransportFactory,
        message_handler: MCPMessageHandler
    ):
        """Test MCP protocol compliance across all servers."""

        for server_type in server_manager.get_all_server_types():
            config = server_manager.get_server_config(server_type)
            print(f"\n🧪 Testing MCP protocol compliance for {config.name}")

            if server_type == "stdio":
                transport = transport_factory.create_transport("command", {
                    "command": "python",
                    "args": ["mcp-testing-servers/stdio.py"],
                    "env": {"MCP_STDIO_AUTH_ENABLED": "false"}
                })
            else:
                transport = transport_factory.create_transport("http", {
                    "url": config.url
                })

            try:
                # Connect
                success = await transport.connect()
                assert success, f"Failed to connect to {server_type}"

                # Test initialize protocol (if supported)
                try:
                    response = await transport.send_request({
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "muxi-test", "version": "1.0"}
                        }
                    })
                    print(f"✅ Initialize response: {response.get('result', {}).get('protocolVersion', 'OK')}")
                except Exception as e:
                    print(f"⚠️  Initialize not supported or failed: {e}")

                # Test tools/list
                response = await transport.send_request({
                    "method": "tools/list",
                    "params": {}
                })
                assert "result" in response or "tools" in response, f"Invalid tools/list response from {server_type}"
                print(f"✅ Tools/list: Found tools")

                # Test ping (if supported)
                try:
                    response = await transport.send_request({
                        "method": "ping",
                        "params": {}
                    })
                    print(f"✅ Ping: {response}")
                except Exception as e:
                    print(f"⚠️  Ping not supported: {e}")

            finally:
                await transport.disconnect()

    async def test_error_handling_and_resilience(
        self,
        server_manager: MCPTestServerManager,
        transport_factory: MCPTransportFactory,
        tool_executor: MCPToolExecutor
    ):
        """Test error handling and resilience across servers."""

        # Test with HTTP SSE server
        transport = transport_factory.create_transport("http", {
            "url": "http://localhost:8001"
        })

        try:
            await transport.connect()

            # Test invalid tool call
            result = await tool_executor.execute_tool(
                transport,
                "nonexistent_tool",
                {"param": "value"}
            )
            assert result["status"] == "error", "Should fail for nonexistent tool"

            # Test invalid parameters
            result = await tool_executor.execute_tool(
                transport,
                "data_proc",
                {"invalid_param": "value"}
            )
            # Should either succeed with validation or fail gracefully
            assert result["status"] in ["error", "success"], f"Unexpected status: {result['status']}"

        finally:
            await transport.disconnect()

    async def test_server_status_monitoring(self, server_manager: MCPTestServerManager):
        """Test server status monitoring capabilities."""
        status = await server_manager.get_server_status()

        assert len(status) == 3, "Expected 3 servers"

        for server_type, server_status in status.items():
            print(f"\n📊 {server_status['name']}:")
            print(f"   Running: {server_status['running']}")
            print(f"   Healthy: {server_status['healthy']}")
            print(f"   Type: {server_status['type']}")
            print(f"   URL: {server_status.get('url', 'N/A')}")
            print(f"   Expected Tools: {server_status['expected_tools']}")

            assert server_status["running"], f"Server {server_type} should be running"
            assert server_status["healthy"], f"Server {server_type} should be healthy"

    async def test_tool_schema_validation(
        self,
        server_manager: MCPTestServerManager,
        transport_factory: MCPTransportFactory,
        tool_discovery: MCPToolDiscovery,
        tool_executor: MCPToolExecutor
    ):
        """Test tool schema validation and parameter checking."""

        # Test with stdio server
        transport = transport_factory.create_transport("command", {
            "command": "python",
            "args": ["mcp-testing-servers/stdio.py"],
            "env": {"MCP_STDIO_AUTH_ENABLED": "false"}
        })

        try:
            await transport.connect()

            # Get tool schema
            schema = await tool_discovery.get_tool_schema(transport, "sys_info")
            assert isinstance(schema, dict), "Tool schema should be a dictionary"

            # Test parameter validation
            validation = tool_executor.validate_arguments(
                {"info_type": "cpu"},
                schema
            )
            assert validation["valid"], f"Validation should pass: {validation}"

            # Test invalid parameters
            validation = tool_executor.validate_arguments(
                {"invalid_param": "value"},
                schema
            )
            # Should either fail validation or warn about unknown parameters
            assert not validation["valid"] or len(validation["warnings"]) > 0

        finally:
            await transport.disconnect()


@pytest.mark.asyncio
async def test_quick_integration_smoke_test():
    """Quick smoke test to verify basic integration works."""
    async with MCPTestServerManager() as manager:
        # Start just the HTTP SSE server for quick test
        success = await manager.start_server("http_sse")
        assert success, "Failed to start HTTP SSE server"

        # Quick tool discovery test
        factory = MCPTransportFactory()
        transport = factory.create_transport("http", {"url": "http://localhost:8001"})

        try:
            success = await transport.connect()
            assert success, "Failed to connect"

            discovery = MCPToolDiscovery()
            tools = await discovery.discover_tools(transport)
            assert len(tools) > 0, "Should discover some tools"

        finally:
            await transport.disconnect()
