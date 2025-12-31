# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Transport Authentication Utilities
# Description:  Shared authentication classes and utilities for MCP transports
# Role:         Provides httpx.Auth implementations for various auth types
# Usage:        Used by HTTP-based MCP transports for authentication
# Author:       Muxi Framework Team
# =============================================================================

import httpx
from typing import Optional, Dict, Any


class BearerAuth(httpx.Auth):
    """Bearer token authentication for httpx."""

    def __init__(self, token: str):
        self.token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class ApiKeyAuth(httpx.Auth):
    """API key authentication for httpx."""

    def __init__(self, key: str, header_name: Optional[str] = None):
        self.key = key
        self.header_name = header_name or "X-API-Key"

    def auth_flow(self, request):
        request.headers[self.header_name] = self.key
        yield request


def create_httpx_auth(auth_config: Optional[Dict[str, Any]]) -> Optional[httpx.Auth]:
    """
    Convert auth config dictionary to httpx.Auth object.

    Args:
        auth_config: Authentication configuration dictionary with:
            - type: Auth type (bearer, basic, api_key)
            - token: Bearer token (for bearer auth)
            - username/password: Credentials (for basic auth)
            - key: API key (for api_key auth)
            - header_name: Optional header name for API key

    Returns:
        httpx.Auth object or None if no auth config provided

    Raises:
        ValueError: If auth config is invalid or missing required fields
    """
    if not auth_config:
        return None

    # Validate input type
    if not isinstance(auth_config, dict):
        raise ValueError(f"Auth config must be a dictionary, got {type(auth_config).__name__}")

    auth_type = auth_config.get("type", "bearer").lower()

    # Validate auth type
    valid_auth_types = {"bearer", "basic", "api_key"}
    if auth_type not in valid_auth_types:
        raise ValueError(
            f"Invalid auth type '{auth_type}'. Must be one of: {', '.join(valid_auth_types)}"
        )

    if auth_type == "bearer":
        token = auth_config.get("token")
        if not token or not isinstance(token, str) or not token.strip():
            raise ValueError("Bearer auth requires a non-empty 'token' field")
        return BearerAuth(token)

    elif auth_type == "basic":
        username = auth_config.get("username")
        password = auth_config.get("password")

        if not username or not isinstance(username, str) or not username.strip():
            raise ValueError("Basic auth requires a non-empty 'username' field")
        if not password or not isinstance(password, str):
            raise ValueError("Basic auth requires a 'password' field")

        return httpx.BasicAuth(username=username, password=password)

    elif auth_type == "api_key":
        key = auth_config.get("key")
        if not key or not isinstance(key, str) or not key.strip():
            raise ValueError("API key auth requires a non-empty 'key' field")

        header_name = auth_config.get("header_name")
        if header_name and not isinstance(header_name, str):
            raise ValueError("API key 'header_name' must be a string if provided")

        return ApiKeyAuth(key, header_name)

    # This should never be reached due to earlier validation
    raise ValueError(f"Unhandled auth type: {auth_type}")
