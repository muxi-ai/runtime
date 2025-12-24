# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Unified Language Model Interface with Multi-modal Support
# Description:  Unified implementation for all language model providers using OneLLM
# Role:         Provides a standardized interface to different LLM providers
# Usage:        Used for all language model interactions in the framework
# Author:       Muxi Framework Team
#
# The llm.py module provides a unified interface for language model interactions
# in the Muxi framework using the OneLLM package. It defines:
#
# 1. LLM Class
#    - Direct integration with OneLLM package
#    - Unified interface for all supported providers
#    - Provider-agnostic with "provider/model-name" format
#    - Multi-modal support for files (images, audio, documents)
#
# 2. Multi-modal Capabilities
#    - Pass-through file handling (user prompts drive processing)
#    - Support for all OneLLM-compatible file formats
#    - Dynamic format support (no hardcoded restrictions)
#    - Security validation with size limits
#
# 3. Enhanced Error Handling & Resilience
#    - Exponential backoff retry strategies
#    - Circuit breaker patterns for provider failures
#    - Comprehensive error classification
#    - Timeout management and graceful degradation
#    - Monitoring and logging integration
#
# 4. Direct OneLLM Integration
#    - Uses onellm.ChatCompletion and onellm.Embedding directly
#    - Enhanced error handling and caching
#    - Modern async/await patterns throughout
#
# Typical usage pattern:
#
#   # Creating an LLM instance with resilience settings
#   model = LLM(
#       model="openai/gpt-4o",
#       api_key="sk-...",
#       timeout=30,
#       max_retries=3,
#       enable_circuit_breaker=True
#   )
#
#   # Using the model with automatic retries and error handling
#   response = await model.chat([
#       {"role": "system", "content": "You are a helpful assistant"},
#       {"role": "user", "content": "Hello, world!"}
#   ])
#
#   # Multi-modal usage with files (pass-through processing)
#   response = await model.chat(
#       "Analyze this image and describe what you see",
#       files=[image_file]  # User prompt drives processing
#   )
#
# The LLM class now includes production-ready resilience patterns and multi-modal support.
# =============================================================================

import asyncio
import base64
import hashlib
import json
import mimetypes
import random
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .. import observability

# File processing imports
# Required runtime dependencies
import aiofiles
import magic

# Import OneLLM components
from onellm import ChatCompletion, Embedding
from onellm.audio import AudioTranscription
from onellm.config import set_api_key
from onellm.errors import AuthenticationError, RateLimitError, InvalidRequestError
from onellm import init_cache as onellm_init_cache

# Import multimodal components
from ..multimodal import (
    MultiModalFusionEngine,
    MultiModalContent,
    ModalityType,
    ProcessingMode,
)

# Filter noisy OneLLM cache warnings that don't affect functionality
import logging


class OneLLMCacheWarningFilter(logging.Filter):
    """Filter out harmless OneLLM semantic cache warnings."""

    def filter(self, record):
        # Suppress the numpy array warning from semantic cache fallback
        return "Failed to add to semantic cache" not in record.getMessage()


# Apply filter to OneLLM cache logger
_onellm_cache_logger = logging.getLogger("onellm.cache")
_onellm_cache_logger.addFilter(OneLLMCacheWarningFilter())

# Module-level cache initialization state
_cache_initialized = False


def initialize_onellm_cache(cache_config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Initialize OneLLM cache with provided configuration.

    This function should be called once during application startup.
    Subsequent calls are ignored (idempotent).

    Args:
        cache_config: Dictionary with cache configuration:
            - enabled: bool (default: True)
            - max_entries: int (default: 10000)
            - p: float (default: 0.98)
            - hash_only: bool (default: False)
            - stream_chunk_strategy: str (default: "sentences")
            - stream_chunk_length: int (default: 1)
            - ttl: int (default: 86400)

    Requires: onellm >= 0.20251013.0

    Returns:
        bool: True if cache was initialized, False if already initialized or disabled
    """
    global _cache_initialized

    # Return early if already initialized
    if _cache_initialized:
        return False

    # Use defaults if no config provided
    if cache_config is None:
        cache_config = {}

    # Check if caching is enabled (default: True)
    if not cache_config.get("enabled", True):
        # Convert to InitEventFormatter
        print(observability.InitEventFormatter.format_info("LLM cache: disabled"))
        _cache_initialized = True  # Mark as initialized to prevent retry
        return False

    # Extract cache parameters with defaults optimized for MUXI
    cache_params = {
        "max_entries": cache_config.get("max_entries", 10000),
        "p": cache_config.get("p", 0.98),
        "hash_only": cache_config.get("hash_only", False),
        "stream_chunk_strategy": cache_config.get("stream_chunk_strategy", "sentences"),
        "stream_chunk_length": cache_config.get("stream_chunk_length", 1),
        "ttl": cache_config.get("ttl", 86400),  # 24 hours
    }

    # Initialize OneLLM cache
    onellm_init_cache(**cache_params)

    # Convert to InitEventFormatter (user: say "LLM cache" not "OneLLM cache")
    print(observability.InitEventFormatter.format_info(
        f"LLM cache: {cache_params['max_entries']} max entries, "
        f"{cache_params['p']} similarity, {cache_params['ttl']}s TTL"
    ))

    _cache_initialized = True
    return True


# File processing configuration
FILE_SIZE_LIMITS = {
    "default": 500 * 1024 * 1024,  # 500MB general limit for safety
    # Let OneLLM enforce its own format-specific limits
}

# MIME type to OneLLM content type mapping
MIME_TO_ONELLM_TYPE = {
    # Images
    "image/jpeg": "image_url",
    "image/png": "image_url",
    "image/gif": "image_url",
    "image/webp": "image_url",
    # Documents - OneLLM handles these, we just pass them through
    "application/pdf": "document",
    "text/plain": "text",
    "text/markdown": "text",
    # Audio/Video - pass through, user prompt determines processing
    "audio/mpeg": "audio",
    "audio/wav": "audio",
    "video/mp4": "video",
    # Archives and other formats
    "application/zip": "document",
    "application/json": "text",
    # Default fallback
    "default": "document",
}


# Enhanced Error Classification
class LLMErrorType(Enum):
    """Classification of LLM error types for appropriate handling."""

    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    INVALID_REQUEST = "invalid_request"
    MODEL_OVERLOAD = "model_overload"
    CONTEXT_LENGTH = "context_length"
    FILE_TOO_LARGE = "file_too_large"
    FILE_PROCESSING = "file_processing"
    UNKNOWN = "unknown"


class LLMError(Exception):
    """Base exception for LLM operations with enhanced metadata."""

    def __init__(
        self,
        message: str,
        error_type: LLMErrorType = LLMErrorType.UNKNOWN,
        provider: str = None,
        model: str = None,
        retryable: bool = False,
        original_error: Exception = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.original_error = original_error
        self.timestamp = time.time()


# File Processing Utilities
class FileProcessor:
    """Handles file processing for multi-modal LLM interactions with pass-through approach."""

    @staticmethod
    async def validate_file_security(file_path: Union[str, Path]) -> bool:
        """
        Security validation only - no format restrictions.
        Let OneLLM handle format compatibility.
        """
        try:
            file_path = Path(file_path)

            # Check if file exists
            if not file_path.exists():
                return False

            # Check file size limits
            file_size = file_path.stat().st_size
            if file_size > FILE_SIZE_LIMITS["default"]:
                observability.observe(
                    event_type=observability.ErrorEvents.RESOURCE_EXHAUSTED,
                    level=observability.EventLevel.WARNING,
                    data={"file_path": str(file_path), "file_size": file_size, "limit": FILE_SIZE_LIMITS["default"]},
                    description=f"File size {file_size} exceeds limit {FILE_SIZE_LIMITS['default']}",
                )
                return False

            # Basic security check - avoid obviously dangerous files
            if file_path.suffix.lower() in [".exe", ".bat", ".sh", ".scr"]:
                observability.observe(
                    event_type=observability.ErrorEvents.VALIDATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "file_path": str(file_path),
                        "extension": file_path.suffix.lower(),
                        "blocked_extensions": [".exe", ".bat", ".sh", ".scr"]
                    },
                    description="File blocked due to dangerous extension (security policy)",
                )
                return False

            return True
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"file_path": str(file_path), "error": str(e)},
                description=f"File security validation failed: {str(e)}",
            )
            return False

    @staticmethod
    def _detect_mime_type(file_path: Union[str, Path]) -> str:
        """Detect MIME type using multiple methods."""
        file_path = Path(file_path)

        # Try python-magic first (most accurate)
        try:
            mime_type = magic.from_file(str(file_path), mime=True)
            if mime_type:
                return mime_type
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.DEBUG,
                data={"file_path": str(file_path), "error": str(e)},
                description="MIME type detection failed, using fallback",
            )

        # Fallback to mimetypes module
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            return mime_type

        # Default fallback
        return "application/octet-stream"

    @staticmethod
    def _map_mime_to_onellm_type(mime_type: str) -> str:
        """Map MIME type to OneLLM content type."""
        # Check exact matches first
        if mime_type in MIME_TO_ONELLM_TYPE:
            return MIME_TO_ONELLM_TYPE[mime_type]

        # Check broad categories
        if mime_type.startswith("image/"):
            return "image_url"
        elif mime_type.startswith("text/"):
            return "text"
        elif mime_type.startswith("audio/"):
            return "audio"
        elif mime_type.startswith("video/"):
            return "video"
        else:
            return MIME_TO_ONELLM_TYPE["default"]

    @staticmethod
    async def convert_file_for_onellm(file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Convert file to OneLLM-compatible format with pass-through approach.
        No processing decisions - just format conversion.
        """
        try:
            file_path = Path(file_path)

            # Detect MIME type
            mime_type = FileProcessor._detect_mime_type(file_path)
            onellm_type = FileProcessor._map_mime_to_onellm_type(mime_type)

            # Read file and convert to base64
            async with aiofiles.open(file_path, "rb") as f:
                file_content = await f.read()

            base64_content = base64.b64encode(file_content).decode("utf-8")

            # Return in OneLLM-compatible format
            if onellm_type == "image_url":
                return {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_content}"},
                }
            elif onellm_type == "text":
                # For text files, include the actual text content
                try:
                    text_content = file_content.decode("utf-8")
                    return {"type": "text", "text": f"[File: {file_path.name}]\n{text_content}"}
                except UnicodeDecodeError:
                    # Fallback to base64 if not valid UTF-8
                    return {
                        "type": "document",
                        "data": base64_content,
                        "filename": file_path.name,
                        "mime_type": mime_type,
                    }
            else:
                # Generic document/audio/video handling
                return {
                    "type": onellm_type,
                    "data": base64_content,
                    "filename": file_path.name,
                    "mime_type": mime_type,
                }

        except Exception as e:
            raise LLMError(
                f"File conversion failed for {file_path}: {str(e)}",
                error_type=LLMErrorType.FILE_PROCESSING,
                retryable=False,
                original_error=e,
            )


class CircuitBreaker:
    """Circuit breaker pattern implementation for provider reliability."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: tuple = (Exception,),
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open

    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if self.state == "open":
            if time.time() - self.last_failure_time < self.timeout:
                raise LLMError(
                    "Circuit breaker is OPEN. Too many failures.",
                    error_type=LLMErrorType.MODEL_OVERLOAD,
                    retryable=False,
                )
            else:
                self.state = "half-open"

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        """Reset circuit breaker on successful call."""
        self.failure_count = 0
        self.state = "closed"

    def _on_failure(self):
        """Handle failure and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_LOOKUP,
                level=observability.EventLevel.WARNING,
                data={"failure_count": self.failure_count, "threshold": self.failure_threshold},
                description="Circuit breaker opened due to repeated failures",
            )


# Global cache for responses (simple in-memory cache)
_response_cache = {}
_cache_ttl = 300  # 5 minutes default TTL

# Global circuit breakers per provider
_circuit_breakers = {}

# Global retry statistics
_retry_stats = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "retry_attempts": 0,
    "circuit_breaker_trips": 0,
}


def _get_cache_key(operation: str, **kwargs) -> str:
    """Generate a cache key from operation and parameters."""
    # Create a hash of the operation and parameters
    key_data = f"{operation}:{str(sorted(kwargs.items()))}"
    return hashlib.md5(key_data.encode()).hexdigest()


def _get_cached_response(cache_key: str) -> Optional[Any]:
    """Get a cached response if it exists and is not expired."""
    if cache_key in _response_cache:
        response, timestamp = _response_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            return response
        else:
            # Remove expired entry
            del _response_cache[cache_key]
    return None


def _cache_response(cache_key: str, response: Any) -> None:
    """Cache a response with current timestamp."""
    _response_cache[cache_key] = (response, time.time())


def _classify_error(error: Exception, provider: str = None) -> LLMError:
    """Classify an exception into appropriate LLM error type."""
    error_message = str(error)

    if isinstance(error, AuthenticationError):
        return LLMError(
            message=f"Authentication failed: {error_message}",
            error_type=LLMErrorType.AUTHENTICATION,
            provider=provider,
            retryable=False,
            original_error=error,
        )
    elif isinstance(error, RateLimitError):
        return LLMError(
            message=f"Rate limit exceeded: {error_message}",
            error_type=LLMErrorType.RATE_LIMIT,
            provider=provider,
            retryable=True,
            original_error=error,
        )
    elif isinstance(error, InvalidRequestError):
        return LLMError(
            message=f"Invalid request: {error_message}",
            error_type=LLMErrorType.INVALID_REQUEST,
            provider=provider,
            retryable=False,
            original_error=error,
        )
    elif isinstance(error, asyncio.TimeoutError):
        # Provide more context for timeout errors
        timeout_msg = (
            error_message if error_message else "No response received within timeout period"
        )
        return LLMError(
            message=f"Request timed out after waiting for response: {timeout_msg}",
            error_type=LLMErrorType.TIMEOUT,
            provider=provider,
            retryable=True,
            original_error=error,
        )
    elif "context length" in error_message.lower() or "token" in error_message.lower():
        return LLMError(
            message=f"Context length exceeded: {error_message}",
            error_type=LLMErrorType.CONTEXT_LENGTH,
            provider=provider,
            retryable=False,
            original_error=error,
        )
    elif "overloaded" in error_message.lower() or "busy" in error_message.lower():
        return LLMError(
            message=f"Model overloaded: {error_message}",
            error_type=LLMErrorType.MODEL_OVERLOAD,
            provider=provider,
            retryable=True,
            original_error=error,
        )
    else:
        return LLMError(
            message=f"Unknown error: {error_message}",
            error_type=LLMErrorType.UNKNOWN,
            provider=provider,
            retryable=True,
            original_error=error,
        )


async def _exponential_backoff_retry(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_errors: tuple = (
        LLMErrorType.RATE_LIMIT,
        LLMErrorType.TIMEOUT,
        LLMErrorType.MODEL_OVERLOAD,
    ),
    llm_instance=None,
    *args,
    **kwargs,
):
    """Execute function with exponential backoff retry strategy."""
    global _retry_stats

    _retry_stats["total_requests"] += 1

    # Try to extract context from function name and kwargs
    operation = getattr(func, "__name__", "llm_request")
    context_parts = []

    # Check if we have an LLM instance
    if llm_instance:
        context_parts.append(f"model={llm_instance.model_name}")
    elif args and hasattr(args[0], "model_name"):
        context_parts.append(f"model={args[0].model_name}")

    # Check for metadata with caller context
    if "metadata" in kwargs and kwargs["metadata"]:
        metadata = kwargs["metadata"]
        if "agent_id" in metadata:
            context_parts.append(f"agent={metadata['agent_id']}")
        if "agent_name" in metadata:
            context_parts.append(f"agent_name={metadata['agent_name']}")
        if "task_id" in metadata:
            context_parts.append(f"task={metadata['task_id']}")
        if "workflow_id" in metadata:
            context_parts.append(f"workflow={metadata['workflow_id']}")

    # Check for common kwargs that provide context
    if "messages" in kwargs and kwargs["messages"]:
        msg_count = len(kwargs["messages"])
        # Try to get the first user message for context
        first_user_msg = next(
            (m["content"] for m in kwargs["messages"] if m.get("role") == "user"), None
        )
        if first_user_msg:
            msg_preview = first_user_msg[:30].replace("\n", " ")
            context_parts.append(f"{msg_count} msgs, first='{msg_preview}...'")
        else:
            context_parts.append(f"{msg_count} messages")

    if "prompt" in kwargs:
        prompt_preview = str(kwargs["prompt"])[:50].replace("\n", " ")
        context_parts.append(f"prompt='{prompt_preview}...'")

    if "temperature" in kwargs:
        context_parts.append(f"temp={kwargs['temperature']}")

    if "max_tokens" in kwargs:
        context_parts.append(f"max_tokens={kwargs['max_tokens']}")

    context_str = f" ({', '.join(context_parts)})" if context_parts else ""

    for attempt in range(max_retries + 1):
        try:
            # Add retry attempt to kwargs for adaptive timeout
            kwargs_with_attempt = kwargs.copy()
            kwargs_with_attempt["retry_attempt"] = attempt

            result = await func(*args, **kwargs_with_attempt)
            _retry_stats["successful_requests"] += 1
            return result
        except LLMError as e:
            if attempt == max_retries or not e.retryable or e.error_type not in retryable_errors:
                _retry_stats["failed_requests"] += 1
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.ERROR,
                    data={
                        "error_type": e.error_type.value,
                        "provider": e.provider,
                        "retryable": e.retryable,
                        "attempt": attempt + 1,
                        "operation": operation,
                        "context": context_str,
                        "error_message": str(e),
                    },
                    description=(
                        f"{operation}{context_str} failed after {attempt + 1} attempts with "
                        f"{e.error_type.value}: {str(e)}"
                    ),
                )
                raise e

            _retry_stats["retry_attempts"] += 1

            # Calculate delay with exponential backoff
            delay = min(base_delay * (2**attempt), max_delay)
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)  # Add 50% jitter

            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "error_type": e.error_type.value,
                    "provider": e.provider,
                    "retry_delay": delay,
                    "attempt": attempt + 1,
                    "operation": operation,
                    "context": context_str,
                    "error_message": str(e),
                },
                description=(
                    f"{operation}{context_str} failed with {e.error_type.value}: {str(e)}. "
                    f"Retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries + 1})"
                ),
            )

            await asyncio.sleep(delay)
        except Exception as e:
            # Convert unknown exceptions to LLMError
            classified_error = _classify_error(e)
            # Re-raise as LLMError to trigger retry logic
            raise classified_error


def set_llm_api_key(api_key: str, provider: str) -> None:
    """
    Set the API key for a specific provider.

    Args:
        api_key: The API key to set
        provider: The provider to set the key for (e.g., "openai", "anthropic")
    """
    set_api_key(api_key, provider)
    observability.observe(
        event_type=observability.SystemEvents.CREDENTIAL_CONFIGURED,
        level=observability.EventLevel.DEBUG,
        data={"provider": provider},
        description=f"API key configured for provider {provider}",
    )


class LLM:
    """
    Unified model implementation using OneLLM with enhanced error handling.

    This class provides a standardized interface for all language model providers
    using the OneLLM package directly, with production-ready resilience patterns
    including exponential backoff, circuit breakers, and comprehensive error handling.
    """

    def __init__(
        self,
        model: str = "openai/gpt-4o",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        fallback_model: Optional[str] = None,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
        enable_circuit_breaker: bool = True,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: float = 60.0,
        enable_adaptive_timeout: bool = True,
        max_adaptive_timeout: float = 120.0,
        **kwargs,
    ):
        """
        Initialize a model using OneLLM with enhanced resilience patterns.

        Args:
            model: The model to use in "provider/model-name" format (e.g., "openai/gpt-4o").
            api_key: API key for the provider. If provided, it will be set in OneLLM.
            temperature: The temperature parameter for generation.
            max_tokens: Maximum tokens to generate in responses.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
            fallback_model: Fallback model to use if primary model fails completely.
            base_retry_delay: Base delay for exponential backoff.
            max_retry_delay: Maximum delay for exponential backoff.
            enable_circuit_breaker: Enable circuit breaker pattern.
            circuit_breaker_threshold: Number of failures before opening circuit.
            circuit_breaker_timeout: Time to wait before retrying after circuit opens.
            enable_adaptive_timeout: Enable adaptive timeout based on context size.
            max_adaptive_timeout: Maximum timeout when using adaptive mode.
            **kwargs: Additional parameters passed to the model.
        """
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.fallback_model = fallback_model
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self.enable_circuit_breaker = enable_circuit_breaker
        self.enable_adaptive_timeout = enable_adaptive_timeout
        self.max_adaptive_timeout = max_adaptive_timeout
        self.additional_params = kwargs

        # Parse provider and model from the model string
        if "/" in model:
            self._provider, self._model = model.split("/", 1)
        else:
            self._provider = "openai"  # Default provider if not specified
            self._model = model
            self.model_name = f"openai/{model}"

        # Initialize circuit breaker for this provider
        if enable_circuit_breaker:
            circuit_breaker_key = f"{self._provider}:{self._model}"
            if circuit_breaker_key not in _circuit_breakers:
                _circuit_breakers[circuit_breaker_key] = CircuitBreaker(
                    failure_threshold=circuit_breaker_threshold,
                    timeout=circuit_breaker_timeout,
                    expected_exception=(LLMError,),
                )
            self.circuit_breaker = _circuit_breakers[circuit_breaker_key]
        else:
            self.circuit_breaker = None

        # If API key is provided, set it in OneLLM
        if api_key:
            set_llm_api_key(api_key, self._provider)

        observability.observe(
            event_type=observability.SystemEvents.LLM_INITIALIZED,
            level=observability.EventLevel.DEBUG,
            data={
                "provider": self._provider,
                "model": self._model,
                "timeout": timeout,
                "max_retries": max_retries,
                "fallback_model": fallback_model,
                "circuit_breaker_enabled": enable_circuit_breaker,
            },
            description=f"Initialized LLM with {self.model_name}",
        )

        # Initialize fusion engine for advanced multimodal processing (lazy loaded)
        self._fusion_engine = None

    @property
    def fusion_engine(self):
        """Lazy initialize fusion engine for advanced multimodal processing"""
        if self._fusion_engine is None:
            try:
                self._fusion_engine = MultiModalFusionEngine(self)
                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                    level=observability.EventLevel.DEBUG,
                    data={"fusion_engine": "MultiModalFusionEngine"},
                    description="Fusion engine initialized successfully",
                )
            except ImportError as e:
                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e)},
                    description="Could not import fusion engine, falling back to basic processing",
                )
                self._fusion_engine = None
        return self._fusion_engine

    async def _convert_files_to_content(self, files: List[Union[str, Path]]):
        """Convert file paths to MultiModalContent objects for fusion engine"""
        try:
            content_items = []

            for file_path in files:
                # Detect modality type from file
                modality = await self._detect_file_modality(file_path)

                # Create MultiModalContent object
                content = MultiModalContent(
                    modality=modality,
                    content=str(file_path),  # Will be processed by fusion engine
                    metadata={
                        "file_path": str(file_path),
                        "processing_source": "llm_files_parameter",
                    },
                )

                content_items.append(content)

            return content_items

        except ImportError:
            # Fusion engine not available, return None to trigger basic processing
            return None

    async def _detect_file_modality(self, file_path: Union[str, Path]):
        """Detect modality from file extension/type"""
        try:
            mime_type, _ = mimetypes.guess_type(str(file_path))

            if mime_type:
                if mime_type.startswith("image/"):
                    return ModalityType.IMAGE
                elif mime_type.startswith("audio/"):
                    return ModalityType.AUDIO
                elif mime_type.startswith("video/"):
                    return ModalityType.VIDEO
                elif mime_type in ["application/pdf", "text/plain", "application/msword"]:
                    return ModalityType.DOCUMENT

            # Default to document for unknown types
            return ModalityType.DOCUMENT

        except ImportError:
            # Fusion engine not available, return None
            return None

    def _extract_user_message(self, messages: List[Dict[str, str]]) -> str:
        """Extract the last user message from conversation"""
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # Extract text from multimodal content
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                    return " ".join(text_parts)
        return ""

    async def _text_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Handle text-only chat (no files)"""
        # Use existing chat logic for text-only processing
        return await self._basic_chat_with_files(messages, None, **kwargs)

    async def _process_files_for_chat(self, files: Optional[List[Union[str, Path]]]) -> List[Dict]:
        """Process files for chat, validating security and converting to OneLLM format."""
        processed_files = []
        if not files:
            return processed_files

        for file_path in files:
            try:
                # Validate file security
                if not await FileProcessor.validate_file_security(file_path):
                    raise LLMError(
                        f"File security validation failed: {file_path}",
                        error_type=LLMErrorType.FILE_PROCESSING,
                        provider=self._provider,
                        retryable=False,
                    )

                # Convert file to OneLLM format
                file_data = await FileProcessor.convert_file_for_onellm(file_path)
                processed_files.append(file_data)

                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_COMPLETED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "file_path": str(file_path),
                        "file_type": file_data.get("type", "unknown"),
                    },
                    description=(
                        f"Successfully processed file "
                        f"{file_path.name if hasattr(file_path, 'name') else file_path}"
                    ),
                )

            except LLMError:
                # Re-raise LLMErrors as-is
                raise
            except Exception as e:
                raise LLMError(
                    f"Failed to process file {file_path}: {str(e)}",
                    error_type=LLMErrorType.FILE_PROCESSING,
                    provider=self._provider,
                    retryable=False,
                    original_error=e,
                ) from e

        return processed_files

    async def _prepare_chat_request(
        self,
        messages: List[Dict[str, str]],
        files: Optional[List[Union[str, Path]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stop: Optional[Union[str, List[str]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Prepare parameters for chat request, including file processing."""
        # Process files if provided
        processed_files = await self._process_files_for_chat(files)

        # Prepare parameters
        params = {
            "model": self.model_name,  # Use full model name with provider prefix
            "messages": messages,
            "temperature": temperature or kwargs.get("temperature") or self.temperature,
        }

        # Add files to parameters if processed
        if processed_files:
            params["files"] = processed_files

        # Add optional parameters if provided
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        elif "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            params["max_tokens"] = kwargs["max_tokens"]
        elif self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens

        if top_p is not None:
            params["top_p"] = top_p
        elif "top_p" in kwargs and kwargs["top_p"] is not None:
            params["top_p"] = kwargs["top_p"]

        if frequency_penalty is not None:
            params["frequency_penalty"] = frequency_penalty
        elif "frequency_penalty" in kwargs and kwargs["frequency_penalty"] is not None:
            params["frequency_penalty"] = kwargs["frequency_penalty"]

        if presence_penalty is not None:
            params["presence_penalty"] = presence_penalty
        elif "presence_penalty" in kwargs and kwargs["presence_penalty"] is not None:
            params["presence_penalty"] = kwargs["presence_penalty"]

        if stop is not None:
            params["stop"] = stop
        elif "stop" in kwargs and kwargs["stop"] is not None:
            params["stop"] = kwargs["stop"]

        # Add any additional kwargs not already handled
        # Note: timeout_seconds and similar are excluded because they're MUXI-specific
        # settings, not per-request parameters for the underlying provider APIs
        # NOTE: caching IS passed through to OneLLM for per-call cache control
        excluded_params = {
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "files",
            "timeout",
            "timeout_seconds",  # MUXI-specific, used for HTTP timeout not API param
            "max_retries",  # MUXI-specific, not an API parameter
            "fallback_model",  # MUXI-specific, not an API parameter
        }
        additional_kwargs = {k: v for k, v in kwargs.items() if k not in excluded_params}
        params.update(additional_kwargs)

        # Filter caching from additional_params as well
        filtered_additional_params = {
            k: v for k, v in self.additional_params.items() if k not in excluded_params
        }
        params.update(filtered_additional_params)

        return params

    def _extract_content_from_response(self, response: Any) -> str:
        """Extract string content from various response formats."""
        if isinstance(response, dict) and "choices" in response:
            content = response["choices"][0]["message"]["content"] or ""
        elif hasattr(response, "choices") and response.choices:
            # Handle ChatCompletionResponse object
            message = response.choices[0].message
            if hasattr(message, "content"):
                content = message.content or ""
            elif isinstance(message, dict):
                content = message.get("content", "")
            else:
                content = str(message)
        elif isinstance(response, str):
            # If it's already a string, return it
            content = response
        else:
            # Fallback: try to extract content from string representation
            response_str = str(response)

            # First, try to parse as JSON
            try:
                response_dict = json.loads(response_str)
                if isinstance(response_dict, dict) and "content" in response_dict:
                    content = response_dict["content"]
                else:
                    raise ValueError("No content key in parsed JSON")
            except (json.JSONDecodeError, ValueError):
                # If JSON parsing fails, try regex with improved pattern
                if "content" in response_str:
                    # More robust regex that handles both single and double quotes,
                    # escaped quotes, and multiline content
                    patterns = [
                        # Try double quotes first with non-greedy match
                        r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"',
                        # Then single quotes with non-greedy match
                        r"'content'\s*:\s*'((?:[^'\\]|\\.)*)'",
                        # Fallback pattern for edge cases
                        r'["\']content["\']\s*:\s*["\']([^"\']*)["\']',
                    ]

                    match = None
                    for pattern in patterns:
                        match = re.search(pattern, response_str, re.DOTALL)
                        if match:
                            content = match.group(1)
                            # Unescape common escaped characters
                            content = content.replace('\\"', '"').replace("\\'", "'")
                            content = content.replace("\\n", "\n").replace("\\t", "\t")
                            break

                    if not match:
                        content = "Error: Could not extract content from response"
                else:
                    content = "Error: No content found in response"

        return content

    def _has_tool_calls(self, response: Any) -> bool:
        """Check if response contains tool calls."""
        if hasattr(response, "choices") and response.choices:
            message = response.choices[0].message
            if isinstance(message, dict) and "tool_calls" in message and message["tool_calls"]:
                return True
            elif hasattr(message, "tool_calls") and message.tool_calls:
                return True
        return False

    def _extract_tokens_from_response(self, response: Any) -> Dict[str, int]:
        """Extract comprehensive token usage including cache information from LLM response."""
        try:
            usage_data = {}

            # Handle object with usage attribute
            if hasattr(response, "usage"):
                usage = response.usage
                if isinstance(usage, dict):
                    usage_data = {
                        "total_tokens": usage.get("total_tokens", 0),
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "prompt_tokens_cached": usage.get("prompt_tokens_cached", 0),
                        "completion_tokens_cached": usage.get("completion_tokens_cached", 0),
                    }
                else:
                    # Handle object-style usage
                    usage_data = {
                        "total_tokens": getattr(usage, "total_tokens", 0),
                        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(usage, "completion_tokens", 0),
                        "prompt_tokens_cached": getattr(usage, "prompt_tokens_cached", 0),
                        "completion_tokens_cached": getattr(usage, "completion_tokens_cached", 0),
                    }

            # Handle dictionary format
            elif isinstance(response, dict) and "usage" in response:
                usage = response["usage"]
                usage_data = {
                    "total_tokens": usage.get("total_tokens", 0),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "prompt_tokens_cached": usage.get("prompt_tokens_cached", 0),
                    "completion_tokens_cached": usage.get("completion_tokens_cached", 0),
                }

            return usage_data

        except (AttributeError, KeyError, TypeError):
            return {}

    async def _execute_with_resilience(self, func, *args, **kwargs):
        """Execute a function with full resilience patterns including fallback model support."""

        # Extract operation type from kwargs (won't be passed to func)
        operation_type = kwargs.pop("operation_type", "chat")

        async def _wrapped_func(*args, **kwargs):
            try:
                # Calculate timeout if adaptive timeout is enabled
                timeout = self.timeout
                if self.enable_adaptive_timeout:
                    # Extract retry attempt from kwargs
                    retry_attempt = kwargs.get("retry_attempt", 0)

                    # Use a simple adaptive timeout based on operation type and retry attempt
                    # NOTE: Known limitation - We can't easily access messages/files here without
                    # major refactoring. This means timeout calculations are less accurate for
                    # large message contexts or file processing operations. This is acceptable
                    # as the operation type modifier provides reasonable defaults.
                    timeout = calculate_adaptive_timeout(
                        base_timeout=self.timeout,
                        messages=None,  # Would need refactoring to pass these properly
                        operation_type=operation_type,
                        retry_attempt=retry_attempt,
                        files=None,
                        max_timeout=self.max_adaptive_timeout,
                    )

                    # Remove internal kwargs before passing to function
                    clean_kwargs = {k: v for k, v in kwargs.items() if k not in ["retry_attempt"]}

                    # Use cleaned kwargs for the actual call
                    return await asyncio.wait_for(func(*args, **clean_kwargs), timeout=timeout)
                else:
                    # Remove internal kwargs before passing to function (same as adaptive case)
                    clean_kwargs = {k: v for k, v in kwargs.items() if k not in ["retry_attempt"]}

                    # Use fixed timeout with cleaned kwargs
                    return await asyncio.wait_for(func(*args, **clean_kwargs), timeout=timeout)
            except asyncio.TimeoutError as e:
                # Provide specific timeout error with timeout value
                raise LLMError(
                    message=f"Request timed out after {timeout}s waiting for {self._provider} response",
                    error_type=LLMErrorType.TIMEOUT,
                    provider=self._provider,
                    retryable=True,
                    original_error=e,
                )
            except Exception as e:
                # Classify and raise appropriate LLMError
                raise _classify_error(e, self._provider)

        # Apply circuit breaker if enabled
        if self.circuit_breaker:

            async def _circuit_breaker_func(*args, **kwargs):
                return await self.circuit_breaker.call(_wrapped_func, *args, **kwargs)

            func_to_retry = _circuit_breaker_func
        else:
            func_to_retry = _wrapped_func

        # First try the primary model with exponential backoff retry
        try:
            # Pass the LLM instance for better context
            return await _exponential_backoff_retry(
                func_to_retry,
                max_retries=self.max_retries,
                base_delay=self.base_retry_delay,
                max_delay=self.max_retry_delay,
                llm_instance=self,
                *args,
                **kwargs,
            )
        except LLMError as primary_error:
            # If primary model fails completely and fallback is available, try fallback
            if self.fallback_model and self.fallback_model != self.model_name:
                observability.observe(
                    event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "primary_model": self.model_name,
                        "fallback_model": self.fallback_model,
                        "primary_error": str(primary_error),
                    },
                    description=f"Primary model {self.model_name} failed, attempting fallback to {self.fallback_model}",
                )

                # Temporarily switch to fallback model
                original_model = self.model_name
                original_provider = self._provider
                original_model_name = self._model

                try:
                    # Parse fallback model
                    if "/" in self.fallback_model:
                        self._provider, self._model = self.fallback_model.split("/", 1)
                    else:
                        self._provider = "openai"
                        self._model = self.fallback_model
                    self.model_name = self.fallback_model

                    # Try the fallback model (without retries to avoid double retry)
                    result = await _wrapped_func(*args, **kwargs)

                    observability.observe(
                        event_type=observability.ConversationEvents.MODEL_REQUEST_COMPLETED,
                        level=observability.EventLevel.INFO,
                        data={
                            "primary_model": original_model,
                            "fallback_model": self.fallback_model,
                            "fallback_success": True,
                        },
                        description=f"Fallback model {self.fallback_model} succeeded after {original_model} failed",
                    )

                    return result
                except Exception as fallback_error:
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.ERROR,
                        data={
                            "primary_model": original_model,
                            "fallback_model": self.fallback_model,
                            "primary_error": str(primary_error),
                            "fallback_error": str(fallback_error),
                        },
                        description=(
                            f"Both primary model {original_model} and fallback model {self.fallback_model} failed"
                        ),
                    )
                    # Restore original model settings
                    self.model_name = original_model
                    self._provider = original_provider
                    self._model = original_model_name
                    # Re-raise the original primary error since that's the main failure
                    raise primary_error
                finally:
                    # Always restore original model settings
                    self.model_name = original_model
                    self._provider = original_provider
                    self._model = original_model_name
            else:
                # No fallback model available, re-raise original error
                raise primary_error

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stop: Optional[Union[str, List[str]]] = None,
        files: Optional[List[Union[str, Path]]] = None,
        fusion_mode: Optional[str] = "adaptive",  # "basic", "adaptive", "advanced"
        metadata: Optional[Dict[str, Any]] = None,  # For tracking caller context
        **kwargs: Any,
    ) -> str:
        """
        Enhanced chat with unified multimodal processing.

        Args:
            messages: A list of messages in the conversation.
            temperature: Controls randomness. Overrides the instance setting when provided.
            max_tokens: The maximum number of tokens to generate.
            top_p: An alternative to sampling with temperature, called nucleus sampling.
            frequency_penalty: Penalize new tokens based on their frequency.
            presence_penalty: Penalize new tokens based on their presence.
            stop: Sequences where the generation will stop.
            files: List of file paths to process.
            fusion_mode: Processing mode - "basic" for simple pass-through,
                        "adaptive" for intelligent processing (default),
                        "advanced" for maximum fusion capabilities
            **kwargs: Additional provider-specific parameters.

        Returns:
            The generated text response as a string.

        Raises:
            LLMError: For various error conditions with appropriate classification.
        """
        # Emit LLM request started event
        try:
            # Build context description
            context_parts = [f"LLM chat request started for {self.model_name}"]
            if metadata:
                if metadata.get("agent_id"):
                    context_parts.append(f"by agent {metadata['agent_id']}")
                if metadata.get("task_id"):
                    context_parts.append(f"for task {metadata['task_id']}")

            observability.observe(
                event_type=observability.ConversationEvents.MODEL_REQUEST_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "model": self.model_name,
                    "provider": self._provider,
                    "message_count": len(messages),
                    "has_files": files is not None and len(files) > 0,
                    "file_count": len(files) if files else 0,
                    "fusion_mode": fusion_mode,
                    "temperature": temperature or self.temperature,
                    "max_tokens": max_tokens or self.max_tokens,
                    "metadata": metadata,
                },
                description=" ".join(context_parts),
            )
        except Exception:
            # Observability failure - continue gracefully
            pass  # Don't emit error event about failing to emit an event (circular)

        # Handle text-only conversations
        if not files:
            result = await self._text_chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stop=stop,
                **kwargs,
            )
            return result

        # Handle multimodal conversations
        if fusion_mode == "basic" or self.fusion_engine is None:
            # Use basic pass-through processing
            return await self._basic_chat_with_files(
                messages,
                files,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stop=stop,
                **kwargs,
            )
        else:
            # Use advanced fusion engine
            return await self._advanced_multimodal_processing(
                messages,
                files,
                fusion_mode,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stop=stop,
                **kwargs,
            )

    async def _advanced_multimodal_processing(
        self,
        messages: List[Dict[str, str]],
        files: List[Union[str, Path]],
        fusion_mode: str,
        **kwargs,
    ) -> str:
        """Process files using advanced fusion engine"""

        try:
            # Convert files to MultiModalContent format
            multimodal_content = await self._convert_files_to_content(files)

            if multimodal_content is None:
                # Fallback to basic processing if conversion failed
                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_STARTED,
                    level=observability.EventLevel.WARNING,
                    data={"fallback_reason": "multimodal_content_conversion_failed"},
                    description="Failed to convert files, using basic processing",
                )
                return await self._basic_chat_with_files(messages, files, **kwargs)

            # Map fusion_mode to ProcessingMode
            mode_mapping = {
                "adaptive": ProcessingMode.ADAPTIVE,
                "advanced": ProcessingMode.COMPREHENSIVE,
            }
            processing_mode = mode_mapping.get(fusion_mode, ProcessingMode.ADAPTIVE)

            # Extract user message for context
            user_message = self._extract_user_message(messages)

            # Process content with fusion engine
            fusion_result = await self.fusion_engine.process_multimodal_content(
                multimodal_content,
                processing_mode=processing_mode,
                fusion_options={
                    "user_context": user_message,
                    "conversation_history": messages[:-1] if len(messages) > 1 else [],
                },
            )

            # Convert fusion result to chat response
            return await self._synthesize_chat_response(fusion_result, user_message, **kwargs)

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.RESPONSE_GENERATION_STARTED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "fusion_mode": fusion_mode},
                description="Multimodal processing failed, falling back to basic processing",
            )
            # Fallback to basic processing on any error
            return await self._basic_chat_with_files(messages, files, **kwargs)

    async def _synthesize_chat_response(self, fusion_result, user_message: str, **kwargs) -> str:
        """Convert fusion result to natural chat response"""

        # Create synthesis prompt
        synthesis_prompt = f"""
Based on the following multimodal analysis, provide a natural response to the user's request.

User Request: {user_message}

Multimodal Analysis:
{fusion_result.unified_analysis}

Key Insights:
{', '.join(fusion_result.insights)}

Provide a helpful, conversational response that directly addresses what the user asked for.
        """

        # Use text-only chat for synthesis
        synthesis_messages = [{"role": "user", "content": synthesis_prompt}]
        return await self._text_chat(synthesis_messages, **kwargs)

    async def _basic_chat_with_files(
        self, messages: List[Dict[str, str]], files: Optional[List[Union[str, Path]]], **kwargs
    ) -> str:
        """Basic file processing implementation"""
        # Extract caching flag before it gets filtered out
        use_caching = kwargs.get("caching", True)

        # Auto-detect file processing results in messages and bypass cache
        # This prevents semantic cache from returning stale responses for file requests
        if use_caching:
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str) and "FILE PROCESSING RESULTS" in content:
                    use_caching = False
                    break

        async def _chat_request():
            # Prepare parameters using helper
            params = await self._prepare_chat_request(messages, files, **kwargs)

            # Pass caching flag to OneLLM to control semantic cache
            if not use_caching:
                params["caching"] = False

            # Check cache first (but exclude files from cache key for security)
            # Also skip cache if caching=False was explicitly passed
            cache_params = {k: v for k, v in params.items() if k != "files"}
            cache_key = _get_cache_key("chat", **cache_params)

            # Only use cache if no files are attached AND caching is enabled
            if not files and use_caching:
                cached_response = _get_cached_response(cache_key)
                if cached_response is not None:
                    return cached_response

            # Call OneLLM ChatCompletion using async method
            response = await ChatCompletion.acreate(**params)

            # Track token usage
            usage_data = self._extract_tokens_from_response(response)
            if usage_data and usage_data.get("total_tokens", 0) > 0:
                from ...services.observability.context import get_current_request_context

                context = get_current_request_context()
                if context:
                    context.tokens.add_tokens(self.model_name, usage_data)

            # Extract content from response using helper
            content = self._extract_content_from_response(response)

            # Cache the response only if no files were involved AND caching is enabled
            if not files and use_caching:
                _cache_response(cache_key, content)

            return content

        # Pass operation type for adaptive timeout via kwargs
        return await self._execute_with_resilience(_chat_request, operation_type="chat")

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stop: Optional[Union[str, List[str]]] = None,
        files: Optional[List[Union[str, Path]]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Enhanced chat that returns full response object when tools are present.

        This method is specifically for agents that need to handle tool calls.
        Unlike the regular chat() method which always returns a string, this
        method returns the full response object when tool calls are detected.

        Args:
            Same as chat() method.

        Returns:
            The full response object if tool calls are present, otherwise a string.
        """

        async def _chat_request_with_tools():
            # Prepare parameters using helper
            params = await self._prepare_chat_request(
                messages,
                files,
                temperature,
                max_tokens,
                top_p,
                frequency_penalty,
                presence_penalty,
                stop,
                **kwargs,
            )

            # Call OneLLM ChatCompletion using async method
            response = await ChatCompletion.acreate(**params)

            # Track token usage
            usage_data = self._extract_tokens_from_response(response)
            if usage_data and usage_data.get("total_tokens", 0) > 0:
                from ...services.observability.context import get_current_request_context

                context = get_current_request_context()
                if context:
                    context.tokens.add_tokens(self.model_name, usage_data)

            # Check if response contains tool calls - if so, return the full response
            if self._has_tool_calls(response):
                return response

            # Otherwise extract and return content as string
            return self._extract_content_from_response(response)

        # Pass operation type for adaptive timeout
        return await self._execute_with_resilience(_chat_request_with_tools, operation_type="tool")

    async def embed(self, text: str, **kwargs: Any) -> List[float]:
        """
        Generate embeddings for the provided text with enhanced error handling.

        Args:
            text: The text to embed.
            **kwargs: Additional parameters.

        Returns:
            The embeddings as a list of floats.

        Raises:
            LLMError: For various error conditions with appropriate classification.
        """
        # Skip embedding for empty strings - APIs don't handle these well
        if not text or not text.strip():
            return []

        async def _embed_request():
            # Default to openai/text-embedding-3-small if no embedding model is specified
            embedding_model = kwargs.pop("model", "openai/text-embedding-3-small")

            # Prepare parameters
            params = {
                "model": embedding_model,
                "input": text,
            }
            params.update(kwargs)

            # Check cache first
            cache_key = _get_cache_key("embed", **params)
            cached_response = _get_cached_response(cache_key)
            if cached_response is not None:
                return cached_response

            # Call OneLLM Embedding using async method
            response = await Embedding.acreate(**params)

            # Track token usage
            usage_data = self._extract_tokens_from_response(response)
            if usage_data:
                from ...services.observability.context import get_current_request_context

                context = get_current_request_context()
                if context:
                    context.tokens.add_tokens(embedding_model, usage_data)

            # Extract embedding from response
            if isinstance(response, dict) and "data" in response:
                embedding = response["data"][0]["embedding"]
            else:
                # If it's already a list, return it
                embedding = response

            # Cache the response
            _cache_response(cache_key, embedding)

            return embedding

        # Pass operation type for adaptive timeout
        return await self._execute_with_resilience(_embed_request, operation_type="embedding")

    async def transcribe(
        self, audio_file: Union[str, bytes], model: Optional[str] = None, **kwargs: Any
    ) -> str:
        """
        Transcribe audio to text using OneLLM's audio transcription API.

        Args:
            audio_file: The audio file to transcribe (path or bytes).
            model: The transcription model to use (default: uses provider default).
            **kwargs: Additional parameters like language, prompt, response_format.

        Returns:
            The transcribed text.

        Raises:
            LLMError: For various error conditions with appropriate classification.
        """

        async def _transcribe_request():
            # Validate audio file if it's a string path
            if isinstance(audio_file, str):
                # Validate file security
                if not await FileProcessor.validate_file_security(audio_file):
                    raise LLMError(
                        f"Audio file security validation failed: {audio_file}",
                        error_type=LLMErrorType.FILE_PROCESSING,
                        provider=self._provider,
                        retryable=False,
                    )

            # Use the transcription model from init or default to whisper-1
            transcription_model = model or self.model_name

            # For transcription models, we might need to adjust the model name
            # e.g., "openai/gpt-4" -> "openai/whisper-1"
            if "/" in transcription_model and not transcription_model.endswith("whisper-1"):
                provider = transcription_model.split("/")[0]
                transcription_model = f"{provider}/whisper-1"

            # Prepare parameters
            params = {
                "model": transcription_model,
                "file": audio_file,
            }
            params.update(kwargs)

            # Call OneLLM AudioTranscription using async method
            response = await AudioTranscription.create(**params)

            # Track token usage
            usage_data = self._extract_tokens_from_response(response)
            if usage_data:
                from ...services.observability.context import get_current_request_context

                context = get_current_request_context()
                if context:
                    context.tokens.add_tokens(transcription_model, usage_data)

            # Extract text from response
            if isinstance(response, dict) and "text" in response:
                return response["text"]
            else:
                return str(response)

        # Pass operation type for adaptive timeout
        return await self._execute_with_resilience(
            _transcribe_request, operation_type="transcription"
        )

    async def generate_embeddings(self, texts: List[str], **kwargs: Any) -> List[List[float]]:
        """
        Generate embeddings for a list of texts with enhanced error handling.

        Args:
            texts: List of texts to generate embeddings for.
            **kwargs: Additional parameters.

        Returns:
            A list of embeddings, each as a list of floats.

        Raises:
            LLMError: For various error conditions with appropriate classification.
        """

        async def _embed_batch_request():
            # Default to openai/text-embedding-3-small if no embedding model is specified
            embedding_model = kwargs.pop("model", "openai/text-embedding-3-small")

            # Prepare parameters
            params = {
                "model": embedding_model,
                "input": texts,
            }
            params.update(kwargs)

            # Check cache first
            cache_key = _get_cache_key("embed_batch", **params)
            cached_response = _get_cached_response(cache_key)
            if cached_response is not None:
                return cached_response

            # Call OneLLM Embedding using async method
            response = await Embedding.acreate(**params)

            # Track token usage
            usage_data = self._extract_tokens_from_response(response)
            if usage_data:
                from ...services.observability.context import get_current_request_context

                context = get_current_request_context()
                if context:
                    context.tokens.add_tokens(embedding_model, usage_data)

            # Extract embeddings from response
            if isinstance(response, dict) and "data" in response:
                embeddings = [item["embedding"] for item in response["data"]]
            elif hasattr(response, "data"):
                # Handle EmbeddingResponse object
                embeddings = [item.embedding for item in response.data]
            elif hasattr(response, "embeddings"):
                # Another possible response format
                embeddings = response.embeddings
            else:
                # If it's already a list of lists, return it
                embeddings = response

            # Cache the response
            _cache_response(cache_key, embeddings)

            return embeddings

        # Pass operation type for adaptive timeout
        return await self._execute_with_resilience(_embed_batch_request, operation_type="embedding")

    async def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        Generate text from the model with a simple prompt and enhanced error handling.

        Args:
            prompt: The prompt to send to the model
            temperature: Optional temperature parameter (overrides model default)
            max_tokens: Optional maximum tokens to generate (overrides model default)
            metadata: Optional metadata for tracking caller context
            **kwargs: Additional model-specific parameters

        Returns:
            The generated text as a string

        Raises:
            LLMError: For various error conditions with appropriate classification.
        """
        # Wrap the prompt in a message and call chat()
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata,
            **kwargs,
        )

    @property
    def model(self) -> str:
        """Get the model name without provider prefix."""
        return self.model_name.split("/")[-1] if "/" in self.model_name else self.model_name

    @property
    def provider(self) -> str:
        """Get the provider name."""
        return self.model_name.split("/")[0] if "/" in self.model_name else "openai"


# Utility functions for cache and monitoring management
def clear_llm_cache():
    """Clear the LLM response cache."""
    global _response_cache
    _response_cache.clear()
    observability.observe(
        event_type=observability.SystemEvents.LLM_CACHE_CLEARED,
        level=observability.EventLevel.DEBUG,
        data={"action": "cache_cleared"},
        description="LLM response cache cleared",
    )


def set_cache_ttl(ttl: int):
    """Set the cache TTL in seconds."""
    global _cache_ttl
    _cache_ttl = ttl
    observability.observe(
        event_type=observability.SystemEvents.LLM_CACHE_CONFIGURED,
        level=observability.EventLevel.DEBUG,
        data={"action": "cache_ttl_set", "ttl": ttl},
        description=f"Cache TTL set to {ttl} seconds",
    )


def get_cache_stats():
    """Get cache statistics."""
    return {
        "cache_size": len(_response_cache),
        "cache_ttl": _cache_ttl,
    }


def get_retry_stats():
    """Get retry and resilience statistics."""
    global _retry_stats
    success_rate = (
        _retry_stats["successful_requests"] / _retry_stats["total_requests"]
        if _retry_stats["total_requests"] > 0
        else 0
    )

    return {
        **_retry_stats,
        "success_rate": success_rate,
        "average_retries_per_request": (
            _retry_stats["retry_attempts"] / _retry_stats["total_requests"]
            if _retry_stats["total_requests"] > 0
            else 0
        ),
    }


def get_circuit_breaker_stats():
    """Get circuit breaker statistics."""
    stats = {}
    for key, cb in _circuit_breakers.items():
        stats[key] = {
            "state": cb.state,
            "failure_count": cb.failure_count,
            "last_failure_time": cb.last_failure_time,
            "failure_threshold": cb.failure_threshold,
        }
    return stats


def reset_all_stats():
    """Reset all statistics and circuit breakers."""
    global _retry_stats, _circuit_breakers
    _retry_stats = {
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "retry_attempts": 0,
        "circuit_breaker_trips": 0,
    }
    _circuit_breakers.clear()
    clear_llm_cache()
    observability.observe(
        event_type=observability.SystemEvents.LLM_STATISTICS_RESET,
        level=observability.EventLevel.INFO,
        data={"action": "stats_reset"},
        description="LLM statistics and circuit breakers reset",
    )


def calculate_adaptive_timeout(
    base_timeout: float = 30.0,
    messages: Optional[List[Dict[str, str]]] = None,
    tool_results: Optional[List[Any]] = None,
    operation_type: str = "chat",
    retry_attempt: int = 0,
    files: Optional[List[Union[str, Path]]] = None,
    max_timeout: float = 120.0,
) -> float:
    """
    Calculate adaptive timeout based on context size and operation complexity.

    Args:
        base_timeout: Base timeout in seconds (default: 30s)
        messages: List of messages in the conversation
        tool_results: List of tool execution results if any
        operation_type: Type of operation ("chat", "tool", "workflow")
        retry_attempt: Current retry attempt number (0 for first attempt)
        files: List of files being processed
        max_timeout: Maximum allowed timeout (default: 120s)

    Returns:
        Calculated timeout in seconds, capped at max_timeout
    """
    # Start with base timeout
    timeout = base_timeout

    # Scale based on context size (messages)
    if messages:
        # Count total tokens approximately (rough estimate: 4 chars per token)
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # Handle multi-modal content
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        total_chars += len(item.get("text", ""))

        estimated_tokens = total_chars / 4
        # Add 1 second per 1000 tokens
        timeout += estimated_tokens / 1000

    # Scale based on tool results
    if tool_results:
        # Add 5 seconds per tool result (tools often have substantial output)
        timeout += len(tool_results) * 5

    # Scale based on files
    if files:
        # Add 3 seconds per file (for processing overhead)
        timeout += len(files) * 3

    # Apply operation type modifier
    operation_modifiers = {
        "chat": 1.0,  # Standard chat operations
        "tool": 1.2,  # Tool operations need more time
        "workflow": 1.5,  # Workflow operations are complex
        "embedding": 0.5,  # Embeddings are typically faster
        "transcription": 2.0,  # Audio transcription can be slow
    }
    modifier = operation_modifiers.get(operation_type, 1.0)
    timeout *= modifier

    # Apply retry escalation (1.5x for each retry)
    if retry_attempt > 0:
        timeout *= 1.5**retry_attempt

    # Cap at maximum timeout
    final_timeout = min(timeout, max_timeout)

    # Log the calculation for debugging
    observability.observe(
        event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
        level=observability.EventLevel.DEBUG,
        data={
            "base_timeout": base_timeout,
            "calculated_timeout": timeout,
            "final_timeout": final_timeout,
            "context_size": len(messages) if messages else 0,
            "tool_results_count": len(tool_results) if tool_results else 0,
            "file_count": len(files) if files else 0,
            "operation_type": operation_type,
            "retry_attempt": retry_attempt,
            "modifier": modifier,
        },
        description=f"Calculated adaptive timeout: {final_timeout:.1f}s for {operation_type} operation",
    )

    return final_timeout
