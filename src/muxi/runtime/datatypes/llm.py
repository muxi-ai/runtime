# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        OneLLM Service Exceptions
# Description:  Custom exception classes for OneLLM service operations
# Role:         Provides specific error types for better error handling
# Usage:        Raised by OneLLMService for various error conditions
# Author:       Muxi Framework Team
# =============================================================================

from typing import Optional


class OneLLMError(Exception):
    """Base exception for OneLLM service errors."""

    def __init__(self, message: str, provider: Optional[str] = None, model: Optional[str] = None):
        self.message = message
        self.provider = provider
        self.model = model
        super().__init__(message)


class OneLLMConnectionError(OneLLMError):
    """Raised when connection to LLM provider fails."""

    pass


class OneLLMAuthenticationError(OneLLMError):
    """Raised when authentication with LLM provider fails."""

    pass


class OneLLMRateLimitError(OneLLMError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class OneLLMTimeoutError(OneLLMError):
    """Raised when request times out."""

    pass


class OneLLMModelNotFoundError(OneLLMError):
    """Raised when specified model is not available."""

    pass


class OneLLMValidationError(OneLLMError):
    """Raised when input validation fails."""

    pass


class OneLLMServiceError(OneLLMError):
    """Raised when service-level operations fail."""

    pass
