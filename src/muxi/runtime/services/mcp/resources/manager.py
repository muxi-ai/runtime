"""High-level MCP Resource management."""

from typing import List, Dict, Any, TYPE_CHECKING
from .discovery import MCPResourceDiscovery
from ....datatypes.exceptions import MCPRequestError

if TYPE_CHECKING:
    from ..service import MCPService


class MCPResourceManager:
    """High-level resource management for MCP servers."""

    def __init__(self, service: "MCPService"):
        """Initialize resource manager.

        Args:
            service: MCPService instance for accessing transports
        """
        self.service = service
        self.discovery = MCPResourceDiscovery()

    async def get_resources(self, server_id: str) -> List[Dict[str, Any]]:
        """Get all resources from a specific MCP server.

        Args:
            server_id: ID of the MCP server to query

        Returns:
            List of resource definitions

        Raises:
            MCPRequestError: If server not found or resources query fails
        """
        transport = self.service.get_transport(server_id)
        if not transport:
            raise MCPRequestError(f"MCP server '{server_id}' not found or not connected")

        return await self.discovery.list_resources(transport)

    async def read_resource(self, server_id: str, uri: str) -> str:
        """Read resource content as string from MCP server.

        Args:
            server_id: ID of the MCP server
            uri: Resource URI to read

        Returns:
            Resource content as string

        Raises:
            MCPRequestError: If server not found or resource read fails
        """
        transport = self.service.get_transport(server_id)
        if not transport:
            raise MCPRequestError(f"MCP server '{server_id}' not found or not connected")

        result = await self.discovery.read_resource(transport, uri)
        return self._extract_text_content(result)

    async def read_resource_raw(self, server_id: str, uri: str) -> Dict[str, Any]:
        """Read resource content in raw format from MCP server.

        Args:
            server_id: ID of the MCP server
            uri: Resource URI to read

        Returns:
            Raw resource content with all metadata

        Raises:
            MCPRequestError: If server not found or resource read fails
        """
        transport = self.service.get_transport(server_id)
        if not transport:
            raise MCPRequestError(f"MCP server '{server_id}' not found or not connected")

        return await self.discovery.read_resource(transport, uri)

    async def list_resources_by_type(
        self,
        server_id: str,
        mime_type_filter: str = None
    ) -> List[Dict[str, Any]]:
        """List resources filtered by MIME type.

        Args:
            server_id: ID of the MCP server
            mime_type_filter: MIME type to filter by (e.g., "text/plain")

        Returns:
            Filtered list of resource definitions

        Raises:
            MCPRequestError: If server not found or resources query fails
        """
        resources = await self.get_resources(server_id)

        if mime_type_filter:
            filtered_resources = [
                resource for resource in resources
                if resource.get("mimeType", "").startswith(mime_type_filter)
            ]
            return filtered_resources

        return resources

    async def find_resources_by_name(
        self,
        server_id: str,
        name_pattern: str
    ) -> List[Dict[str, Any]]:
        """Find resources by name pattern.

        Args:
            server_id: ID of the MCP server
            name_pattern: Pattern to match in resource names (case-insensitive)

        Returns:
            List of matching resource definitions

        Raises:
            MCPRequestError: If server not found or resources query fails
        """
        resources = await self.get_resources(server_id)
        pattern_lower = name_pattern.lower()

        matching_resources = [
            resource for resource in resources
            if pattern_lower in resource.get("name", "").lower()
        ]

        return matching_resources

    def _extract_text_content(self, resource_result: Dict[str, Any]) -> str:
        """Extract text content from resource result.

        Args:
            resource_result: Raw resource result from server

        Returns:
            Extracted text content, or string representation if not text
        """
        contents = resource_result.get("contents", [])

        if not contents:
            return ""

        # Try to find text content first
        for content_item in contents:
            if content_item.get("type") == "text":
                return content_item.get("text", "")

        # If no text content, try to convert blob to text
        for content_item in contents:
            if content_item.get("type") == "blob":
                blob_data = content_item.get("blob", "")
                mime_type = content_item.get("mimeType", "")

                # For text-based MIME types, try to decode
                if mime_type.startswith("text/"):
                    try:
                        # Assuming blob is base64 encoded
                        import base64
                        decoded_bytes = base64.b64decode(blob_data)
                        return decoded_bytes.decode('utf-8')
                    except Exception:
                        return f"[Binary content: {mime_type}]"
                else:
                    return f"[Binary content: {mime_type}, size: {len(blob_data)} bytes]"

        # Fallback to string representation
        return str(resource_result)

    def get_resource_summary(self, resources: List[Dict[str, Any]]) -> str:
        """Generate a summary of available resources.

        Args:
            resources: List of resource definitions

        Returns:
            Human-readable summary string
        """
        if not resources:
            return "No resources available"

        summary_lines = [f"📚 Available Resources ({len(resources)} total):"]

        # Group by MIME type
        by_type = {}
        for resource in resources:
            mime_type = resource.get("mimeType", "unknown")
            if mime_type not in by_type:
                by_type[mime_type] = []
            by_type[mime_type].append(resource)

        for mime_type, type_resources in by_type.items():
            summary_lines.append(f"\n  📄 {mime_type} ({len(type_resources)} resources):")

            for resource in type_resources[:3]:  # Show max 3 per type
                name = resource.get("name", "Unnamed")
                uri = resource.get("uri", "")
                summary_lines.append(f"    • {name} ({uri})")

            if len(type_resources) > 3:
                summary_lines.append(f"    ... and {len(type_resources) - 3} more")

        return "\n".join(summary_lines)

    async def test_resource_access(self, server_id: str) -> Dict[str, Any]:
        """Test resource access capabilities for a server.

        Args:
            server_id: ID of the MCP server to test

        Returns:
            Test results with success/failure information
        """
        test_results = {
            "server_id": server_id,
            "list_resources_success": False,
            "read_resource_success": False,
            "resource_count": 0,
            "test_errors": []
        }

        try:
            # Test resource listing
            resources = await self.get_resources(server_id)
            test_results["list_resources_success"] = True
            test_results["resource_count"] = len(resources)

            # Test reading first resource if available
            if resources:
                first_resource = resources[0]
                uri = first_resource.get("uri")

                if uri:
                    try:
                        content = await self.read_resource(server_id, uri)
                        test_results["read_resource_success"] = True
                        test_results["sample_content_length"] = len(content)
                    except Exception as e:
                        test_results["test_errors"].append(f"Resource read failed: {e}")

        except Exception as e:
            test_results["test_errors"].append(f"Resource listing failed: {e}")

        return test_results
