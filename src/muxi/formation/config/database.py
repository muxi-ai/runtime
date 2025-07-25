# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Database Configuration - Database Connection Settings
# Description:  Configuration for database connections and connection pooling
# Role:         Provides centralized database configuration
# Usage:        Imported by components that need database access
# Author:       Muxi Framework Team
#
# The Database Configuration module provides centralized settings for database
# connections, including connection strings, pooling parameters, and timeout
# settings. This configuration supports various database backends including
# PostgreSQL and SQLite.
#
# Key features include:
#
# 1. Connection Management
#    - Database URL configuration
#    - Connection pool settings
#    - Timeout and recycling parameters
#
# 2. Environment Integration
#    - Environment variable based configuration
#    - Sensible defaults for development
#
# All settings can be overridden via environment variables, allowing for
# easy configuration in different deployment environments without code changes.
#
# Example usage:
#
#   from .config import database_config
#
#   # Access database configuration
#   connection_string = database_config.connection_string
#   pool_size = database_config.pool_size
# =============================================================================

from pydantic import BaseModel, Field
from typing import Optional
from ...utils.user_dirs import get_memory_dir


class DatabaseConfig(BaseModel):
    """
    Configuration settings for database connections.

    This class defines the configuration structure for database connections,
    including connection strings, pooling parameters, and timeout settings.
    Settings can be customized per formation or environment.

    Attributes:
        connection_string: Database connection string
        pool_size: Number of connections to maintain in the pool
        max_overflow: Maximum number of overflow connections
        pool_timeout: Seconds to wait for a connection from the pool
        pool_recycle: Seconds after which a connection is recreated
    """

    connection_string: Optional[str] = Field(
        default=f"sqlite:///{get_memory_dir()}/muxi.db",
        description="Database connection string",
    )
    pool_size: int = Field(
        default=5,
        description="Number of connections to maintain in the pool",
    )
    max_overflow: int = Field(
        default=10,
        description="Maximum number of overflow connections",
    )
    pool_timeout: int = Field(
        default=30,
        description="Seconds to wait for a connection from the pool",
    )
    pool_recycle: int = Field(
        default=1800,
        description="Seconds after which a connection is recreated",
    )
