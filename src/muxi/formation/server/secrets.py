"""
Secret placeholder restoration utilities.

This module provides utilities for restoring original secret placeholders
in configuration data before sending API responses.
"""

import re
from copy import deepcopy
from typing import Any, Dict, List, Union


def restore_secret_placeholders(
    config: Dict[str, Any], placeholder_registry: Dict[str, str]
) -> Dict[str, Any]:
    """
    Restore secret placeholders in configuration data.

    Traverses the placeholder registry and replaces actual secret values
    with their original placeholder strings (e.g., ${{ secrets.API_KEY }}).

    Args:
        config: Configuration dictionary to restore placeholders in
        placeholder_registry: Registry mapping paths to original placeholder values

    Returns:
        Dict[str, Any]: Deep copy of config with placeholders restored
    """
    # Create a deep copy to avoid modifying the original
    safe_config = deepcopy(config)

    # Apply each placeholder restoration
    for path, placeholder in placeholder_registry.items():
        _apply_placeholder_at_path(safe_config, path, placeholder)

    # After restoring placeholders, mask any remaining hardcoded secrets
    mask_hardcoded_secrets(safe_config)

    return safe_config


def _apply_placeholder_at_path(obj: Any, path: str, placeholder: str) -> None:
    """
    Apply a placeholder at a specific path in the object.

    Args:
        obj: Object to modify (dict or list)
        path: Dot-separated path with array indices (e.g., "agents[0].api_key")
        placeholder: Original placeholder value to restore
    """
    # Parse the path into segments
    segments = _parse_path(path)

    # Navigate to the parent of the target
    current = obj
    for segment in segments[:-1]:
        if segment.type == "key":
            if isinstance(current, dict) and segment.value in current:
                current = current[segment.value]
            else:
                # Path doesn't exist in this object
                return
        elif segment.type == "index":
            if isinstance(current, list) and 0 <= segment.value < len(current):
                current = current[segment.value]
            else:
                # Index out of bounds
                return

    # Apply the placeholder at the final segment
    final_segment = segments[-1]
    if final_segment.type == "key" and isinstance(current, dict):
        if final_segment.value in current:
            current[final_segment.value] = placeholder
    elif final_segment.type == "index" and isinstance(current, list):
        if 0 <= final_segment.value < len(current):
            current[final_segment.value] = placeholder


class PathSegment:
    """Represents a segment in a path (either a key or array index)."""

    def __init__(self, type: str, value: Union[str, int]):
        self.type = type  # "key" or "index"
        self.value = value


def _parse_path(path: str) -> List[PathSegment]:
    """
    Parse a path string into segments.

    Examples:
        "llm.api_key" -> [key("llm"), key("api_key")]
        "agents[0].name" -> [key("agents"), index(0), key("name")]
        "mcp.servers[2].env.API_KEY" -> [key("mcp"), key("servers"), index(2), key("env"), key("API_KEY")]

    Args:
        path: Path string to parse

    Returns:
        List[PathSegment]: Parsed path segments
    """
    segments = []
    current_key = ""
    i = 0

    while i < len(path):
        char = path[i]

        if char == ".":
            # End of a key segment
            if current_key:
                segments.append(PathSegment("key", current_key))
                current_key = ""
            i += 1
        elif char == "[":
            # Start of an array index
            if current_key:
                segments.append(PathSegment("key", current_key))
                current_key = ""

            # Find the closing bracket
            j = i + 1
            while j < len(path) and path[j] != "]":
                j += 1

            if j < len(path):
                # Extract the index
                index_str = path[i+1:j]
                try:
                    index = int(index_str)
                    segments.append(PathSegment("index", index))
                except ValueError:
                    # Invalid index, skip
                    pass
                i = j + 1
            else:
                # No closing bracket found
                i += 1
        else:
            # Part of a key
            current_key += char
            i += 1

    # Add any remaining key
    if current_key:
        segments.append(PathSegment("key", current_key))

    return segments


# Known secret paths that should be masked if they contain hardcoded values
KNOWN_SECRET_PATHS = {
    # Server API keys
    "server.api_keys.admin_key",
    "server.api_keys.client_key",

    # LLM API keys
    "llm.api_keys.openai",
    "llm.api_keys.anthropic",
    "llm.api_keys.google",
    "llm.api_keys.cohere",
    "llm.api_keys.huggingface",

    # Agent model API keys
    "agents[*].model.api_key",

    # MCP server environment variables that commonly contain secrets
    "mcp.servers[*].env.API_KEY",
    "mcp.servers[*].env.API_TOKEN",
    "mcp.servers[*].env.SECRET_KEY",
    "mcp.servers[*].env.ACCESS_TOKEN",
    "mcp.servers[*].env.AUTH_TOKEN",

    # Overlord API key
    "overlord.api_key",

    # Database connection strings
    "database.connection_string",
    "memory.database.url",

    # Webhook secrets
    "async.webhook_secret",
    "webhooks.secret",
}

# Patterns to detect different types of API keys
API_KEY_PATTERNS = [
    # OpenAI keys
    re.compile(r'^sk-[a-zA-Z0-9]{20,}$'),
    re.compile(r'^sk-proj-[a-zA-Z0-9]{20,}$'),

    # Anthropic keys
    re.compile(r'^sk-ant-[a-zA-Z0-9-]{40,}$'),

    # Google/GCP keys
    re.compile(r'^AIza[a-zA-Z0-9-_]{35}$'),

    # Generic API key patterns
    re.compile(r'^sk_[a-zA-Z0-9_]{20,}$'),  # Stripe-like keys
    re.compile(r'^[a-f0-9]{32,64}$'),  # MD5/SHA256 hex keys
    re.compile(r'^[A-Z0-9]{20,40}$'),  # All caps keys

    # Muxi-specific keys
    re.compile(r'^sk_muxi_[a-zA-Z0-9_]+$'),
]


def mask_hardcoded_secrets(config: Dict[str, Any]) -> None:
    """
    Mask hardcoded secrets in the configuration.

    This function identifies values that appear to be hardcoded secrets
    (not using ${{ ... }} placeholders) and masks them for security.

    Args:
        config: Configuration dictionary to mask secrets in (modified in place)
    """
    # Process each known secret path
    for path_pattern in KNOWN_SECRET_PATHS:
        _mask_secrets_at_path_pattern(config, path_pattern)

    # Also do a general scan for API key patterns
    _scan_and_mask_api_keys(config)


def _mask_secrets_at_path_pattern(config: Dict[str, Any], path_pattern: str) -> None:
    """
    Mask secrets at paths matching the given pattern.

    Args:
        config: Configuration to process
        path_pattern: Path pattern with wildcards (e.g., "agents[*].api_key")
    """
    # Handle wildcard patterns
    if "[*]" in path_pattern:
        # Split pattern into parts before and after [*]
        parts = path_pattern.split("[*]")
        if len(parts) == 2:
            prefix, suffix = parts
            prefix_segments = _parse_path(prefix) if prefix else []

            # Navigate to the array
            current = config
            for segment in prefix_segments:
                if segment.type == "key" and isinstance(current, dict):
                    if segment.value in current:
                        current = current[segment.value]
                    else:
                        return
                else:
                    return

            # Process each item in the array
            if isinstance(current, list):
                for i in range(len(current)):
                    item_path = f"{prefix}[{i}]{suffix}"
                    _mask_secret_at_exact_path(config, item_path)
    else:
        # Exact path
        _mask_secret_at_exact_path(config, path_pattern)


def _mask_secret_at_exact_path(config: Dict[str, Any], path: str) -> None:
    """
    Mask a secret at an exact path if it's a hardcoded value.

    Args:
        config: Configuration to process
        path: Exact path to the secret
    """
    segments = _parse_path(path)

    # Navigate to the parent
    current = config
    for segment in segments[:-1]:
        if segment.type == "key" and isinstance(current, dict):
            if segment.value in current:
                current = current[segment.value]
            else:
                return
        elif segment.type == "index" and isinstance(current, list):
            if 0 <= segment.value < len(current):
                current = current[segment.value]
            else:
                return
        else:
            return

    # Check the final value
    final_segment = segments[-1]
    if final_segment.type == "key" and isinstance(current, dict):
        if final_segment.value in current:
            value = current[final_segment.value]
            if _should_mask_value(value):
                current[final_segment.value] = _mask_value(value)


def _scan_and_mask_api_keys(obj: Any, path: str = "") -> None:
    """
    Recursively scan for and mask API keys based on patterns.

    Args:
        obj: Object to scan (dict, list, or primitive)
        path: Current path for tracking
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            if isinstance(value, str) and _looks_like_api_key(value):
                if _should_mask_value(value):
                    obj[key] = _mask_value(value)
            else:
                _scan_and_mask_api_keys(value, new_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            _scan_and_mask_api_keys(item, new_path)


def _should_mask_value(value: Any) -> bool:
    """
    Check if a value should be masked.

    Values starting with ${{ are template placeholders and should not be masked.

    Args:
        value: Value to check

    Returns:
        bool: True if the value should be masked
    """
    if not isinstance(value, str):
        return False

    # Don't mask template placeholders
    if value.strip().startswith("${{") and value.strip().endswith("}}"):
        return False

    # Don't mask already masked values
    if "•" in value or "***" in value:
        return False

    # Don't mask empty or very short values
    if len(value) < 8:
        return False

    return True


def _looks_like_api_key(value: str) -> bool:
    """
    Check if a value looks like an API key based on common patterns.

    Args:
        value: String value to check

    Returns:
        bool: True if the value matches API key patterns
    """
    # Check against known patterns
    for pattern in API_KEY_PATTERNS:
        if pattern.match(value):
            return True

    # Additional heuristics
    # High entropy strings that look like keys
    if len(value) > 20 and any(prefix in value.lower() for prefix in ['sk_', 'pk_', 'api_', 'key_']):
        return True

    return False


def _mask_value(value: str) -> str:
    """
    Mask a secret value, showing only hints for identification.

    Args:
        value: Value to mask

    Returns:
        str: Masked value
    """
    if len(value) <= 12:
        return "••••••••"

    # For longer values, show first few and last few characters
    if value.startswith(("sk_", "pk_", "api_", "key_")):
        # Show the prefix and last 4 characters
        prefix_end = value.find("_") + 1
        if prefix_end > 0 and prefix_end < len(value):
            return f"{value[:prefix_end]}{'•' * 8}{value[-4:]}"

    # For other patterns, show first 3 and last 3 characters
    return f"{value[:3]}{'•' * 8}{value[-3:]}"
