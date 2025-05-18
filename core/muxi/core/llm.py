# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Unified Language Model Interface
# Description:  Unified implementation for all language model providers
# Role:         Provides a standardized interface to different LLM providers
# Usage:        Used for all language model interactions in the framework
# Author:       Muxi Framework Team
#
# The llm.py module provides a unified interface for language model interactions
# in the Muxi framework through the muxi-llm package. It defines:
#
# 1. LLM Class
#    - Concrete implementation using muxi-llm package
#    - Unified interface for all supported providers
#    - Provider-agnostic with "provider/model-name" format
#
# Typical usage pattern:
#
#   # Creating an LLM instance
#   model = LLM(model="openai/gpt-4o", api_key="sk-...")
#
#   # Using the model with standard interface
#   response = await model.chat([
#       {"role": "system", "content": "You are a helpful assistant"},
#       {"role": "user", "content": "Hello, world!"}
#   ])
#
#   # Generating embeddings
#   embedding = await model.embed("Text to embed")
#
# The LLM class uses the muxi-llm package to provide a consistent interface
# across all supported language model providers.
# =============================================================================

from typing import Any, Dict, List, Optional, Union

from muxi_llm import ChatCompletion, Embedding  # type: ignore
from muxi_llm.config import set_api_key as muxi_llm_set_api_key  # type: ignore
from loguru import logger


def set_llm_api_key(api_key: str, provider: str) -> None:
    """
    Set the API key for a specific provider in muxi-llm.

    This is a convenience function that wraps muxi_llm.config.set_api_key.
    Use this to configure API keys before creating LLM instances.

    Args:
        api_key: The API key to set
        provider: The provider to set the key for (e.g., "openai", "anthropic")
    """
    muxi_llm_set_api_key(api_key, provider)
    logger.debug(f"API key set for provider: {provider}")


class LLM:
    """
    Unified model implementation using muxi-llm.

    This class provides a standardized interface for all language model providers
    using the muxi-llm package, which supports multiple providers through a
    consistent API.
    """

    def __init__(
        self,
        model: str = "openai/gpt-4o",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize a model using muxi-llm.

        Args:
            model: The model to use in "provider/model-name" format (e.g., "openai/gpt-4o").
                This unified format works across all supported providers.
            api_key: API key for the provider. If provided, it will be set using
                muxi_llm.config.set_api_key for the appropriate provider.
            temperature: The temperature parameter for generation. Controls randomness
                where higher values produce more random outputs.
            max_tokens: Maximum tokens to generate in responses. If None, uses
                provider defaults.
            **kwargs: Additional parameters passed directly to the LLM.
        """
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.additional_params = kwargs

        # Store the provider from the model name for later use
        if "/" in model:
            self.provider = model.split("/")[0]
        else:
            self.provider = "openai"  # Default provider if not specified
            self.model_name = f"openai/{model}"  # Automatically prefix with openai/

        # If API key is provided, set it for the provider
        if api_key:
            set_llm_api_key(api_key, self.provider)

        logger.info(f"Initialized LLM with {self.model_name}")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stop: Optional[Union[str, List[str]]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate a chat completion using muxi-llm.

        Args:
            messages: A list of messages in the conversation.
            temperature: Controls randomness. Overrides the instance setting when provided.
            max_tokens: The maximum number of tokens to generate.
            top_p: An alternative to sampling with temperature, called nucleus sampling.
            frequency_penalty: Penalize new tokens based on their frequency.
            presence_penalty: Penalize new tokens based on their presence.
            stop: Sequences where the generation will stop.
            **kwargs: Additional provider-specific parameters.

        Returns:
            The generated text response as a string.
        """
        try:
            # Prepare parameters
            params = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.temperature,
            }

            # Add optional parameters if provided
            if max_tokens is not None:
                params["max_tokens"] = max_tokens
            elif self.max_tokens is not None:
                params["max_tokens"] = self.max_tokens

            if top_p is not None:
                params["top_p"] = top_p

            if frequency_penalty is not None:
                params["frequency_penalty"] = frequency_penalty

            if presence_penalty is not None:
                params["presence_penalty"] = presence_penalty

            if stop is not None:
                params["stop"] = stop

            # Add any additional kwargs
            params.update(kwargs)

            # Call ChatCompletion API
            response = await ChatCompletion.acreate(**params)

            # Extract content from response
            return response.choices[0].message["content"] or ""

        except Exception as e:
            logger.error(f"Error calling model {self.model_name}: {str(e)}")
            raise e

    async def embed(self, text: str, **kwargs: Any) -> List[float]:
        """
        Generate embeddings for the provided text.

        Args:
            text: The text to embed.
            **kwargs: Additional parameters.

        Returns:
            The embeddings as a list of floats.
        """
        try:
            # Default to text-embedding-3-small if no embedding model is specified
            if "model" not in kwargs:
                embedding_model = "openai/text-embedding-3-small"
            else:
                embedding_model = kwargs.pop("model")

            # Use the API key if provided
            embedding_params = kwargs.copy()
            if self.api_key:
                embedding_params["api_key"] = self.api_key

            response = await Embedding.acreate(
                model=embedding_model,
                input=text,
                **embedding_params
            )

            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise e

    async def generate_embeddings(self, texts: List[str], **kwargs: Any) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to generate embeddings for.
            **kwargs: Additional parameters.

        Returns:
            A list of embeddings, each as a list of floats.
        """
        try:
            # Default to text-embedding-3-small if no embedding model is specified
            if "model" not in kwargs:
                embedding_model = "openai/text-embedding-3-small"
            else:
                embedding_model = kwargs.pop("model")

            # Use the API key if provided
            embedding_params = kwargs.copy()
            if self.api_key:
                embedding_params["api_key"] = self.api_key

            response = await Embedding.acreate(
                model=embedding_model,
                input=texts,
                **embedding_params
            )

            # Extract embeddings from response
            return [item.embedding for item in response.data]

        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise e

    async def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Generate text from the model with a simple prompt.

        Args:
            prompt: The prompt to send to the model
            temperature: Optional temperature parameter (overrides model default)
            max_tokens: Optional maximum tokens to generate (overrides model default)
            **kwargs: Additional model-specific parameters

        Returns:
            The generated text as a string
        """
        # Wrap the prompt in a message and calls chat()
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(
            messages=messages, temperature=temperature, max_tokens=max_tokens, **kwargs
        )
