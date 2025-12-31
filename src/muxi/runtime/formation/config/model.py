# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Model Configuration - AI Model Provider Settings
# Description:  Configuration for language models, embeddings, and provider API keys
# Role:         Provides centralized configuration for AI model interactions
# Usage:        Imported by components that need AI model configuration
# Author:       Muxi Framework Team
#
# The Model Configuration module provides centralized settings for AI model
# providers, embedding models, and related parameters in the Muxi Framework.
# This configuration supports multiple providers (OpenAI, Anthropic, etc.)
# and enables consistent model behavior across the system.
# =============================================================================

from pydantic import BaseModel, Field
from typing import Optional


class ModelConfig(BaseModel):
    """
    Configuration settings for AI models and providers.

    This class defines the configuration structure for AI model settings,
    including provider selection, model parameters, and API credentials.
    Settings can be customized per formation or environment.

    Attributes:
        provider: The AI provider to use (e.g., "openai", "anthropic")
        model: The specific model name (e.g., "gpt-4o", "claude-3-sonnet")
        openai_api_key: OpenAI API key for authentication
        anthropic_api_key: Anthropic API key for authentication
        temperature: Model temperature for response randomness (0.0-1.0)
        max_tokens: Maximum tokens in model responses
        embedding_dimension: Vector dimension for embeddings
        top_p: Top-p sampling parameter
        frequency_penalty: Frequency penalty parameter
        presence_penalty: Presence penalty parameter
    """

    # Provider and model selection
    provider: str = Field(
        default="openai",
        description="The AI provider to use for model requests",
    )
    model: str = Field(
        default="gpt-4o",
        description="The specific model name to use",
    )

    # API keys for providers
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key for authentication",
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for authentication",
    )

    # Model parameters
    temperature: float = Field(
        default=0.7,
        description="Temperature for controlling response randomness",
    )
    max_tokens: int = Field(
        default=4096,
        description="Maximum number of tokens in model responses",
    )
    embedding_dimension: int = Field(
        default=1536,
        description="Vector dimension for embeddings",
    )
    top_p: float = Field(
        default=1.0,
        description="Top-p sampling parameter",
    )
    frequency_penalty: float = Field(
        default=0.0,
        description="Frequency penalty parameter",
    )
    presence_penalty: float = Field(
        default=0.0,
        description="Presence penalty parameter",
    )
