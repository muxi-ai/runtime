# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Logging Configuration - Application Logging Settings
# Description:  Configuration for log levels, file rotation, and formatting
# Role:         Provides centralized logging configuration
# Usage:        Imported by components that need logging configuration
# Author:       Muxi Framework Team
#
# The Logging Configuration module provides centralized settings for logging
# behavior including log levels, file output, rotation, and formatting options.
# =============================================================================

from pydantic import BaseModel, Field
from typing import Optional


class LoggingConfig(BaseModel):
    """
    Configuration settings for application logging.

    This class defines the configuration structure for logging behavior,
    including log levels, file output, rotation, and formatting options.
    Settings can be customized per formation or environment.

    Attributes:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        file: Log file path (None for stdout only)
        format: Log message format string
        rotation: Log file rotation setting
        retention: Log file retention period
        compression: Log file compression format
    """

    # Core logging settings
    level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    file: Optional[str] = Field(
        default=None,
        description="Path to log file (None for stdout only)",
    )

    # Log formatting
    format: str = Field(
        default="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        description="Log message format string",
    )

    # File rotation and management
    rotation: str = Field(
        default="10 MB",
        description="Log file rotation setting (size or time-based)",
    )
    retention: str = Field(
        default="1 week",
        description="Log file retention period",
    )
    compression: str = Field(
        default="zip",
        description="Log file compression format",
    )


def configure_logging(config: Optional[LoggingConfig] = None):
    """
    Configure the logging system based on the provided configuration settings.

    This function sets up the logging system using the loguru library according
    to the settings in the LoggingConfig instance. It:

    1. Removes the default handler to start with a clean slate
    2. Adds a console handler with the configured format and level
    3. Optionally adds a file handler if a log file is specified
    4. Creates directories for log files if they don't exist

    Args:
        config: LoggingConfig instance to use. If None, uses default settings.

    Usage:
        from .logging import configure_logging, LoggingConfig

        # Use default settings
        configure_logging()

        # Use custom settings
        config = LoggingConfig(level="DEBUG", file="logs/app.log")
        configure_logging(config)
    """
    import sys
    from pathlib import Path

    from loguru import logger

    # Use provided config or create default
    if config is None:
        config = LoggingConfig()

    # Remove default handler
    logger.remove()

    # Add console handler
    logger.add(sink=sys.stdout, level=config.level, format=config.format)

    # Add file handler if configured
    if config.file:
        # Create directory if it doesn't exist
        log_path = Path(config.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            sink=config.file,
            level=config.level,
            rotation=config.rotation,
            retention=config.retention,
            compression=config.compression,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} - {message}",
        )
