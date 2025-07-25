"""
Test for real MCP tool discovery and execution.
"""

import pytest

from src.muxi.services.mcp.tools.discovery import MCPToolDiscovery
from src.muxi.services.mcp.tools.executor import MCPToolExecutor
from src.muxi.services.mcp.transports.base import BaseTransport, MCPRequestError


class MockTransport(BaseTransport):
    """Mock transport for testing."""

    def __init__(self):
        super().__init__("http://test", 30)
        self.connected = True
        self.responses = {}

    def set_response(self, method: str, response: dict):
        """Set response for a specific method."""
        self.responses[method] = response

    async def send_request(self, request_obj: dict, timeout: int = None) -> dict:
        """Mock send request."""
        method = request_obj.get("method")
        if method in self.responses:
            return self.responses[method]
        else:
            raise MCPRequestError(f"No mock response for method: {method}")


class TestMCPToolDiscovery:
    """Test real MCP tool discovery."""

    @pytest.fixture
    def discovery(self):
        """Create discovery instance."""
        return MCPToolDiscovery()

    @pytest.fixture
    def mock_transport(self):
        """Create mock transport."""
        return MockTransport()

    @pytest.mark.asyncio
    async def test_discover_tools_success(self, discovery, mock_transport):
        """Test successful tool discovery."""
        mock_tools_response = {
            "result": {
                "tools": [
                    {
                        "name": "test_tool",
                        "description": "A test tool",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "param1": {"type": "string"}
                            },
                            "required": ["param1"]
                        }
                    }
                ]
            }
        }

        mock_transport.set_response("tools/list", mock_tools_response)

        tools = await discovery.discover_tools(mock_transport)

        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"
        assert tools[0]["description"] == "A test tool"
        assert tools[0]["protocol_compliant"] is True

    @pytest.mark.asyncio
    async def test_get_tool_schema(self, discovery, mock_transport):
        """Test getting tool schema."""
        mock_tools_response = {
            "result": {
                "tools": [
                    {
                        "name": "schema_tool",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "param1": {"type": "string"}
                            },
                            "required": ["param1"]
                        }
                    }
                ]
            }
        }

        mock_transport.set_response("tools/list", mock_tools_response)

        schema = await discovery.get_tool_schema(mock_transport, "schema_tool")

        assert "properties" in schema
        assert "param1" in schema["properties"]


class TestMCPToolExecutor:
    """Test real MCP tool executor."""

    @pytest.fixture
    def executor(self):
        """Create executor instance."""
        return MCPToolExecutor()

    @pytest.fixture
    def mock_transport(self):
        """Create mock transport."""
        return MockTransport()

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, executor, mock_transport):
        """Test successful tool execution."""
        mock_response = {
            "result": {
                "content": [
                    {"type": "text", "text": "Tool executed successfully"}
                ],
                "isError": False
            }
        }

        mock_transport.set_response("tools/call", mock_response)

        result = await executor.execute_tool(
            mock_transport,
            "test_tool",
            {"param1": "value1"}
        )

        assert result["status"] == "success"
        assert result["tool_name"] == "test_tool"
        assert len(result["content"]) == 1
        assert result["isError"] is False

    def test_validate_arguments_valid(self, executor):
        """Test argument validation with valid arguments."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"}
            },
            "required": ["name"]
        }

        arguments = {
            "name": "John",
            "age": 30
        }

        validation = executor.validate_arguments(arguments, schema)

        assert validation["valid"] is True
        assert len(validation["errors"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
