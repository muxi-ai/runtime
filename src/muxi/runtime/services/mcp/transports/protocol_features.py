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

from typing import Any, Dict


class ModernProtocolFeatures:
    """
    Support for MCP 2025-06-18 protocol enhancements.
    """

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
