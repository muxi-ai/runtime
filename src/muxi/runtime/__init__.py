# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Core Framework Package Initialization
# Description:  Main entry point for the Muxi Runtime Framework
# Role:         Defines package-level imports and version information
# Usage:        Imported when accessing runtime framework components
# Author:       Muxi Framework Team
#
# This file initializes the Muxi Runtime framework package and defines what's
# available when importing from muxi.runtime. It exports:
#
# Core Components
#  - Overlord for direct agent and memory management
#  - LLM for language model interactions
#
# The runtime package provides the essential components for building
# AI agent applications with direct programmatic access.
# =============================================================================

# Import core classes for direct access
from .formation.overlord import Overlord
from .services.llm import LLM
from .utils.version import get_version


# Initialize package version from .version file
__version__ = get_version()

# Package metadata
__author__ = "Ran Aroussi"
__license__ = "Elastic License 2.0"
__url__ = "https://github.com/muxi-ai"


# Explicitly define what's available when using "from muxi.runtime import *"
__all__ = [
    "Overlord",
    "LLM",
    "observability",
]

# Public API methods for Overlord (exposed when importing Overlord directly):
# - overlord.run_agent() - for development/testing specific agents
# - overlord.get_agent() - for getting agent references
# - overlord.list_agents() - for viewing available agents
# - overlord.load_formation_from_path() - for loading formation configs
# Agent creation should only happen via formation YAML files
