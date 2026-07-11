# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Modern Protocol Features - MCP 2025-06-18 Support
# Description:  Support for modern MCP protocol enhancements and features
# Role:         Handles advanced MCP features like structured output and elicitation
# Usage:        Used by transports and service to support latest MCP protocol
# Author:       Muxi Framework Team
#
# The Modern Protocol Features module provides support for MCP 2025-06-18
# protocol enhancements, including:
#
# 1. Structured Output Support
#    - Processing of structured tool output format
#    - Resource links in tool results
#    - Enhanced metadata handling
#
# 2. Display Name Enhancement
#    - Human-friendly tool names using title field
#    - Fallback to name field for compatibility
#
# 3. Elicitation Request Handling
#    - Server requests for additional user information
#    - Structured prompt and field definitions
#    - Response format standardization
#
# This module implements the protocol enhancements specified in the
# Streamable HTTP implementation plan Phase 2.3.
# =============================================================================

from typing import Any, Dict, List, Optional


class ModernProtocolFeatures:
    """
    Support for MCP 2025-06-18 protocol enhancements.
    """

    @staticmethod
    def _ui_resource_entry(item: Any) -> Optional[Dict[str, Any]]:
        """
        Recognize an MCP Apps UI resource inside a tool-result content
        block (Response Envelope UI PRD, P2 — the gateway passthrough).

        v1 detection is deliberately narrow and honest: an *embedded
        resource* block (``type: "resource"``, the SDK's
        ``EmbeddedResource``) whose resource URI uses the ``ui://``
        scheme — the MCP Apps convention for UI resources. Both text
        (``TextResourceContents``) and binary (``BlobResourceContents``,
        base64) contents are relayed. ``resource_link`` blocks are NOT
        relayed: they carry no data, and MUXI does not proxy ``ui://``
        resource fetches.

        Handles both dict-shaped blocks (``model_dump()`` output from
        the transports) and attribute-shaped SDK objects.

        Returns:
            ``{"uri", "data", "encoding", "mime_type"?}`` with the
            content relayed verbatim, or None when the block is not a
            UI resource.
        """
        if isinstance(item, dict):
            block_type = item.get("type")
            resource = item.get("resource")
        else:
            block_type = getattr(item, "type", None)
            resource = getattr(item, "resource", None)
        if block_type != "resource" or resource is None:
            return None

        if isinstance(resource, dict):
            uri = resource.get("uri")
            mime_type = resource.get("mimeType")
            text = resource.get("text")
            blob = resource.get("blob")
        else:
            uri = getattr(resource, "uri", None)
            mime_type = getattr(resource, "mimeType", None)
            text = getattr(resource, "text", None)
            blob = getattr(resource, "blob", None)

        # Transports hand us model_dump() output where uri is a
        # pydantic AnyUrl — normalize to the plain string.
        uri = str(uri) if uri is not None else ""
        if not uri.startswith("ui://"):
            return None

        if isinstance(text, str) and text:
            entry: Dict[str, Any] = {"uri": uri, "data": text, "encoding": "text"}
        elif isinstance(blob, str) and blob:
            entry = {"uri": uri, "data": blob, "encoding": "base64"}
        else:
            return None
        if mime_type:
            entry["mime_type"] = str(mime_type)
        return entry

    @staticmethod
    def extract_ui_resources(result: Any) -> List[Dict[str, Any]]:
        """
        Extract MCP Apps UI resources (``ui://`` embedded resources)
        from a raw tool result, before content flattening loses the
        block structure.

        Args:
            result: Raw tool result (dict from ``model_dump()`` or a
                CallToolResult-shaped object).

        Returns:
            List of relay entries (see ``_ui_resource_entry``), empty
            when the result carries none.
        """
        if isinstance(result, dict):
            content = result.get("content")
        else:
            content = getattr(result, "content", None)
        if not isinstance(content, list):
            return []

        entries = []
        for item in content:
            entry = ModernProtocolFeatures._ui_resource_entry(item)
            if entry is not None:
                entries.append(entry)
        return entries

    @staticmethod
    def extract_display_name(tool_info: Dict[str, Any]) -> str:
        """
        Extract human-friendly display name using new title field.

        Priority: title > name (2025-06-18 spec compliance)

        Args:
            tool_info: Tool information dictionary from MCP server

        Returns:
            Human-friendly display name for the tool
        """
        if tool_info is None:
            return "Unnamed Tool"

        title = tool_info.get("title", "")
        if title and title.strip():
            return title

        name = tool_info.get("name", "")
        if name and name.strip():
            return name

        return "Unnamed Tool"

    @staticmethod
    def process_structured_output(result: Any) -> Dict[str, Any]:
        """
        Process structured tool output format introduced in 2025-06-18.

        Args:
            result: Raw result from tool execution

        Returns:
            Standardized structured output format
        """

        def _extract_content_text(content: Any) -> str:
            """Extract joined text content from modern MCP content blocks."""
            if not content:
                return str(content) if content is not None else ""

            if isinstance(content, list):
                content_parts = []
                for item in content:
                    # UI resources (ui:// embedded resources) are
                    # untrusted external content relayed verbatim to the
                    # client as mcp_resource widgets — they are never
                    # flattened into the LLM-visible text. The server's
                    # accompanying text blocks carry the model-facing
                    # summary.
                    if ModernProtocolFeatures._ui_resource_entry(item) is not None:
                        continue
                    if isinstance(item, dict):
                        text_value = item.get("text")
                        content_parts.append(
                            str(text_value) if text_value is not None else str(item)
                        )
                    else:
                        text_value = getattr(item, "text", None)
                        content_parts.append(
                            str(text_value) if text_value is not None else str(item)
                        )
                return "\n".join(part for part in content_parts if part)

            return str(content)

        # Handle dict results (e.g., from streamable HTTP transport)
        if isinstance(result, dict) and "content" in result:
            content = result.get("content")
            content_text = _extract_content_text(content)
            return {
                "content": content_text,
                "isError": result.get("isError", False),
                "links": result.get("links", []),
                "_meta": result.get("meta") or {},
                "structured_content": (
                    result.get("structuredContent") or result.get("structured_content") or {}
                ),
                "type": "structured",
            }

        if hasattr(result, "content") and hasattr(result, "isError"):
            # Handle _meta attribute carefully to avoid mock objects
            meta_attr = getattr(result, "_meta", None)
            if meta_attr is None or (hasattr(meta_attr, "_mock_name")):
                # Handle case where _meta doesn't exist or is a mock
                meta_value = {}
            else:
                meta_value = meta_attr

            content = getattr(result, "content", None)
            content_text = _extract_content_text(content)

            return {
                "content": content_text,
                "isError": getattr(result, "isError", False),
                "links": getattr(result, "links", []),
                "_meta": meta_value,
                "structured_content": (
                    getattr(result, "structuredContent", None)
                    or getattr(result, "structured_content", None)
                    or {}
                ),
                "type": "structured",
            }

        # Legacy format
        return {
            "content": result,
            "isError": False,
            "links": [],
            "_meta": {},
            "structured_content": {},
            "type": "legacy",
        }

    @staticmethod
    def handle_elicitation_request(elicitation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle server elicitation requests for additional user information.

        This is a new feature in 2025-06-18 that allows servers to request
        additional context from users during tool interactions.

        Args:
            elicitation_data: Elicitation request data from server

        Returns:
            Standardized elicitation request format
        """
        if elicitation_data is None:
            elicitation_data = {}

        return {
            "type": "elicitation",
            "prompt": elicitation_data.get("prompt", "Additional information needed"),
            "fields": elicitation_data.get("fields", []),
            "required": elicitation_data.get("required", []),
            "_meta": elicitation_data.get("_meta", {}),
        }
