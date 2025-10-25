"""
Input Validation Module

Provides centralized input validation to prevent denial-of-service attacks
and enforce reasonable input boundaries across the MUXI Runtime.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class InputValidationError(ValueError):
    """Raised when input validation fails."""

    pass


@dataclass
class InputLimits:
    """Configurable input size limits."""

    max_message_length: int = 100_000  # 100KB
    max_file_size_bytes: int = 52_428_800  # 50MB
    max_memory_entry_size: int = 10_000  # 10KB
    max_tool_output_size: int = 1_048_576  # 1MB
    max_batch_items: int = 100  # Max items in batch operations

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "InputLimits":
        """
        Create InputLimits from formation configuration.

        Args:
            config: Formation configuration dict with 'input_limits' section

        Returns:
            InputLimits instance with configured or default values
        """
        if not config or "input_limits" not in config:
            return cls()  # Use defaults

        limits_config = config["input_limits"]
        return cls(
            max_message_length=limits_config.get("max_message_length", cls.max_message_length),
            max_file_size_bytes=limits_config.get(
                "max_file_size_bytes", cls.max_file_size_bytes
            ),
            max_memory_entry_size=limits_config.get(
                "max_memory_entry_size", cls.max_memory_entry_size
            ),
            max_tool_output_size=limits_config.get(
                "max_tool_output_size", cls.max_tool_output_size
            ),
            max_batch_items=limits_config.get("max_batch_items", cls.max_batch_items),
        )


class InputValidator:
    """Validates input sizes before processing."""

    def __init__(self, limits: Optional[InputLimits] = None):
        """
        Initialize the input validator.

        Args:
            limits: Input limits configuration. If None, uses defaults.
        """
        self.limits = limits or InputLimits()

    def validate_message(self, message: str) -> None:
        """
        Validate chat message length.

        Args:
            message: Chat message to validate

        Raises:
            InputValidationError: If message exceeds maximum length
        """
        length = len(message)
        if length > self.limits.max_message_length:
            raise InputValidationError(
                f"Message too long: {length:,} characters "
                f"(max: {self.limits.max_message_length:,}).\n\n"
                "Try:\n"
                "- Breaking into multiple messages\n"
                "- Uploading content as a file\n"
                "- Summarizing the key points"
            )

    def validate_file_upload(self, filename: str, size_bytes: int) -> None:
        """
        Validate file upload size.

        Args:
            filename: Name of the file being uploaded
            size_bytes: Size of the file in bytes

        Raises:
            InputValidationError: If file exceeds maximum size
        """
        if size_bytes > self.limits.max_file_size_bytes:
            raise InputValidationError(
                f"File '{filename}' too large: {size_bytes:,} bytes "
                f"({size_bytes / 1_000_000:.1f}MB) "
                f"(max: {self.limits.max_file_size_bytes / 1_000_000:.0f}MB).\n\n"
                "Try:\n"
                "- Compressing the file (zip, gzip)\n"
                "- Splitting into smaller files\n"
                "- Uploading to cloud storage and sharing a link"
            )

    def validate_memory_entry(self, content: str) -> None:
        """
        Validate memory entry size.

        Args:
            content: Memory entry content to validate

        Raises:
            InputValidationError: If entry exceeds maximum size
        """
        length = len(content)
        if length > self.limits.max_memory_entry_size:
            raise InputValidationError(
                f"Memory entry too large: {length:,} characters "
                f"(max: {self.limits.max_memory_entry_size:,}).\n\n"
                "Memory entries should be concise summaries, not full documents."
            )

    def validate_tool_output(self, output: Any, tool_name: str = "tool") -> None:
        """
        Validate tool output size.

        Args:
            output: Tool output to validate (will be converted to string for size check)
            tool_name: Name of the tool for error message

        Raises:
            InputValidationError: If output exceeds maximum size
        """
        # Convert to string for size validation
        output_str = str(output)
        size_bytes = len(output_str.encode("utf-8"))

        if size_bytes > self.limits.max_tool_output_size:
            raise InputValidationError(
                f"Tool '{tool_name}' output too large: {size_bytes:,} bytes "
                f"({size_bytes / 1_000_000:.1f}MB) "
                f"(max: {self.limits.max_tool_output_size / 1_000_000:.0f}MB).\n\n"
                "Try:\n"
                "- Paginating results\n"
                "- Filtering or aggregating data\n"
                "- Writing results to a file instead"
            )

    def validate_batch_size(self, items: List[Any]) -> None:
        """
        Validate batch operation size.

        Args:
            items: List of items in the batch

        Raises:
            InputValidationError: If batch exceeds maximum size
        """
        count = len(items)
        if count > self.limits.max_batch_items:
            raise InputValidationError(
                f"Batch too large: {count} items "
                f"(max: {self.limits.max_batch_items}).\n\n"
                "Break into smaller batches for processing."
            )
