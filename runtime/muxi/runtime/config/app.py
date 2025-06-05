# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Application Configuration - Core App Settings
# Description:  Configuration for application-level settings and server options
# Role:         Provides centralized application configuration
# Usage:        Imported by components that need app-level settings
# Author:       Muxi Framework Team
#
# The Application Configuration module provides centralized settings for
# core application behavior, including server settings, security options,
# and environment configuration.
# =============================================================================

import secrets
from pydantic import BaseModel, Field
from typing import Optional


class AppConfig(BaseModel):
    """
    Configuration settings for the application.

    This class defines the configuration structure for application-level
    settings including server configuration, security settings, and
    environment options. Settings can be customized per formation or environment.

    Attributes:
        default_agent_id: Default agent to use when none specified
        environment: Application environment (development, production, etc.)
        debug: Enable debug mode
        host: Server host address
        port: Server port number
        base_url: Base URL for the application
        cors_origins: CORS allowed origins
        secret_key: Secret key for cryptographic operations
        jwt_algorithm: JWT signing algorithm
        jwt_expiration: JWT token expiration time in seconds
        admin_password: Admin password for protected operations
    """

    # Core application settings
    default_agent_id: str = Field(
        default="default_agent",
        description="Default agent ID to use when none is specified",
    )
    environment: str = Field(
        default="development",
        description="Application environment (development, production, etc.)",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    # Server settings
    host: str = Field(
        default="0.0.0.0",
        description="Server host address",
    )
    port: int = Field(
        default=8000,
        description="Server port number",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Base URL for the application",
    )

    # Security settings
    cors_origins: str = Field(
        default="*",
        description="CORS allowed origins",
    )
    secret_key: str = Field(
        default_factory=lambda: secrets.token_hex(24),
        description="Secret key for cryptographic operations",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm",
    )
    jwt_expiration: int = Field(
        default=86400,
        description="JWT token expiration time in seconds",
    )
    admin_password: Optional[str] = Field(
        default=None,
        description="Admin password for protected operations",
    )
