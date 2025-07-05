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
    """
    if not auth_config:
        return None

    auth_type = auth_config.get("type", "bearer").lower()

    if auth_type == "bearer" and "token" in auth_config:
        return BearerAuth(auth_config["token"])

    elif auth_type == "basic":
        return httpx.BasicAuth(
            username=auth_config.get("username", ""), password=auth_config.get("password", "")
        )

    elif auth_type == "api_key":
        return ApiKeyAuth(auth_config.get("key", ""), auth_config.get("header_name"))

    return None
