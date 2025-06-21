"""MCP Templates discovery and retrieval implementation."""

from typing import Dict, Any, Optional, List
from ..transports.base import BaseTransport
from ..protocol.message_handler import MCPMessageHandler
from ....datatypes.exceptions import MCPRequestError


class MCPTemplateDiscovery:
    """MCP Templates discovery and retrieval using resources/templates protocol."""

    def __init__(self):
        """Initialize template discovery."""
        self.message_handler = MCPMessageHandler()

    async def list_templates(self, transport: BaseTransport) -> List[Dict[str, Any]]:
        """List available templates using resources/templates/list method.

        Args:
            transport: MCP transport to use for communication

        Returns:
            List of template definitions with metadata

        Raises:
            MCPRequestError: If template listing fails
        """
        try:
            # Send request to MCP server
            response = await transport.send_request(
                {"method": "resources/templates/list", "params": {}}
            )

            # Extract templates from result
            result = response.get("result", {})
            templates = result.get("templates", [])

            # Validate and process templates
            validated_templates = []
            for template in templates:
                self._validate_template_definition(template)
                validated_templates.append(template)

            return validated_templates

        except Exception as e:
            if isinstance(e, MCPRequestError):
                raise
            raise MCPRequestError(f"Failed to list templates: {e}")

    async def get_template(
        self, transport: BaseTransport, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get a specific template using resources/templates/get method.

        Args:
            transport: MCP transport to use for communication
            name: Name of the template to retrieve
            arguments: Optional arguments for template variable substitution

        Returns:
            Template content with interpolated variables

        Raises:
            MCPRequestError: If template retrieval fails
        """
        try:
            # Prepare request parameters
            params = {"name": name}
            if arguments:
                params["arguments"] = arguments

            # Send request to MCP server
            response = await transport.send_request(
                {"method": "resources/templates/get", "params": params}
            )

            # Extract template content from result
            result = response.get("result", {})
            self._validate_template_content(result)

            return result

        except Exception as e:
            if isinstance(e, MCPRequestError):
                raise
            raise MCPRequestError(f"Failed to get template '{name}': {e}")

    def _validate_template_definition(self, template: Dict[str, Any]) -> None:
        """Validate template definition structure.

        Args:
            template: Template definition to validate

        Raises:
            MCPRequestError: If template definition is invalid
        """
        required_fields = ["name", "uriTemplate"]

        for field in required_fields:
            if field not in template:
                raise MCPRequestError(f"Template definition missing required field: {field}")

        # Validate name and uriTemplate are strings
        if not isinstance(template["name"], str):
            raise MCPRequestError("Template name must be a string")

        if not isinstance(template["uriTemplate"], str):
            raise MCPRequestError("Template uriTemplate must be a string")

        # Validate optional fields if present
        if "description" in template and not isinstance(template["description"], str):
            raise MCPRequestError("Template description must be a string")

        if "mimeType" in template and not isinstance(template["mimeType"], str):
            raise MCPRequestError("Template mimeType must be a string")

    def _validate_template_content(self, content: Dict[str, Any]) -> None:
        """Validate template content structure.

        Args:
            content: Template content to validate

        Raises:
            MCPRequestError: If template content is invalid
        """
        # Must have either text or blob content
        has_text = "text" in content
        has_blob = "blob" in content

        if not (has_text or has_blob):
            raise MCPRequestError("Template content must have either 'text' or 'blob' field")

        if has_text and has_blob:
            raise MCPRequestError("Template content cannot have both 'text' and 'blob' fields")

        # Validate content types
        if has_text and not isinstance(content["text"], str):
            raise MCPRequestError("Template text content must be a string")

        if has_blob and not isinstance(content["blob"], str):
            raise MCPRequestError("Template blob content must be a base64 string")

        # Validate optional mimeType
        if "mimeType" in content and not isinstance(content["mimeType"], str):
            raise MCPRequestError("Template mimeType must be a string")

    def format_templates_summary(self, templates_result: Dict[str, Any]) -> str:
        """Format a human-readable summary of available templates.

        Args:
            templates_result: Result from list_templates containing templates and optional cursor

        Returns:
            Formatted summary string
        """
        templates = templates_result.get("templates", [])
        next_cursor = templates_result.get("nextCursor")

        if not templates:
            return "No templates available"

        summary_lines = [f"📋 Available Templates ({len(templates)} shown):"]

        for template in templates:
            name = template.get("name", "Unnamed")
            uri_template = template.get("uriTemplate", "No URI template")
            description = template.get("description", "No description")
            mime_type = template.get("mimeType", "Unknown type")

            summary_lines.append(f"\n  📄 {name}")
            summary_lines.append(f"     URI Template: {uri_template}")
            summary_lines.append(f"     Type: {mime_type}")
            summary_lines.append(f"     {description}")

        if next_cursor:
            summary_lines.append(f"\n  ⏭️  More templates available (cursor: {next_cursor})")

        return "\n".join(summary_lines)

    def extract_template_text(self, template_content: Dict[str, Any]) -> Optional[str]:
        """Extract text content from template.

        Args:
            template_content: Template content

        Returns:
            Text content if available, None if blob-only
        """
        return template_content.get("text")

    def get_template_metadata(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Get metadata information for a template.

        Args:
            template: Template definition or content

        Returns:
            Metadata including name, uriTemplate, type, etc.
        """
        metadata = {}

        # Extract available metadata fields
        for field in ["name", "uriTemplate", "description", "mimeType"]:
            if field in template:
                metadata[field] = template[field]

        return metadata

    def interpolate_uri_template(self, uri_template: str, parameters: Dict[str, str]) -> str:
        """Interpolate URI template with parameters.

        Args:
            uri_template: URI template string with placeholders
            parameters: Parameters to substitute in the template

        Returns:
            Interpolated URI string

        Note:
            This implements basic string substitution for {variable} placeholders.
            For full RFC 6570 compliance, a proper URI template library should be used.
        """
        interpolated = uri_template

        for key, value in parameters.items():
            placeholder = f"{{{key}}}"
            interpolated = interpolated.replace(placeholder, str(value))

        return interpolated

    def extract_template_variables(self, uri_template: str) -> list[str]:
        """Extract variable names from URI template.

        Args:
            uri_template: URI template string

        Returns:
            List of variable names found in the template
        """
        import re

        # Find all {variable} patterns
        pattern = r"\{([^}]+)\}"
        matches = re.findall(pattern, uri_template)

        # Remove any URI template operators (RFC 6570)
        variables = []
        for match in matches:
            # Remove operators like +, #, ., /, ;, ?, &
            cleaned = re.sub(r"^[+#./;?&]", "", match)
            variables.append(cleaned)

        return variables

    def validate_template_parameters(self, uri_template: str, parameters: Dict[str, str]) -> bool:
        """Validate that all required template parameters are provided.

        Args:
            uri_template: URI template string
            parameters: Parameters provided for interpolation

        Returns:
            True if all required parameters are provided, False otherwise
        """
        required_variables = self.extract_template_variables(uri_template)
        provided_variables = set(parameters.keys())

        return all(var in provided_variables for var in required_variables)
