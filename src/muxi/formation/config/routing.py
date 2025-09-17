# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Routing Configuration - LLM-Based Message Routing Settings
# Description:  Configuration for intelligent message routing between agents
# Role:         Provides settings for the message routing system
# Usage:        Imported by components using the routing system
# Author:       Muxi Framework Team
#
# The Routing Configuration module provides centralized settings for the
# LLM-based message routing functionality in the Muxi Framework. This system
# enables intelligent message routing between different specialized agents
# based on message content and agent capabilities.
#
# Key features include:
#
# 1. Routing LLM Configuration
#    - Model selection for routing decisions
#    - Temperature and token settings
#    - System prompt customization
#
# 2. Performance Optimization
#    - Caching settings for routing decisions
#    - TTL configuration for cached routes
#
# 3. Formation YAML Integration
#    - Values are loaded from formation YAML configuration
#    - Sensible defaults when not specified in YAML
#
# Example usage:
#
#   # Created from formation YAML data in Overlord
#   routing_config = RoutingConfig(
#       model=yaml_data.get('model', 'openai/gpt-4o-mini'),
#       temperature=yaml_data.get('settings', {}).get('temperature', 0.2)
#   )
# =============================================================================

from pydantic import BaseModel, Field


class RoutingConfig(BaseModel):
    """
    Configuration for the LLM-based message routing system.

    This class defines parameters for the language model used to make
    intelligent routing decisions between agents. It includes model selection,
    generation parameters, caching settings, and prompt customization.

    Values are provided by the Overlord from formation YAML configuration,
    with sensible defaults when not specified.
    """

    model: str = Field(
        default="openai/gpt-4o-mini",
        description="The model to use for routing decisions in OneLLM format (provider/model)",
    )

    temperature: float = Field(
        default=0.0,
        description="Temperature setting for routing (low for consistent decisions)",
    )

    max_tokens: int = Field(
        default=256,
        description="Maximum response length for routing decisions",
    )

    use_caching: bool = Field(
        default=True,
        description="Whether to cache routing decisions to improve performance",
    )

    cache_ttl: int = Field(
        default=3600,
        description="Time to live for cached routing decisions in seconds",
    )

    system_message: str = Field(
        default=(
            "You are a routing assistant that determines which agent should handle a user message. "
            "Based on the user's message and the available agents' descriptions, select the most "
            "appropriate agent to handle the request. Respond with just the agent ID."
        ),
        description="System message that guides the routing model's behavior",
    )
