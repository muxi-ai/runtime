"""
Local embedding support using sentence-transformers.

This module provides a local embedding fallback when no API-based embedding
model is configured in the formation. It uses the sentence-transformers library
with the all-MiniLM-L6-v2 model to generate high-quality semantic embeddings.

The model is loaded lazily and cached globally to avoid repeated initialization
overhead. Thread-safety is ensured through a lock mechanism.

Model Details:
- Model: all-MiniLM-L6-v2
- Dimensions: 384
- Size: ~22MB download (one-time)
- First load: ~10-15 seconds
- Subsequent embeddings: <100ms

Usage:
    from muxi.runtime.services.memory.local_embeddings import (
        get_local_embedding,
        get_local_embedding_dimension,
        LOCAL_EMBEDDING_MODEL_NAME,
    )

    # Generate embedding
    embedding = get_local_embedding("Hello, world!")

    # Get dimension for the model
    dimension = get_local_embedding_dimension()  # Returns 384
"""

import threading
from typing import List, Optional

from .. import observability

# Default local embedding model
LOCAL_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Alternative models available (can be used via configuration in future)
AVAILABLE_LOCAL_MODELS = {
    "all-MiniLM-L6-v2": {
        "dimension": 384,
        "description": "Fast, lightweight model for semantic similarity",
        "size_mb": 22,
    },
    "paraphrase-multilingual-MiniLM-L12-v2": {
        "dimension": 384,
        "description": "Multilingual support (50+ languages)",
        "size_mb": 118,
    },
    "all-mpnet-base-v2": {
        "dimension": 768,
        "description": "Higher quality, slower performance",
        "size_mb": 420,
    },
}

# Global model cache with thread-safe initialization
_model = None
_model_lock = threading.Lock()
_model_name = None
_initialization_logged = False


def get_local_embedding(
    text: str,
    model_name: str = LOCAL_EMBEDDING_MODEL_NAME,
) -> List[float]:
    """
    Generate embedding using local sentence-transformer model.

    This function provides a synchronous interface for generating embeddings
    using a local sentence-transformer model. The model is loaded lazily on
    first use and cached globally for efficiency.

    Args:
        text: Text to embed
        model_name: Model name (default: all-MiniLM-L6-v2)

    Returns:
        List of floats (384 dimensions for MiniLM models)

    Example:
        >>> embedding = get_local_embedding("Hello, world!")
        >>> len(embedding)
        384
    """
    # Skip embedding for empty strings
    if not text or not text.strip():
        return []

    global _model, _model_name, _initialization_logged

    with _model_lock:
        # Check if we need to load or reload the model
        if _model is None or _model_name != model_name:
            # Log first load information
            if not _initialization_logged:
                observability.observe(
                    event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                    level=observability.EventLevel.INFO,
                    data={
                        "model_name": model_name,
                        "dimension": get_local_embedding_dimension(model_name),
                        "type": "local_fallback",
                    },
                    description=(
                        f"Loading local embedding model '{model_name}' (one-time, ~10s). "
                        "For better quality, configure: llm.models.embedding"
                    ),
                )
                _initialization_logged = True

            try:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(model_name)
                _model_name = model_name

                # Log successful initialization
                observability.observe(
                    event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                    level=observability.EventLevel.INFO,
                    data={
                        "model_name": model_name,
                        "dimension": get_local_embedding_dimension(model_name),
                        "status": "ready",
                    },
                    description=f"Local embedding model ready ({get_local_embedding_dimension(model_name)} dimensions)",
                )
            except ImportError as e:
                observability.observe(
                    event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "model_name": model_name,
                        "error": str(e),
                        "error_type": "ImportError",
                    },
                    description="sentence-transformers not installed. Install with: pip install sentence-transformers",
                )
                raise ImportError(
                    "sentence-transformers is required for local embeddings. "
                    "Install with: pip install sentence-transformers"
                ) from e
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "model_name": model_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Failed to load local embedding model: {e}",
                )
                raise

    # Generate embedding
    try:
        embedding = _model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
            level=observability.EventLevel.ERROR,
            data={
                "text_length": len(text),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            description=f"Failed to generate local embedding: {e}",
        )
        raise


async def get_local_embedding_async(
    text: str,
    model_name: str = LOCAL_EMBEDDING_MODEL_NAME,
) -> List[float]:
    """
    Async wrapper for generating local embeddings.

    This function provides an async interface for generating embeddings
    using a local sentence-transformer model. The actual embedding generation
    is synchronous but wrapped for async compatibility.

    Args:
        text: Text to embed
        model_name: Model name (default: all-MiniLM-L6-v2)

    Returns:
        List of floats (384 dimensions for MiniLM models)

    Example:
        >>> embedding = await get_local_embedding_async("Hello, world!")
        >>> len(embedding)
        384
    """
    import asyncio

    # Run in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_local_embedding, text, model_name)


def get_local_embedding_dimension(model_name: str = LOCAL_EMBEDDING_MODEL_NAME) -> int:
    """
    Get embedding dimension for the specified model.

    Args:
        model_name: Model name (default: all-MiniLM-L6-v2)

    Returns:
        Integer dimension of the embedding vector
    """
    model_info = AVAILABLE_LOCAL_MODELS.get(model_name)
    if model_info:
        return model_info["dimension"]

    # Default to 384 for unknown models (most MiniLM variants use this)
    return 384


def is_local_embedding_available() -> bool:
    """
    Check if local embedding support is available.

    Returns:
        True if sentence-transformers is installed, False otherwise
    """
    try:
        import sentence_transformers  # noqa: F401

        return True
    except ImportError:
        return False


def clear_local_embedding_cache() -> None:
    """
    Clear the cached model to free memory.

    This function clears the global model cache, which can be useful
    for testing or when switching between models.
    """
    global _model, _model_name, _initialization_logged

    with _model_lock:
        _model = None
        _model_name = None
        _initialization_logged = False


class LocalEmbeddingProvider:
    """
    A class-based wrapper for local embedding generation.

    This class provides an interface compatible with the LLM embedding API,
    making it easy to use as a drop-in replacement when no API-based
    embedding model is configured.

    Attributes:
        model_name: The name of the sentence-transformer model
        dimension: The dimension of the embedding vectors

    Example:
        >>> provider = LocalEmbeddingProvider()
        >>> result = await provider.embed("Hello, world!")
        >>> len(result)
        384
    """

    def __init__(self, model_name: str = LOCAL_EMBEDDING_MODEL_NAME):
        """
        Initialize the local embedding provider.

        Args:
            model_name: The sentence-transformer model to use
        """
        self.model_name = model_name
        self.dimension = get_local_embedding_dimension(model_name)

    async def embed(self, text: str) -> List[float]:
        """
        Generate embedding for text (async interface).

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding
        """
        return await get_local_embedding_async(text, self.model_name)

    def embed_sync(self, text: str) -> List[float]:
        """
        Generate embedding for text (sync interface).

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding
        """
        return get_local_embedding(text, self.model_name)
