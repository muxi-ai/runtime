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
#  - Formation for operational lifecycle management
#  - LLM for language model interactions
#
# The runtime package provides the essential components for building
# AI agent applications. Formation manages the complete lifecycle including
# creating and configuring Overlord instances internally.
# =============================================================================

# Import core classes for direct access
from .formation import Formation
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
    "Formation",
    "LLM",
    "observability",
]

# Usage:
# from muxi.runtime import Formation
# formation = Formation()
# formation.load("formation.yaml")
# muxi = formation.start_overlord()  # Returns Overlord instance
# response = muxi.chat("Hello!")
# formation.stop_overlord()
