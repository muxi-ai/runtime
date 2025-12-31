"""
Utility functions for the Formation server.
"""

import re
from typing import Optional, List, Dict, Any, Set, Tuple, TYPE_CHECKING
from starlette.datastructures import Headers

if TYPE_CHECKING:
    from ..formation import Formation  # noqa: E402

# Precompiled regex patterns for performance
# Pattern to match ${{ secrets.* }} and ${{ user.credentials.* }}
SECRET_REF_PATTERN = re.compile(r"\$\{\{\s*(secrets|user\.credentials)\.([^}]+)\s*\}\}")


def get_header_case_insensitive(headers: Headers, header_name: str) -> Optional[str]:
    """
    Get a header value from the request headers in a case-insensitive manner.

    Args:
        headers: The request headers object
        header_name: The header name to look for (case-insensitive)

    Returns:
        The header value if found, None otherwise
    """
    # Starlette Headers class already handles case-insensitive lookups
    return headers.get(header_name)


def has_header_case_insensitive(headers: Headers, header_name: str) -> bool:
    """
    Check if a header exists in the request headers (case-insensitive).

    Args:
        headers: The request headers object
        header_name: The header name to check for (case-insensitive)

    Returns:
        True if the header exists, False otherwise
    """
    return get_header_case_insensitive(headers, header_name) is not None


def mask_secret_value(
    secret_value: Optional[str], common_prefixes: Optional[List[str]] = None
) -> str:
    """
    Mask a secret value for safe display, preserving identifiable parts.

    This function intelligently masks secrets while keeping useful identifying information:
    - Preserves protocols (https://, mongodb://, etc.)
    - Shows common API key prefixes (sk-, pk-, ghp_, etc.)
    - Displays first and last few characters for identification
    - Handles various secret lengths appropriately

    Args:
        secret_value: The secret value to mask. If None or empty, returns generic mask.
        common_prefixes: List of common API key prefixes to preserve.
                        Defaults to ["sk-", "pk-", "ghp_", "ghs_", "pat_", "key-", "tok-", "lin_"]

    Returns:
        Masked secret value safe for display

    Examples:
        >>> mask_secret_value("sk-1234567890abcdef")
        'sk-12••••••cdef'
        >>> mask_secret_value("https://user:pass@example.com")
        'https://us•••••••.com'
        >>> mask_secret_value("short")
        '••••••••'
    """
    if not secret_value:
        return "••••••••"

    # Default common prefixes if not provided
    if common_prefixes is None:
        common_prefixes = ["sk-", "pk-", "ghp_", "ghs_", "pat_", "key-", "tok-", "lin_"]

    # Check for protocols (preserve these)
    protocol_match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*://)", secret_value)
    protocol = protocol_match.group(1) if protocol_match else ""
    value_after_protocol = secret_value[len(protocol):]

    # Check for common API key prefixes
    prefix_len = 0
    for prefix in common_prefixes:
        if value_after_protocol.startswith(prefix):
            prefix_len = len(prefix)
            break

    if protocol:
        # For URLs with protocols, be more careful about what we show
        # Show protocol + first 2 chars + dots + last few chars
        if len(value_after_protocol) > 8:
            masked_value = f"{protocol}{value_after_protocol[:2]}•••••••{value_after_protocol[-4:]}"
        else:
            masked_value = f"{protocol}••••••••"
    elif len(value_after_protocol) > 12:
        if prefix_len > 0:
            # Show prefix + 2 chars and last 4 chars
            masked_value = f"{value_after_protocol[:prefix_len+2]}••••••{value_after_protocol[-4:]}"
        else:
            # Show first 4 and last 4 characters
            masked_value = f"{value_after_protocol[:4]}••••••••{value_after_protocol[-4:]}"
    elif len(value_after_protocol) > 6:
        # For medium secrets, show first 3 and last 3
        masked_value = f"{value_after_protocol[:3]}••••{value_after_protocol[-3:]}"
    else:
        # For very short secrets, just mask them entirely
        masked_value = "••••••••"

    return masked_value


def extract_secret_references(data: Any, path: str = "") -> Set[Tuple[str, str, str]]:
    """
    Recursively extract all secret and user credential references from a data structure.

    Args:
        data: The data structure to scan (dict, list, or primitive)
        path: Current path for error reporting (used internally for recursion)

    Returns:
        Set of tuples (reference_type, reference_name, path) where:
        - reference_type is either "secret" or "user_credential"
        - reference_name is the extracted name (e.g., "OPENAI_API_KEY" or "github")
        - path is the location in the data structure where it was found
    """
    references = set()

    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            references.update(extract_secret_references(value, new_path))

    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{path}[{i}]"
            references.update(extract_secret_references(item, new_path))

    elif isinstance(data, str):
        # Find all matches in the string using the precompiled pattern
        for match in SECRET_REF_PATTERN.finditer(data):
            ref_type = match.group(1)
            ref_name = match.group(2).strip()

            if ref_type == "secrets":
                references.add(("secret", ref_name, path))
            elif ref_type == "user.credentials":
                references.add(("user_credential", ref_name, path))

    return references


async def validate_secret_references(
    data: Any, formation: "Formation"
) -> Tuple[bool, List[Dict[str, str]]]:
    """
    Validate that all secret and user credential references in the data exist.

    For secrets: Check if the secret exists in the formation's secrets manager.
    For user credentials: Check if a corresponding USER_CREDENTIALS_* secret exists.

    Args:
        data: The data structure to validate
        formation: The Formation instance with access to secrets manager

    Returns:
        Tuple of (is_valid, errors) where:
        - is_valid: True if all references are valid
        - errors: List of error details for missing references
    """
    errors = []
    references = extract_secret_references(data)

    # Check if secrets manager is available
    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        if references:
            errors.append(
                {
                    "type": "SERVICE_UNAVAILABLE",
                    "message": "Secrets manager not available",
                    "details": "Cannot validate secret references without secrets manager",
                }
            )
        return len(errors) == 0, errors

    # Group references by type for better error messages
    missing_secrets = []
    missing_user_credentials = []

    for ref_type, ref_name, path in references:
        if ref_type == "secret":
            # Check if secret exists
            try:
                secret_exists = await formation.secrets_manager.secret_exists(ref_name)
                if not secret_exists:
                    missing_secrets.append(
                        {
                            "name": ref_name,
                            "path": path,
                            "reference": f"${{{{ secrets.{ref_name} }}}}",
                        }
                    )
            except Exception as e:
                # If we can't check the secret, treat it as missing
                missing_secrets.append(
                    {
                        "name": ref_name,
                        "path": path,
                        "reference": f"${{{{ secrets.{ref_name} }}}}",
                        "error": f"Unable to verify: {str(e)}",
                    }
                )

        elif ref_type == "user_credential":
            # For user credentials, check if USER_CREDENTIALS_<NAME> secret exists
            secret_key = f"USER_CREDENTIALS_{ref_name.upper()}"
            try:
                secret_exists = await formation.secrets_manager.secret_exists(secret_key)
                if not secret_exists:
                    missing_user_credentials.append(
                        {
                            "name": ref_name,
                            "path": path,
                            "reference": f"${{{{ user.credentials.{ref_name} }}}}",
                            "required_secret": secret_key,
                        }
                    )
            except Exception as e:
                # If we can't check the secret, treat it as missing
                missing_user_credentials.append(
                    {
                        "name": ref_name,
                        "path": path,
                        "reference": f"${{{{ user.credentials.{ref_name} }}}}",
                        "required_secret": secret_key,
                        "error": f"Unable to verify: {str(e)}",
                    }
                )

    # Build comprehensive error messages
    if missing_secrets:
        errors.append(
            {
                "type": "MISSING_SECRETS",
                "message": f"Missing {len(missing_secrets)} secret(s)",
                "details": "The following secrets are referenced but do not exist",
                "missing": missing_secrets,
            }
        )

    if missing_user_credentials:
        errors.append(
            {
                "type": "MISSING_USER_CREDENTIALS",
                "message": f"Missing {len(missing_user_credentials)} user credential configuration(s)",
                "details": "The following user credentials require corresponding secrets",
                "missing": missing_user_credentials,
            }
        )

    return len(errors) == 0, errors


def render_trigger_template(template: str, data: Dict[str, Any]) -> str:
    """
    Render trigger template with data substitution.

    Supports nested data access using dot notation:
    - ${{ data.key }} - Simple key access
    - ${{ data.nested.key }} - Nested key access
    - ${{ data.user.name }} - Multi-level nesting
    - ${{ data.items.0.name }} - List indexing (numeric segments)

    Args:
        template: Template string with ${{ data.* }} placeholders
        data: Dictionary of data to substitute into template

    Returns:
        Rendered template with all placeholders replaced

    Raises:
        ValueError: If a referenced data key doesn't exist or index is out of range

    Examples:
        >>> render_trigger_template("Hello ${{ data.name }}", {"name": "World"})
        'Hello World'

        >>> render_trigger_template("Issue #${{ data.issue.id }}", {"issue": {"id": 123}})
        'Issue #123'

        >>> render_trigger_template("Label: ${{ data.labels.0.name }}", {"labels": [{"name": "bug"}]})
        'Label: bug'
    """
    # Pattern matches: ${{ data.key }}, ${{ data.nested.key }}, etc.
    pattern = re.compile(r'\$\{\{\s*data\.([a-zA-Z0-9_.]+)\s*\}\}')

    def replace_data(match):
        key_path = match.group(1)
        keys = key_path.split('.')
        value = data

        # Navigate through nested dict/list structure
        for key in keys:
            if isinstance(value, dict):
                # Check if key exists (distinguish from value being None)
                if key not in value:
                    raise ValueError(
                        f"Data key 'data.{key_path}' not found. "
                        f"Available keys: {list(value.keys())}"
                    )
                value = value[key]
            elif isinstance(value, list):
                # Handle list indexing with numeric strings
                if key.isdigit():
                    index = int(key)
                    if 0 <= index < len(value):
                        value = value[index]
                    else:
                        raise ValueError(
                            f"List index {index} out of range at 'data.{key_path}'. "
                            f"List length: {len(value)}"
                        )
                else:
                    raise ValueError(
                        f"Cannot access non-numeric key '{key}' in list at 'data.{key_path}'. "
                        f"Use numeric index (0-{len(value)-1})"
                    )
            else:
                raise ValueError(
                    f"Cannot access '{key}' in non-dict/non-list value at 'data.{key_path}'. "
                    f"Value type: {type(value).__name__}"
                )

        return str(value)

    try:
        return pattern.sub(replace_data, template)
    except ValueError:
        # Re-raise ValueError with context preserved
        raise
    except Exception as e:
        raise ValueError(f"Template rendering failed: {str(e)}")
