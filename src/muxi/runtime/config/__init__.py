# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Configuration System - Framework Configuration Management
# Description:  Centralized configuration system for the Muxi framework
# Role:         Provides configuration classes for framework components
# Usage:        Imported by components needing configuration classes
# Author:       Muxi Framework Team
#
# The configuration system provides centralized configuration classes
# for the Muxi framework. These classes define:
#
# 1. Configuration Structure
#    - Type-safe configuration classes using Pydantic
#    - Clear defaults for all settings
#    - Validation and conversion of values
#
# 2. Component-Specific Settings
#    - Database connection settings
#    - Memory configuration (buffer size, vector search, etc.)
#    - Model settings (providers, parameters, API keys)
#    - Routing rules for agent selection and message handling
#    - Application settings (server, security, etc.)
#
# Configuration instances are created from formation YAML data by
# components like the Overlord, rather than using global instances.
#
# Example usage:
#
#   # Create configuration from formation data
#   from .routing import RoutingConfig
#   routing_config = RoutingConfig(**formation_yaml.get('routing', {}))
#
#   # Use configuration
#   provider = routing_config.provider
#   model = routing_config.model
#
# This approach provides better testability and flexibility compared
# to global configuration instances.
# =============================================================================

from .app import AppConfig
from .database import DatabaseConfig
from .loader import ConfigLoader
from .formation_loader import FormationLoader

from .memory import MemoryConfig
from .model import ModelConfig
from .routing import RoutingConfig


__all__ = [
    "AppConfig",
    "ConfigLoader",
    "DatabaseConfig",
    "FormationLoader",
    "MemoryConfig",
    "ModelConfig",
    "RoutingConfig",
]
