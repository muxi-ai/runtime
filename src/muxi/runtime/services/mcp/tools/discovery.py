"""
Real MCP tool discovery using tools/list protocol.
"""

from typing import List, Dict, Any
from ..transports.base import BaseTransport, MCPRequestError


class MCPToolDiscovery:
    """Real MCP tool discovery using tools/list protocol."""

    async def discover_tools(self, transport: BaseTransport) -> List[Dict[str, Any]]:
        """Discover tools using real MCP tools/list method."""
        try:
            # Send real tools/list request
            response = await transport.send_request({
                "method": "tools/list",
                "params": {}
            })

            if "result" in response and "tools" in response["result"]:
                tools = response["result"]["tools"]
                return self._process_tool_definitions(tools)
            elif "tools" in response:
                # Handle direct tools response
                tools = response["tools"]
                return self._process_tool_definitions(tools)
            else:
                raise MCPRequestError(f"Tool discovery failed: {response}")

        except Exception as e:
            raise MCPRequestError(f"Tool discovery error: {e}")

    def _process_tool_definitions(self, tools: List[Dict]) -> List[Dict[str, Any]]:
        """Process and validate tool definitions."""
        processed_tools = []
        for tool in tools:
            if self._validate_tool_definition(tool):
                processed_tools.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {}),
                    "displayName": tool.get("title", tool["name"]),
                    "protocol_compliant": True
                })
        return processed_tools

    def _validate_tool_definition(self, tool: Dict[str, Any]) -> bool:
        """Validate tool definition has required fields."""
        required_fields = ["name"]
        return all(field in tool for field in required_fields)

    async def get_tool_schema(self, transport: BaseTransport, tool_name: str) -> Dict[str, Any]:
        """Get detailed schema for a specific tool."""
        try:
            # First get all tools
            tools = await self.discover_tools(transport)

            # Find the specific tool
            for tool in tools:
                if tool["name"] == tool_name:
                    return tool["inputSchema"]

            raise MCPRequestError(f"Tool '{tool_name}' not found")

        except Exception as e:
            raise MCPRequestError(f"Error getting tool schema: {e}")

    def format_tool_for_display(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Format tool definition for display in UI."""
        return {
            "id": tool["name"],
            "name": tool.get("displayName", tool["name"]),
            "description": tool.get("description", "No description available"),
            "parameters": self._extract_parameters(tool.get("inputSchema", {})),
            "required": self._extract_required_parameters(tool.get("inputSchema", {})),
            "mcp_compliant": tool.get("protocol_compliant", False)
        }

    def _extract_parameters(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameter definitions from JSON schema."""
        if "properties" in schema:
            return schema["properties"]
        return {}

    def _extract_required_parameters(self, schema: Dict[str, Any]) -> List[str]:
        """Extract required parameter names from JSON schema."""
        if "required" in schema:
            return schema["required"]
        return []
