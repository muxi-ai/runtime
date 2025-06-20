"""MCP Resources discovery and retrieval implementation."""

from typing import Dict, Any, Optional
from ..transports.base import BaseTransport
from ..protocol.message_handler import MCPMessageHandler
from ....datatypes.exceptions import MCPRequestError


class MCPResourceDiscovery:
    """MCP Resources discovery and retrieval using resources protocol."""

    def __init__(self):
        """Initialize resource discovery."""
        self.message_handler = MCPMessageHandler()

    async def list_resources(self, transport: BaseTransport, cursor: Optional[str] = None) -> Dict[str, Any]:
        """List available resources using resources/list method.

        Args:
            transport: MCP transport to use for communication
            cursor: Optional cursor for pagination

        Returns:
            Dict containing resources list and optional nextCursor for pagination

        Raises:
            MCPRequestError: If resource listing fails
        """
        try:
            # Prepare request parameters
            params = {}
            if cursor:
                params["cursor"] = cursor

            # Send request to MCP server
            response = await transport.send_request({
                "method": "resources/list",
                "params": params
            })

            # Extract resources from result
            result = response.get("result", {})
            resources = result.get("resources", [])

            # Validate resource structure
            validated_resources = []
            for resource in resources:
                self._validate_resource_definition(resource)
                validated_resources.append(resource)

            return {
                "resources": validated_resources,
                "nextCursor": result.get("nextCursor")
            }

        except Exception as e:
            if isinstance(e, MCPRequestError):
                raise
            raise MCPRequestError(f"Failed to list resources: {e}")

    async def read_resource(self, transport: BaseTransport, uri: str) -> Dict[str, Any]:
        """Read a specific resource using resources/read method.

        Args:
            transport: MCP transport to use for communication
            uri: URI of the resource to read

        Returns:
            Resource content with text/blob data and metadata

        Raises:
            MCPRequestError: If resource reading fails
        """
        try:
            # Send request to MCP server
            response = await transport.send_request({
                "method": "resources/read",
                "params": {"uri": uri}
            })

            # Extract resource content from result
            result = response.get("result", {})
            self._validate_resource_content(result)

            return result

        except Exception as e:
            if isinstance(e, MCPRequestError):
                raise
            raise MCPRequestError(f"Failed to read resource '{uri}': {e}")

    def _validate_resource_definition(self, resource: Dict[str, Any]) -> None:
        """Validate resource definition structure.

        Args:
            resource: Resource definition to validate

        Raises:
            MCPRequestError: If resource definition is invalid
        """
        required_fields = ["uri", "name"]

        for field in required_fields:
            if field not in resource:
                raise MCPRequestError(f"Resource definition missing required field: {field}")

        # Validate URI and name are strings
        if not isinstance(resource["uri"], str):
            raise MCPRequestError("Resource URI must be a string")

        if not isinstance(resource["name"], str):
            raise MCPRequestError("Resource name must be a string")

        # Validate optional fields if present
        if "description" in resource and not isinstance(resource["description"], str):
            raise MCPRequestError("Resource description must be a string")

        if "mimeType" in resource and not isinstance(resource["mimeType"], str):
            raise MCPRequestError("Resource mimeType must be a string")

    def _validate_resource_content(self, content: Dict[str, Any]) -> None:
        """Validate resource content structure.

        Args:
            content: Resource content to validate

        Raises:
            MCPRequestError: If resource content is invalid
        """
        # Must have either text or blob content
        has_text = "text" in content
        has_blob = "blob" in content

        if not (has_text or has_blob):
            raise MCPRequestError("Resource content must have either 'text' or 'blob' field")

        if has_text and has_blob:
            raise MCPRequestError("Resource content cannot have both 'text' and 'blob' fields")

        # Validate content types
        if has_text and not isinstance(content["text"], str):
            raise MCPRequestError("Resource text content must be a string")

        if has_blob and not isinstance(content["blob"], str):
            raise MCPRequestError("Resource blob content must be a base64 string")

        # Validate optional mimeType
        if "mimeType" in content and not isinstance(content["mimeType"], str):
            raise MCPRequestError("Resource mimeType must be a string")

    def format_resources_summary(self, resources_result: Dict[str, Any]) -> str:
        """Format a human-readable summary of available resources.

        Args:
            resources_result: Result from list_resources containing resources and optional cursor

        Returns:
            Formatted summary string
        """
        resources = resources_result.get("resources", [])
        next_cursor = resources_result.get("nextCursor")

        if not resources:
            return "No resources available"

        summary_lines = [f"📁 Available Resources ({len(resources)} shown):"]

        for resource in resources:
            uri = resource.get("uri", "No URI")
            name = resource.get("name", "Unnamed")
            description = resource.get("description", "No description")
            mime_type = resource.get("mimeType", "Unknown type")

            summary_lines.append(f"\n  📄 {name}")
            summary_lines.append(f"     URI: {uri}")
            summary_lines.append(f"     Type: {mime_type}")
            summary_lines.append(f"     {description}")

        if next_cursor:
            summary_lines.append(f"\n  ⏭️  More resources available (cursor: {next_cursor})")

        return "\n".join(summary_lines)

    def extract_resource_text(self, resource_content: Dict[str, Any]) -> Optional[str]:
        """Extract text content from resource.

        Args:
            resource_content: Resource content

        Returns:
            Text content if available, None if blob-only
        """
        return resource_content.get("text")

    def get_resource_metadata(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Get metadata information for a resource.

        Args:
            resource: Resource definition or content

        Returns:
            Metadata including URI, name, type, etc.
        """
        metadata = {}

        # Extract available metadata fields
        for field in ["uri", "name", "description", "mimeType"]:
            if field in resource:
                metadata[field] = resource[field]

        return metadata
