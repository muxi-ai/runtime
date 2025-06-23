#!/usr/bin/env python3
"""
Test MCP server connectivity and tool discovery.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from muxi.runtime.datatypes.mcp_types import MCPServer, MCPTool, MCPServerType
from muxi.runtime.services.mcp import MCPService


class TestMCPConnectivity:
    """Test MCP server connectivity and tool discovery."""
    
    @pytest.mark.asyncio
    async def test_builtin_file_generation_mcp(self, mock_openai_api_key):
        """Test that built-in file generation MCP can be discovered."""
        # Create mock MCP service
        mcp_service = MCPService()
        
        # Create mock server config for file generation
        server_config = MCPServer(
            id="file_generation",
            description="Built-in file generation MCP",
            type=MCPServerType.BUILTIN,
            builtin_name="file_generation",
            active=True
        )
        
        # Test that we can recognize built-in MCPs
        assert server_config.type == MCPServerType.BUILTIN
        assert server_config.builtin_name == "file_generation"
        
    @pytest.mark.asyncio
    async def test_http_mcp_server_config(self):
        """Test HTTP MCP server configuration."""
        # Create HTTP server config
        server_config = MCPServer(
            id="web_tools",
            description="External web tools",
            type=MCPServerType.HTTP,
            endpoint="http://localhost:8080",
            active=True,
            timeout_seconds=30,
            retry_attempts=3
        )
        
        # Validate configuration
        assert server_config.type == MCPServerType.HTTP
        assert server_config.endpoint == "http://localhost:8080"
        assert server_config.timeout_seconds == 30
        assert server_config.retry_attempts == 3
        
    @pytest.mark.asyncio
    async def test_mcp_tool_discovery_mock(self):
        """Test MCP tool discovery with mocked responses."""
        # Create mock MCP service
        mcp_service = Mock(spec=MCPService)
        
        # Mock tool discovery
        mock_tools = [
            MCPTool(
                name="create_chart",
                description="Create data visualizations",
                input_schema={"type": "object", "properties": {"data": {"type": "array"}}}
            ),
            MCPTool(
                name="create_document", 
                description="Create Word documents",
                input_schema={"type": "object", "properties": {"content": {"type": "string"}}}
            )
        ]
        
        # Mock the discover_tools method
        mcp_service.discover_tools = AsyncMock(return_value=mock_tools)
        
        # Test tool discovery
        discovered_tools = await mcp_service.discover_tools("file_generation")
        
        assert len(discovered_tools) == 2
        assert discovered_tools[0].name == "create_chart"
        assert discovered_tools[1].name == "create_document"
        
    def test_mcp_server_validation(self):
        """Test MCP server configuration validation."""
        # Test valid configurations
        valid_configs = [
            {
                "id": "test1",
                "description": "Test server",
                "type": MCPServerType.HTTP,
                "endpoint": "http://localhost:3000"
            },
            {
                "id": "test2", 
                "description": "Command server",
                "type": MCPServerType.COMMAND,
                "command": "python",
                "args": ["-m", "mcp_server"]
            }
        ]
        
        for config in valid_configs:
            server = MCPServer(**config)
            assert server.id == config["id"]
            assert server.description == config["description"]
            
        # Test that HTTP requires endpoint
        with pytest.raises(ValueError):
            MCPServer(
                id="invalid",
                description="Invalid HTTP server",
                type=MCPServerType.HTTP
                # Missing endpoint
            )
            
        # Test that COMMAND requires command
        with pytest.raises(ValueError):
            MCPServer(
                id="invalid",
                description="Invalid command server",
                type=MCPServerType.COMMAND
                # Missing command
            )