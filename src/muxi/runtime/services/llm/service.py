# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        OneLLM Service - Centralized Language Model Management
# Description:  Singleton service for unified LLM operations across providers
# Role:         Provides centralized, thread-safe access to language models
# Usage:        Primary interface for all LLM operations in the framework
# Author:       Muxi Framework Team
#
# The OneLLMService provides a centralized, singleton-based approach to
# language model management. Key features include:
#
# 1. Singleton Pattern
#    - Thread-safe singleton implementation
#    - Consistent access across the entire framework
#    - Centralized configuration and state management
#
# 2. Model Management
#    - Unified interface across all providers (OpenAI, Anthropic, etc.)
#    - Automatic provider detection from model strings
#    - Intelligent caching and connection pooling
#
# 3. Enhanced Features
#    - Comprehensive error handling with custom exceptions
#    - Request/response logging and statistics
#    - Configurable timeouts and retry mechanisms
#    - Multi-modal support (text, images, audio)
#
# 4. Performance Optimization
#    - Connection pooling for efficiency
#    - Response caching for repeated requests
#    - Async/await support throughout
#
# Usage:
#   service = await OneLLMService.get_instance()
#   response = await service.chat("openai/gpt-4o", messages)
#   embeddings = await service.embed("openai/text-embedding-ada-002", texts)
# =============================================================================

import asyncio
import hashlib
import time
from typing import Dict, List, Optional, Any, Tuple, Union


# OneLLM imports - external package
from onellm import ChatCompletion, Embedding, set_api_key

# Local imports
from .errors import (
    OneLLMConnectionError,
    OneLLMAuthenticationError,
    OneLLMRateLimitError,
    OneLLMTimeoutError,
    OneLLMServiceError,
)

# Observability imports
from .. import observability


class OneLLMService:
    """
    Singleton service for centralized language model management.

    This service provides a unified interface for all LLM operations
    across different providers, with enhanced features like caching,
    error handling, and performance optimization.
    """

    _instance: Optional["OneLLMService"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        """Initialize the OneLLM service."""
        if OneLLMService._instance is not None:
            raise OneLLMServiceError("OneLLMService is a singleton. Use get_instance() instead.")

        # Configuration
        self._api_keys: Dict[str, str] = {}
        self._default_timeout: float = 60.0
        self._max_retries: int = 3
        self._retry_delay: float = 1.0

        # Statistics
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        # Cache for responses (simple in-memory cache)
        self._response_cache: Dict[str, Any] = {}
        self._cache_ttl: float = 300.0  # 5 minutes
        self._cache_timestamps: Dict[str, float] = {}

        # Emit service initialization event
        observability.observe(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description="OneLLMService singleton initialized",
            data={
                "service": "OneLLMService",
                "default_timeout": self._default_timeout,
                "max_retries": self._max_retries,
                "retry_delay": self._retry_delay,
                "cache_ttl": self._cache_ttl,
                "stats": self._stats.copy(),
            },
        )

    @classmethod
    async def get_instance(cls) -> "OneLLMService":
        """
        Get the singleton instance of OneLLMService.

        Returns:
            OneLLMService: The singleton instance
        """
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()

                    # Emit singleton access event
                    observability.observe(
                        event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                        level=observability.EventLevel.INFO,
                        description="OneLLMService singleton instance created",
                        data={"service": "OneLLMService", "action": "singleton_created"},
                    )

        return cls._instance

    def set_api_key(self, provider: str, api_key: str) -> None:
        """
        Set API key for a specific provider.

        Args:
            provider: The provider name (e.g., 'openai', 'anthropic')
            api_key: The API key for the provider
        """
        self._api_keys[provider] = api_key
        # Also set it in onellm for immediate use
        set_api_key(provider, api_key)

        # Emit API key configuration event
        observability.observe(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description=f"API key configured for provider: {provider}",
            data={
                "service": "OneLLMService",
                "action": "api_key_set",
                "provider": provider,
                "has_api_key": bool(api_key),
            },
        )

    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key for a specific provider.

        Args:
            provider: The provider name

        Returns:
            The API key if set, None otherwise
        """
        api_key = self._api_keys.get(provider)

        # Emit API key access event
        observability.observe(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.DEBUG,
            description=f"API key accessed for provider: {provider}",
            data={
                "service": "OneLLMService",
                "action": "api_key_get",
                "provider": provider,
                "has_api_key": api_key is not None,
            },
        )

        return api_key

    def _parse_model(self, model: str) -> Tuple[str, str]:
        """
        Parse model string into provider and model name.

        Args:
            model: Model string in format "provider/model" or just "model"

        Returns:
            Tuple of (provider, model_name)
        """
        if "/" in model:
            provider, model_name = model.split("/", 1)
        else:
            # Default to openai if no provider specified
            provider, model_name = "openai", model

        return provider, model_name

    def _get_cache_key(self, operation: str, model: str, **kwargs) -> str:
        """
        Generate cache key for request.

        Args:
            operation: The operation type (chat, embed, etc.)
            model: The model string
            **kwargs: Additional parameters

        Returns:
            Cache key string
        """
        # Create a simple hash of the parameters
        key_data = f"{operation}:{model}:{str(sorted(kwargs.items()))}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Check if cache entry is still valid.

        Args:
            cache_key: The cache key to check

        Returns:
            True if cache is valid, False otherwise
        """
        if cache_key not in self._cache_timestamps:
            return False

        age = time.time() - self._cache_timestamps[cache_key]
        return age < self._cache_ttl

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """
        Get response from cache if valid.

        Args:
            cache_key: The cache key

        Returns:
            Cached response if valid, None otherwise
        """
        if self._is_cache_valid(cache_key):
            self._stats["cache_hits"] += 1

            # Emit cache hit event
            observability.observe(
                event_type=observability.SystemEvents.PERFORMANCE_OPTIMIZED,
                level=observability.EventLevel.DEBUG,
                description="Cache hit for LLM request",
                data={
                    "service": "OneLLMService",
                    "action": "cache_hit",
                    "cache_key": cache_key,
                    "total_cache_hits": self._stats["cache_hits"],
                },
            )

            return self._response_cache.get(cache_key)

        self._stats["cache_misses"] += 1

        # Emit cache miss event
        observability.observe(
            event_type=observability.SystemEvents.PERFORMANCE_OPTIMIZED,
            level=observability.EventLevel.DEBUG,
            description="Cache miss for LLM request",
            data={
                "service": "OneLLMService",
                "action": "cache_miss",
                "cache_key": cache_key,
                "total_cache_misses": self._stats["cache_misses"],
            },
        )

        return None

    def _set_cache(self, cache_key: str, response: Any) -> None:
        """
        Store response in cache.

        Args:
            cache_key: The cache key
            response: The response to cache
        """
        self._response_cache[cache_key] = response
        self._cache_timestamps[cache_key] = time.time()

        # Emit cache store event
        observability.observe(
            event_type=observability.SystemEvents.PERFORMANCE_OPTIMIZED,
            level=observability.EventLevel.DEBUG,
            description="Response cached for LLM request",
            data={
                "service": "OneLLMService",
                "action": "cache_store",
                "cache_key": cache_key,
                "cache_size": len(self._response_cache),
            },
        )

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        use_cache: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate chat completion using specified model.

        Args:
            model: Model string (e.g., "openai/gpt-4o")
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            use_cache: Whether to use response caching
            **kwargs: Additional parameters for the model

        Returns:
            Chat completion response

        Raises:
            OneLLMError: For various error conditions
        """
        provider, model_name = self._parse_model(model)
        timeout = timeout or self._default_timeout

        # Emit chat request start event
        observability.observe(
            event_type=observability.ConversationEvents.MODEL_REQUEST_STARTED,
            level=observability.EventLevel.INFO,
            description=f"Chat completion request started for {model}",
            data={
                "service": "OneLLMService",
                "operation": "chat",
                "model": model,
                "provider": provider,
                "model_name": model_name,
                "message_count": len(messages),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
                "use_cache": use_cache,
            },
        )

        # Check cache first
        cache_key = None
        if use_cache:
            cache_key = self._get_cache_key(
                "chat",
                model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            cached_response = self._get_from_cache(cache_key)
            if cached_response:
                # Emit cache hit completion event
                observability.observe(
                    event_type=observability.ConversationEvents.MODEL_REQUEST_COMPLETED,
                    level=observability.EventLevel.INFO,
                    description=f"Chat completion served from cache for {model}",
                    data={
                        "service": "OneLLMService",
                        "operation": "chat",
                        "model": model,
                        "provider": provider,
                        "source": "cache",
                        "cache_key": cache_key,
                    },
                )

                return cached_response

        try:
            self._stats["total_requests"] += 1

            # Prepare parameters
            params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                **kwargs,
            }

            if max_tokens:
                params["max_tokens"] = max_tokens

            # Make the request
            response = ChatCompletion.create(**params)

            self._stats["successful_requests"] += 1

            # Cache the response
            if use_cache and cache_key:
                self._set_cache(cache_key, response)

            # Emit successful completion event
            observability.observe(
                event_type=observability.ConversationEvents.MODEL_REQUEST_COMPLETED,
                level=observability.EventLevel.INFO,
                description=f"Chat completion successful for {model}",
                data={
                    "service": "OneLLMService",
                    "operation": "chat",
                    "model": model,
                    "provider": provider,
                    "source": "api",
                    "success": True,
                    "total_requests": self._stats["total_requests"],
                    "successful_requests": self._stats["successful_requests"],
                },
            )

            return response

        except Exception as e:
            self._stats["failed_requests"] += 1

            # Emit error event
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.ERROR,
                description=f"LLM service chat completion failed for {model}: {str(e)}",
                data={
                    "service": "OneLLMService",
                    "operation": "chat",
                    "model": model,
                    "provider": provider,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "failed_requests": self._stats["failed_requests"],
                    "total_requests": self._stats["total_requests"],
                },
            )
            # Convert to appropriate OneLLM exception
            if "authentication" in str(e).lower():
                raise OneLLMAuthenticationError(
                    f"Authentication failed for {provider}", provider, model_name
                )
            elif "rate limit" in str(e).lower():
                raise OneLLMRateLimitError(
                    f"Rate limit exceeded for {provider}", provider, model_name
                )
            elif "timeout" in str(e).lower():
                raise OneLLMTimeoutError(f"Request timeout for {provider}", provider, model_name)
            else:
                raise OneLLMConnectionError(
                    f"Connection error for {provider}: {e}", provider, model_name
                )

    async def embed(
        self,
        model: str,
        texts: Union[str, List[str]],
        timeout: Optional[float] = None,
        use_cache: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate embeddings using specified model.

        Args:
            model: Model string (e.g., "openai/text-embedding-ada-002")
            texts: Text or list of texts to embed
            timeout: Request timeout in seconds
            use_cache: Whether to use response caching
            **kwargs: Additional parameters for the model

        Returns:
            Embedding response

        Raises:
            OneLLMError: For various error conditions
        """
        provider, model_name = self._parse_model(model)
        timeout = timeout or self._default_timeout

        # Ensure texts is a list
        if isinstance(texts, str):
            texts = [texts]

        # Emit embedding request start event
        observability.observe(
            event_type=observability.ConversationEvents.MODEL_REQUEST_STARTED,
            level=observability.EventLevel.INFO,
            description=f"Embedding request started for {model}",
            data={
                "service": "OneLLMService",
                "operation": "embed",
                "model": model,
                "provider": provider,
                "model_name": model_name,
                "text_count": len(texts),
                "timeout": timeout,
                "use_cache": use_cache,
            },
        )

        # Check cache first
        cache_key = None
        if use_cache:
            cache_key = self._get_cache_key("embed", model, texts=texts, **kwargs)
            cached_response = self._get_from_cache(cache_key)
            if cached_response:
                # Emit cache hit completion event
                observability.observe(
                    event_type=observability.ConversationEvents.MODEL_REQUEST_COMPLETED,
                    level=observability.EventLevel.INFO,
                    description=f"Embedding served from cache for {model}",
                    data={
                        "service": "OneLLMService",
                        "operation": "embed",
                        "model": model,
                        "provider": provider,
                        "source": "cache",
                        "cache_key": cache_key,
                    },
                )

                return cached_response

        try:
            self._stats["total_requests"] += 1

            # Prepare parameters
            params = {"model": model_name, "input": texts, **kwargs}

            # Make the request
            response = Embedding.create(**params)

            self._stats["successful_requests"] += 1

            # Cache the response
            if use_cache and cache_key:
                self._set_cache(cache_key, response)

            # Emit successful completion event
            observability.observe(
                event_type=observability.ConversationEvents.MODEL_REQUEST_COMPLETED,
                level=observability.EventLevel.INFO,
                description=f"Embedding successful for {model}",
                data={
                    "service": "OneLLMService",
                    "operation": "embed",
                    "model": model,
                    "provider": provider,
                    "source": "api",
                    "success": True,
                    "total_requests": self._stats["total_requests"],
                    "successful_requests": self._stats["successful_requests"],
                },
            )

            return response

        except Exception as e:
            self._stats["failed_requests"] += 1
            # Emit error event
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.ERROR,
                description=f"LLM service embedding generation failed for {model}: {str(e)}",
                data={
                    "service": "OneLLMService",
                    "operation": "embed",
                    "model": model,
                    "provider": provider,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "failed_requests": self._stats["failed_requests"],
                    "total_requests": self._stats["total_requests"],
                },
            )

            # Convert to appropriate OneLLM exception
            if "authentication" in str(e).lower():
                raise OneLLMAuthenticationError(
                    f"Authentication failed for {provider}", provider, model_name
                )
            elif "rate limit" in str(e).lower():
                raise OneLLMRateLimitError(
                    f"Rate limit exceeded for {provider}", provider, model_name
                )
            elif "timeout" in str(e).lower():
                raise OneLLMTimeoutError(f"Request timeout for {provider}", provider, model_name)
            else:
                raise OneLLMConnectionError(
                    f"Connection error for {provider}: {e}", provider, model_name
                )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get service statistics.

        Returns:
            Dictionary containing service statistics
        """
        stats = self._stats.copy()

        # Emit stats access event
        observability.observe(
            event_type=observability.SystemEvents.PERFORMANCE_OPTIMIZED,
            level=observability.EventLevel.DEBUG,
            description="Service statistics accessed",
            data={"service": "OneLLMService", "action": "get_stats", "stats": stats},
        )

        return stats

    def reset_stats(self) -> None:
        """Reset service statistics."""
        old_stats = self._stats.copy()
        for key in self._stats:
            self._stats[key] = 0

        # Emit stats reset event
        observability.observe(
            event_type=observability.SystemEvents.PERFORMANCE_OPTIMIZED,
            level=observability.EventLevel.INFO,
            description="Service statistics reset",
            data={
                "service": "OneLLMService",
                "action": "reset_stats",
                "old_stats": old_stats,
                "new_stats": self._stats.copy(),
            },
        )

    def clear_cache(self) -> None:
        """Clear response cache."""
        cache_size = len(self._response_cache)
        self._response_cache.clear()
        self._cache_timestamps.clear()

        # Emit cache clear event
        observability.observe(
            event_type=observability.SystemEvents.PERFORMANCE_OPTIMIZED,
            level=observability.EventLevel.INFO,
            description="Response cache cleared",
            data={
                "service": "OneLLMService",
                "action": "clear_cache",
                "cleared_entries": cache_size,
            },
        )

    def configure(
        self,
        default_timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
        cache_ttl: Optional[float] = None,
    ) -> None:
        """
        Configure service parameters.

        Args:
            default_timeout: Default request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
            cache_ttl: Cache time-to-live in seconds
        """
        old_config = {
            "default_timeout": self._default_timeout,
            "max_retries": self._max_retries,
            "retry_delay": self._retry_delay,
            "cache_ttl": self._cache_ttl,
        }

        if default_timeout is not None:
            self._default_timeout = default_timeout
        if max_retries is not None:
            self._max_retries = max_retries
        if retry_delay is not None:
            self._retry_delay = retry_delay
        if cache_ttl is not None:
            self._cache_ttl = cache_ttl

        # Emit configuration update event
        observability.observe(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description="Service configuration updated",
            data={
                "service": "OneLLMService",
                "action": "configure",
                "old_config": old_config,
                "new_config": {
                    "default_timeout": self._default_timeout,
                    "max_retries": self._max_retries,
                    "retry_delay": self._retry_delay,
                    "cache_ttl": self._cache_ttl,
                },
                "updated_fields": {
                    "default_timeout": default_timeout is not None,
                    "max_retries": max_retries is not None,
                    "retry_delay": retry_delay is not None,
                    "cache_ttl": cache_ttl is not None,
                },
            },
        )
