"""
Real MCP tool discovery using tools/list protocol.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from ..transports.base import BaseTransport, MCPRequestError

logger = logging.getLogger(__name__)


class MCPToolDiscovery:
    """Real MCP tool discovery using tools/list protocol."""

    def __init__(self):
        """Initialize tool discovery with caching."""
        self._cached_tools: List[Dict[str, Any]] = []
        self._cache_valid = False

    async def discover_tools(
        self, transport: BaseTransport, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Discover tools using real MCP tools/list method.

        Args:
            transport: MCP transport to use for communication
            use_cache: Whether to use cached results if available

        Returns:
            List of discovered tools
        """
        # Return cached tools if available and requested
        if use_cache and self._cache_valid and self._cached_tools:
            return self._cached_tools

        try:
            # Send real tools/list request
            response = await transport.send_request({"method": "tools/list", "params": {}})

            if "result" in response and "tools" in response["result"]:
                tools = response["result"]["tools"]
                processed_tools = self._process_tool_definitions(tools)
            elif "tools" in response:
                # Handle direct tools response
                tools = response["tools"]
                processed_tools = self._process_tool_definitions(tools)
            else:
                raise MCPRequestError(f"Tool discovery failed: {response}")

            # Cache the results
            self._cached_tools = processed_tools
            self._cache_valid = True

            return processed_tools

        except Exception as e:
            raise MCPRequestError(f"Tool discovery error: {e}")

    def _process_tool_definitions(self, tools: List[Dict]) -> List[Dict[str, Any]]:
        """Process and validate tool definitions."""
        processed_tools = []
        for tool in tools:
            if self._validate_tool_definition(tool):
                processed_tools.append(
                    {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "inputSchema": tool.get("inputSchema", {}),
                        "displayName": tool.get("title", tool["name"]),
                        "protocol_compliant": True,
                    }
                )
        return processed_tools

    def _validate_tool_definition(self, tool: Dict[str, Any]) -> bool:
        """Validate tool definition according to MCP specification.

        Args:
            tool: Tool definition dictionary to validate

        Returns:
            True if tool definition is valid, False otherwise
        """
        try:
            # Check if tool is a dictionary
            if not isinstance(tool, dict):
                logger.debug(f"Tool definition is not a dictionary: {type(tool)}")
                return False

            # Validate required 'name' field
            if "name" not in tool:
                logger.debug("Tool definition missing required 'name' field")
                return False

            name = tool["name"]
            if not isinstance(name, str):
                logger.debug(f"Tool name is not a string: {type(name)}")
                return False

            if not name.strip():
                logger.debug("Tool name is empty or whitespace only")
                return False

            # Validate name format (should be valid identifier)
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*$", name):
                logger.debug(f"Tool name '{name}' contains invalid characters")
                return False

            # Validate optional 'description' field
            if "description" in tool:
                description = tool["description"]
                if not isinstance(description, str):
                    logger.debug(f"Tool description is not a string: {type(description)}")
                    return False

            # Validate optional 'inputSchema' field
            if "inputSchema" in tool:
                input_schema = tool["inputSchema"]
                if not isinstance(input_schema, dict):
                    logger.debug(f"Tool inputSchema is not a dictionary: {type(input_schema)}")
                    return False

                # Validate JSON Schema structure if present
                if not self._validate_json_schema(input_schema):
                    logger.debug(f"Tool '{name}' has invalid inputSchema structure")
                    return False

            # Validate optional 'title' field (used as displayName)
            if "title" in tool:
                title = tool["title"]
                if not isinstance(title, str):
                    logger.debug(f"Tool title is not a string: {type(title)}")
                    return False

            return True

        except Exception as e:
            logger.debug(f"Error validating tool definition: {e}")
            return False

    def _validate_json_schema(self, schema: Dict[str, Any]) -> bool:
        """Validate JSON Schema structure for tool input schema.

        Args:
            schema: JSON Schema dictionary to validate

        Returns:
            True if schema structure is valid, False otherwise
        """
        try:
            # Basic JSON Schema validation
            if not isinstance(schema, dict):
                return False

            # If it has properties, validate the structure
            if "properties" in schema:
                properties = schema["properties"]
                if not isinstance(properties, dict):
                    logger.debug("inputSchema properties field is not a dictionary")
                    return False

                # Validate each property definition
                for prop_name, prop_def in properties.items():
                    if not isinstance(prop_name, str):
                        logger.debug(f"Property name is not a string: {type(prop_name)}")
                        return False
                    if not isinstance(prop_def, dict):
                        logger.debug(f"Property definition for '{prop_name}' is not a dictionary")
                        return False

            # If it has required, validate the structure
            if "required" in schema:
                required = schema["required"]
                if not isinstance(required, list):
                    logger.debug("inputSchema required field is not a list")
                    return False

                # All required items should be strings
                for req_item in required:
                    if not isinstance(req_item, str):
                        logger.debug(f"Required field item is not a string: {type(req_item)}")
                        return False

            # If it has type, it should be a string
            if "type" in schema:
                schema_type = schema["type"]
                if not isinstance(schema_type, str):
                    logger.debug(f"inputSchema type is not a string: {type(schema_type)}")
                    return False

            return True

        except Exception as e:
            logger.debug(f"Error validating JSON schema: {e}")
            return False

    async def get_tool_schema(
        self, transport: BaseTransport, tool_name: str, tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Get detailed schema for a specific tool.

        Args:
            transport: MCP transport to use for communication
            tool_name: Name of the tool to get schema for
            tools: Optional pre-fetched list of tools to search in

        Returns:
            Tool input schema
        """
        try:
            # Use pre-fetched tools if provided, otherwise discover with caching
            if tools is not None:
                available_tools = tools
            else:
                available_tools = await self.discover_tools(transport, use_cache=True)

            # Find the specific tool
            for tool in available_tools:
                if tool["name"] == tool_name:
                    return tool["inputSchema"]

            raise MCPRequestError(f"Tool '{tool_name}' not found")

        except Exception as e:
            raise MCPRequestError(f"Error getting tool schema: {e}")

    def clear_cache(self) -> None:
        """Clear the cached tools."""
        self._cached_tools = []
        self._cache_valid = False

    def is_cache_valid(self) -> bool:
        """Check if the cache contains valid data."""
        return self._cache_valid and bool(self._cached_tools)

    def get_cached_tools(self) -> List[Dict[str, Any]]:
        """Get cached tools without making network requests."""
        if self._cache_valid:
            return self._cached_tools.copy()
        return []

    def format_tool_for_display(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Format tool definition for display in UI."""
        return {
            "id": tool["name"],
            "name": tool.get("displayName", tool["name"]),
            "description": tool.get("description", "No description available"),
            "parameters": self._extract_parameters(tool.get("inputSchema", {})),
            "required": self._extract_required_parameters(tool.get("inputSchema", {})),
            "mcp_compliant": tool.get("protocol_compliant", False),
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
