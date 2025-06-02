# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        LLM Package - Unified Language Model Interface
# Description:  Package for language model interactions using OneLLM
# Role:         Provides unified access to language models across providers
# Usage:        Import LLM classes and services for model interactions
# Author:       Muxi Framework Team
#
# This package provides a unified interface for language model interactions
# in the Muxi framework. It includes:
#
# 1. OneLLMService - Singleton service for centralized model management
# 2. Custom exceptions for better error handling
# 3. Utility functions for common operations
#
# Usage:
#   from .llm import OneLLMService
#
#   service = await OneLLMService.get_instance()
#   response = await service.chat("openai/gpt-4o", messages)
# =============================================================================

from .service import OneLLMService
from .errors import (
    OneLLMError,
    OneLLMConnectionError,
    OneLLMAuthenticationError,
    OneLLMRateLimitError,
    OneLLMTimeoutError,
    OneLLMModelNotFoundError,
    OneLLMValidationError,
    OneLLMServiceError,
)

__all__ = [
    "OneLLMService",
    "OneLLMError",
    "OneLLMConnectionError",
    "OneLLMAuthenticationError",
    "OneLLMRateLimitError",
    "OneLLMTimeoutError",
    "OneLLMModelNotFoundError",
    "OneLLMValidationError",
    "OneLLMServiceError",
]
