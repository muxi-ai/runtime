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
import mimetypes
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import random

from loguru import logger

# File processing imports
# Required runtime dependencies
import aiofiles
import magic

# Import OneLLM components
from onellm import ChatCompletion, Embedding
from onellm.config import set_api_key
from onellm.errors import AuthenticationError, RateLimitError, InvalidRequestError

# Import observability components
from ..observability import ObservabilityManager, EventType, EventLevel


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
                logger.warning(f"File {file_path} exceeds size limit: {file_size} bytes")
                return False

            # Basic security check - avoid obviously dangerous files
            if file_path.suffix.lower() in [".exe", ".bat", ".sh", ".scr"]:
                logger.warning(f"Potentially dangerous file type: {file_path.suffix}")
                return False

            return True
        except Exception as e:
            logger.error(f"File validation error: {str(e)}")
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
            logger.debug(f"Magic MIME detection failed: {e}")

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
            logger.warning("Circuit breaker OPENED after {} failures".format(self.failure_count))


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
        return LLMError(
            message=f"Request timed out: {error_message}",
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
    *args,
    **kwargs,
):
    """Execute function with exponential backoff retry strategy."""
    global _retry_stats

    _retry_stats["total_requests"] += 1

    for attempt in range(max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            _retry_stats["successful_requests"] += 1
            return result
        except LLMError as e:
            if attempt == max_retries or not e.retryable or e.error_type not in retryable_errors:
                _retry_stats["failed_requests"] += 1
                logger.error(
                    f"Request failed after {attempt + 1} attempts: {str(e)}",
                    extra={
                        "error_type": e.error_type.value,
                        "provider": e.provider,
                        "retryable": e.retryable,
                        "attempt": attempt + 1,
                    },
                )
                raise e

            _retry_stats["retry_attempts"] += 1

            # Calculate delay with exponential backoff
            delay = min(base_delay * (2**attempt), max_delay)
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)  # Add 50% jitter

            logger.warning(
                f"Request failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}. "
                f"Retrying in {delay:.2f}s",
                extra={
                    "error_type": e.error_type.value,
                    "provider": e.provider,
                    "retry_delay": delay,
                    "attempt": attempt + 1,
                },
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
    set_api_key(provider, api_key)
    logger.debug(f"API key set for provider: {provider}")


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
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
        enable_circuit_breaker: bool = True,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: float = 60.0,
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
            base_retry_delay: Base delay for exponential backoff.
            max_retry_delay: Maximum delay for exponential backoff.
            enable_circuit_breaker: Enable circuit breaker pattern.
            circuit_breaker_threshold: Number of failures before opening circuit.
            circuit_breaker_timeout: Time to wait before retrying after circuit opens.
            **kwargs: Additional parameters passed to the model.
        """
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self.enable_circuit_breaker = enable_circuit_breaker
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

        logger.info(
            f"Initialized LLM with {self.model_name}",
            extra={
                "provider": self._provider,
                "model": self._model,
                "timeout": timeout,
                "max_retries": max_retries,
                "circuit_breaker_enabled": enable_circuit_breaker,
            },
        )

        # Initialize fusion engine for advanced multimodal processing (lazy loaded)
        self._fusion_engine = None

    @property
    def fusion_engine(self):
        """Lazy initialize fusion engine for advanced multimodal processing"""
        if self._fusion_engine is None:
            try:
                from ..overlord.workflow.multimodal import MultiModalFusionEngine

                self._fusion_engine = MultiModalFusionEngine(self)
                logger.debug("Initialized fusion engine for advanced multimodal processing")
            except ImportError as e:
                logger.warning(
                    f"Could not import fusion engine: {e}. " "Falling back to basic processing."
                )
                self._fusion_engine = None
        return self._fusion_engine

    async def _convert_files_to_content(self, files: List[Union[str, Path]]):
        """Convert file paths to MultiModalContent objects for fusion engine"""
        try:
            from ..overlord.workflow.multimodal import MultiModalContent

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
            from ..overlord.workflow.multimodal import ModalityType

            import mimetypes

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
        return await self._legacy_chat_with_files(messages, None, **kwargs)

    async def _execute_with_resilience(self, func, *args, **kwargs):
        """Execute a function with full resilience patterns."""

        async def _wrapped_func(*args, **kwargs):
            try:
                # Add timeout to the function call
                return await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
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

        # Apply exponential backoff retry
        return await _exponential_backoff_retry(
            func_to_retry,
            max_retries=self.max_retries,
            base_delay=self.base_retry_delay,
            max_delay=self.max_retry_delay,
            *args,
            **kwargs,
        )

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
        start_time = time.time()

        # Emit LLM request started event
        try:
            await ObservabilityManager.get_instance().event_logger.emit_event(
                EventType.LLM_REQUEST_STARTED,
                level=EventLevel.INFO,
                data={
                    "model": self.model_name,
                    "provider": self._provider,
                    "message_count": len(messages),
                    "has_files": files is not None and len(files) > 0,
                    "file_count": len(files) if files else 0,
                    "fusion_mode": fusion_mode,
                    "temperature": temperature or self.temperature,
                    "max_tokens": max_tokens or self.max_tokens,
                },
                description=f"LLM chat request started for {self.model_name}",
            )
        except Exception as e:
            logger.warning(f"Failed to emit LLM request started event: {e}")

        # Handle text-only conversations
        if not files:
            return await self._text_chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stop=stop,
                **kwargs,
            )

        # Handle multimodal conversations
        if fusion_mode == "basic" or self.fusion_engine is None:
            # Use basic pass-through processing
            return await self._legacy_chat_with_files(
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
            from ..overlord.workflow.multimodal import ProcessingMode

            # Convert files to MultiModalContent format
            multimodal_content = await self._convert_files_to_content(files)

            if multimodal_content is None:
                # Fallback to basic processing if conversion failed
                logger.warning(
                    "Failed to convert files to multimodal content, " "using basic processing"
                )
                return await self._legacy_chat_with_files(messages, files, **kwargs)

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
            logger.error(f"Error in advanced multimodal processing: {e}")
            # Fallback to basic processing on any error
            return await self._legacy_chat_with_files(messages, files, **kwargs)

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

    async def _legacy_chat_with_files(
        self, messages: List[Dict[str, str]], files: Optional[List[Union[str, Path]]], **kwargs
    ) -> str:
        """Legacy file processing implementation for backward compatibility"""

        async def _chat_request():
            # Process files if provided
            processed_files = []
            if files:
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

                        logger.debug(f"Successfully processed file: {file_path}")

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
                        )

            # Prepare parameters
            params = {
                "model": self.model_name,  # Use full model name with provider prefix
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
            }

            # Add files to parameters if processed
            if processed_files:
                params["files"] = processed_files

            # Add optional parameters if provided
            for param_name in [
                "max_tokens",
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "stop",
            ]:
                if param_name in kwargs and kwargs[param_name] is not None:
                    params[param_name] = kwargs[param_name]
                elif param_name == "max_tokens" and self.max_tokens is not None:
                    params["max_tokens"] = self.max_tokens

            # Add any additional kwargs
            additional_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k
                not in [
                    "temperature",
                    "max_tokens",
                    "top_p",
                    "frequency_penalty",
                    "presence_penalty",
                    "stop",
                ]
            }
            params.update(additional_kwargs)
            params.update(self.additional_params)

            # Check cache first (but exclude files from cache key for security)
            cache_params = {k: v for k, v in params.items() if k != "files"}
            cache_key = _get_cache_key("chat", **cache_params)

            # Only use cache if no files are attached
            if not files:
                cached_response = _get_cached_response(cache_key)
                if cached_response is not None:
                    logger.debug(f"Cache hit for chat request: {cache_key}")
                    return cached_response

            # Call OneLLM ChatCompletion using async method
            response = await ChatCompletion.acreate(**params)

            # Extract content from response
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
                if "content" in response_str:
                    # Try to extract content using regex
                    import re

                    match = re.search(r"'content':\s*'([^']*)'", response_str)
                    if match:
                        content = match.group(1)
                    else:
                        content = "Error: Could not extract content from response"
                else:
                    content = "Error: No content found in response"

            # Cache the response only if no files were involved
            if not files:
                _cache_response(cache_key, content)

            return content

        return await self._execute_with_resilience(_chat_request)

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

        async def _embed_request():
            # Default to text-embedding-3-small if no embedding model is specified
            embedding_model = kwargs.pop("model", "text-embedding-3-small")

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
                logger.debug(f"Cache hit for embedding request: {cache_key}")
                return cached_response

            # Call OneLLM Embedding using async method
            response = await Embedding.acreate(**params)

            # Extract embedding from response
            if isinstance(response, dict) and "data" in response:
                embedding = response["data"][0]["embedding"]
            else:
                # If it's already a list, return it
                embedding = response

            # Cache the response
            _cache_response(cache_key, embedding)

            return embedding

        return await self._execute_with_resilience(_embed_request)

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
            # Default to text-embedding-3-small if no embedding model is specified
            embedding_model = kwargs.pop("model", "text-embedding-3-small")

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
                logger.debug(f"Cache hit for batch embedding request: {cache_key}")
                return cached_response

            # Call OneLLM Embedding using async method
            response = await Embedding.acreate(**params)

            # Extract embeddings from response
            if isinstance(response, dict) and "data" in response:
                embeddings = [item["embedding"] for item in response["data"]]
            else:
                # If it's already a list of lists, return it
                embeddings = response

            # Cache the response
            _cache_response(cache_key, embeddings)

            return embeddings

        return await self._execute_with_resilience(_embed_batch_request)

    async def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Generate text from the model with a simple prompt and enhanced error handling.

        Args:
            prompt: The prompt to send to the model
            temperature: Optional temperature parameter (overrides model default)
            max_tokens: Optional maximum tokens to generate (overrides model default)
            **kwargs: Additional model-specific parameters

        Returns:
            The generated text as a string

        Raises:
            LLMError: For various error conditions with appropriate classification.
        """
        # Wrap the prompt in a message and call chat()
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(
            messages=messages, temperature=temperature, max_tokens=max_tokens, **kwargs
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
    logger.info("LLM cache cleared")


def set_cache_ttl(ttl: int):
    """Set the cache TTL in seconds."""
    global _cache_ttl
    _cache_ttl = ttl
    logger.info(f"LLM cache TTL set to {ttl} seconds")


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
    logger.info("All LLM statistics and circuit breakers reset")
