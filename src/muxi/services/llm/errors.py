"""
OneLLM Service Error Classes

Custom exceptions for the OneLLM service to provide granular error handling
and better debugging capabilities.
"""


class OneLLMBaseError(Exception):
    """Base exception for all OneLLM service errors."""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class OneLLMConnectionError(OneLLMBaseError):
    """Raised when there's a connection issue with the LLM provider."""

    pass


class OneLLMAuthenticationError(OneLLMBaseError):
    """Raised when authentication with the LLM provider fails."""

    pass


class OneLLMRateLimitError(OneLLMBaseError):
    """Raised when the LLM provider rate limit is exceeded."""

    pass


class OneLLMTimeoutError(OneLLMBaseError):
    """Raised when a request to the LLM provider times out."""

    pass


class OneLLMServiceError(OneLLMBaseError):
    """General service error for the OneLLM service."""

    pass
