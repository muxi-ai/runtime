"""
Test Enhanced LLM Implementation

This module contains tests for the enhanced LLM class with OneLLM integration,
error handling, retry mechanisms, and circuit breakers.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

import pytest

# Add current directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from runtime.muxi.runtime.llm import (
    LLM, LLMError, LLMErrorType, get_cache_stats, get_retry_stats,
    get_circuit_breaker_stats, clear_llm_cache, set_cache_ttl, reset_all_stats,
    AuthenticationError, RateLimitError
)


class TestEnhancedLLM(unittest.TestCase):
    """Test suite for enhanced LLM implementation."""

    def setup_method(self):
        """Setup for each test method."""
        # Reset all stats and caches before each test
        reset_all_stats()

    @pytest.mark.asyncio
    async def test_llm_initialization(self):
        """Test LLM initialization with various parameters."""
        # Test basic initialization
        llm = LLM(model="openai/gpt-4o")
        self.assertEqual(llm.model_name, "openai/gpt-4o")
        self.assertEqual(llm.provider, "openai")
        self.assertEqual(llm.model, "gpt-4o")
        self.assertEqual(llm.temperature, 0.7)
        self.assertEqual(llm.timeout, 30.0)
        self.assertEqual(llm.max_retries, 3)
        self.assertEqual(llm.enable_circuit_breaker, True)

        # Test initialization with custom parameters
        llm2 = LLM(
            model="anthropic/claude-3-sonnet",
            temperature=0.5,
            max_tokens=1000,
            timeout=60.0,
            max_retries=5,
            enable_circuit_breaker=False
        )
        self.assertEqual(llm2.model_name, "anthropic/claude-3-sonnet")
        self.assertEqual(llm2.provider, "anthropic")
        self.assertEqual(llm2.model, "claude-3-sonnet")
        self.assertEqual(llm2.temperature, 0.5)
        self.assertEqual(llm2.max_tokens, 1000)
        self.assertEqual(llm2.timeout, 60.0)
        self.assertEqual(llm2.max_retries, 5)
        self.assertEqual(llm2.enable_circuit_breaker, False)

        # Test model without provider (should default to openai)
        llm3 = LLM(model="gpt-3.5-turbo")
        self.assertEqual(llm3.model_name, "openai/gpt-3.5-turbo")
        self.assertEqual(llm3.provider, "openai")
        self.assertEqual(llm3.model, "gpt-3.5-turbo")

    @pytest.mark.asyncio
    async def test_chat_functionality(self):
        """Test chat functionality with mocking."""
        llm = LLM(model="openai/gpt-4o")

        # Mock the ChatCompletion.create method
        with patch('muxi.runtime.llm.ChatCompletion.create') as mock_create:
            mock_create.return_value = {
                "choices": [{"message": {"content": "Hello! How can I help you?"}}]
            }

            messages = [
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "Hello, world!"}
            ]

            response = await llm.chat(messages)
            self.assertEqual(response, "Hello! How can I help you?")

            # Verify the mock was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args[1]
            self.assertEqual(call_args["model"], "gpt-4o")
            self.assertEqual(call_args["messages"], messages)
            self.assertEqual(call_args["temperature"], 0.7)

    @pytest.mark.asyncio
    async def test_embed_functionality(self):
        """Test embedding functionality with mocking."""
        llm = LLM(model="openai/gpt-4o")

        # Mock the Embedding.create method
        with patch('muxi.runtime.llm.Embedding.create') as mock_create:
            mock_create.return_value = {
                "data": [{"embedding": [0.1, 0.2, 0.3]}]
            }

            response = await llm.embed("Hello, world!")
            self.assertEqual(response, [0.1, 0.2, 0.3])

            # Verify the mock was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args[1]
            self.assertEqual(call_args["model"], "text-embedding-3-small")
            self.assertEqual(call_args["input"], "Hello, world!")

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch(self):
        """Test batch embedding functionality."""
        llm = LLM(model="openai/gpt-4o")

        # Mock the Embedding.create method
        with patch('muxi.runtime.llm.Embedding.create') as mock_create:
            mock_create.return_value = {
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]}
                ]
            }

            texts = ["Hello", "World"]
            response = await llm.generate_embeddings(texts)
            self.assertEqual(response, [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

            # Verify the mock was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args[1]
            self.assertEqual(call_args["input"], texts)

    @pytest.mark.asyncio
    async def test_generate_text_functionality(self):
        """Test generate_text method."""
        llm = LLM(model="openai/gpt-4o")

        # Mock the ChatCompletion.create method
        with patch('muxi.runtime.llm.ChatCompletion.create') as mock_create:
            mock_create.return_value = {
                "choices": [{"message": {"content": "Generated response"}}]
            }

            response = await llm.generate_text("Generate something interesting")
            self.assertEqual(response, "Generated response")

            # Verify the mock was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args[1]
            expected_messages = [
                {"role": "user", "content": "Generate something interesting"}
            ]
            self.assertEqual(call_args["messages"], expected_messages)

    @pytest.mark.asyncio
    async def test_caching_functionality(self):
        """Test response caching."""
        llm = LLM(model="openai/gpt-4o")

        # Mock the ChatCompletion.create method
        with patch('muxi.runtime.llm.ChatCompletion.create') as mock_create:
            mock_create.return_value = {
                "choices": [{"message": {"content": "Cached response"}}]
            }

            messages = [{"role": "user", "content": "Test caching"}]

            # First call should hit the API
            response1 = await llm.chat(messages)
            self.assertEqual(response1, "Cached response")
            self.assertEqual(mock_create.call_count, 1)

            # Second call with same parameters should use cache
            response2 = await llm.chat(messages)
            self.assertEqual(response2, "Cached response")
            self.assertEqual(mock_create.call_count, 1)  # No additional API call

            # Verify cache stats
            stats = get_cache_stats()
            self.assertGreater(stats["cache_size"], 0)

    @pytest.mark.asyncio
    async def test_cache_management(self):
        """Test cache management functions."""
        # Test cache TTL setting
        set_cache_ttl(600)
        stats = get_cache_stats()
        self.assertEqual(stats["cache_ttl"], 600)

        # Test cache clearing
        clear_llm_cache()
        stats = get_cache_stats()
        self.assertEqual(stats["cache_size"], 0)

    @pytest.mark.asyncio
    async def test_error_classification(self):
        """Test error classification and handling."""
        llm = LLM(model="openai/gpt-4o")

        # Test authentication error
        with patch('muxi.runtime.llm.ChatCompletion.create') as mock_create:
            mock_create.side_effect = AuthenticationError("Invalid API key")

            with self.assertRaises(LLMError) as exc_info:
                await llm.chat([{"role": "user", "content": "test"}])

            self.assertEqual(exc_info.exception.error_type, LLMErrorType.AUTHENTICATION)
            self.assertFalse(exc_info.exception.retryable)

    @pytest.mark.asyncio
    async def test_retry_mechanism(self):
        """Test retry mechanism with retryable errors."""
        llm = LLM(model="openai/gpt-4o", max_retries=2)

        # Mock the ChatCompletion.create method to fail twice then succeed
        with patch('muxi.runtime.llm.ChatCompletion.create') as mock_create:
            mock_create.side_effect = [
                RateLimitError("Rate limit"),
                RateLimitError("Rate limit"),
                {"choices": [{"message": {"content": "Success after retries"}}]}
            ]

            response = await llm.chat([{"role": "user", "content": "test"}])
            self.assertEqual(response, "Success after retries")
            self.assertEqual(mock_create.call_count, 3)  # Original + 2 retries

            # Check retry stats
            stats = get_retry_stats()
            self.assertEqual(stats["total_requests"], 1)
            self.assertEqual(stats["successful_requests"], 1)
            self.assertEqual(stats["retry_attempts"], 2)

    def test_utility_functions(self):
        """Test utility functions for monitoring."""
        # Reset stats
        reset_all_stats()

        # Test retry stats
        retry_stats = get_retry_stats()
        self.assertEqual(retry_stats["total_requests"], 0)
        self.assertEqual(retry_stats["successful_requests"], 0)
        self.assertEqual(retry_stats["failed_requests"], 0)

        # Test circuit breaker stats
        cb_stats = get_circuit_breaker_stats()
        self.assertIsInstance(cb_stats, dict)

        # Test cache stats
        cache_stats = get_cache_stats()
        self.assertIn("cache_size", cache_stats)
        self.assertIn("cache_ttl", cache_stats)

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test timeout handling."""
        llm = LLM(model="openai/gpt-4o", timeout=0.1)  # Very short timeout

        # Mock a slow response
        async def slow_response(**kwargs):
            await asyncio.sleep(0.2)  # Sleep longer than timeout
            return {"choices": [{"message": {"content": "Too slow"}}]}

        with patch('muxi.runtime.llm.ChatCompletion.create', side_effect=slow_response):
            with self.assertRaises(LLMError) as exc_info:
                await llm.chat([{"role": "user", "content": "test"}])

            self.assertEqual(exc_info.exception.error_type, LLMErrorType.TIMEOUT)
            self.assertTrue(exc_info.exception.retryable)

    def test_properties(self):
        """Test LLM properties."""
        llm = LLM(model="anthropic/claude-3-sonnet")

        self.assertEqual(llm.model, "claude-3-sonnet")
        self.assertEqual(llm.provider, "anthropic")
        self.assertEqual(llm.model_name, "anthropic/claude-3-sonnet")

        # Test model without provider
        llm2 = LLM(model="gpt-4")
        self.assertEqual(llm2.model, "gpt-4")
        self.assertEqual(llm2.provider, "openai")
        self.assertEqual(llm2.model_name, "openai/gpt-4")

    def test_multimodal_chat_with_files(self):
        """Test chat method with file attachments."""
        async def run_test():
            from runtime.muxi.runtime.llm import LLM

            llm = LLM(model="openai/gpt-4o")

            # Create a test file
            test_file = "test_image.txt"  # Simple text file for testing
            with open(test_file, "w") as f:
                f.write("This is test content for multimodal chat.")

            try:
                # Mock the OneLLM response
                with patch('runtime.muxi.runtime.llm.ChatCompletion.create') as mock_create:
                    mock_create.return_value = {
                        "choices": [{"message": {"content": "I can see the file content."}}]
                    }

                    messages = [{"role": "user", "content": "Please analyze this file."}]
                    response = await llm.chat(messages, files=[test_file])

                    self.assertEqual(response, "I can see the file content.")
                    mock_create.assert_called_once()

                    # Check that files were processed and included in the call
                    call_args = mock_create.call_args[1]
                    self.assertIn("files", call_args)
                    self.assertIsInstance(call_args["files"], list)
                    self.assertEqual(len(call_args["files"]), 1)

            finally:
                # Clean up test file
                if os.path.exists(test_file):
                    os.remove(test_file)

        asyncio.run(run_test())

    def test_multimodal_file_security_validation(self):
        """Test file security validation."""
        async def run_test():
            from runtime.muxi.runtime.llm import FileProcessor

            # Test with a normal file
            test_file = "normal_test.txt"
            with open(test_file, "w") as f:
                f.write("Normal content")

            try:
                is_valid = await FileProcessor.validate_file_security(test_file)
                self.assertTrue(is_valid)
            finally:
                if os.path.exists(test_file):
                    os.remove(test_file)

            # Test with non-existent file
            is_valid = await FileProcessor.validate_file_security("non_existent.txt")
            self.assertFalse(is_valid)

        asyncio.run(run_test())

    def test_multimodal_file_processing_error_handling(self):
        """Test error handling in file processing."""
        async def run_test():
            from runtime.muxi.runtime.llm import LLM

            llm = LLM(model="openai/gpt-4o")

            # Test with non-existent file
            messages = [{"role": "user", "content": "Analyze this file."}]

            with self.assertRaises(Exception):  # Should raise LLMError
                await llm.chat(messages, files=["non_existent_file.txt"])

        asyncio.run(run_test())

    def test_multimodal_cache_behavior_with_files(self):
        """Test that files are not cached for security."""
        async def run_test():
            from runtime.muxi.runtime.llm import LLM

            llm = LLM(model="openai/gpt-4o")

            # Create a test file
            test_file = "cache_test.txt"
            with open(test_file, "w") as f:
                f.write("Cache test content")

            try:
                messages = [{"role": "user", "content": "Analyze this file."}]

                with patch('runtime.muxi.runtime.llm.ChatCompletion.create') as mock_create:
                    mock_create.return_value = {
                        "choices": [{"message": {"content": "First response"}}]
                    }

                    # First call with file
                    response1 = await llm.chat(messages, files=[test_file])

                    # Second call with same file should not use cache
                    mock_create.return_value = {
                        "choices": [{"message": {"content": "Second response"}}]
                    }
                    response2 = await llm.chat(messages, files=[test_file])

                    # Both calls should have been made (no caching with files)
                    self.assertEqual(mock_create.call_count, 2)
                    self.assertEqual(response1, "First response")
                    self.assertEqual(response2, "Second response")

            finally:
                if os.path.exists(test_file):
                    os.remove(test_file)

        asyncio.run(run_test())

    def test_file_format_detection(self):
        """Test file format detection and MIME type mapping."""
        async def run_test():
            from runtime.muxi.runtime.llm import FileProcessor

            # Test text file
            text_file = "test.txt"
            with open(text_file, "w") as f:
                f.write("Test content")

            try:
                mime_type = FileProcessor._detect_mime_type(text_file)
                self.assertIn("text", mime_type.lower())

                onellm_type = FileProcessor._map_mime_to_onellm_type(mime_type)
                self.assertIsInstance(onellm_type, str)

            finally:
                if os.path.exists(text_file):
                    os.remove(text_file)

        asyncio.run(run_test())

    def test_multimodal_multiple_files(self):
        """Test processing multiple files at once."""
        async def run_test():
            from runtime.muxi.runtime.llm import LLM

            llm = LLM(model="openai/gpt-4o")

            # Create multiple test files
            files_to_create = ["file1.txt", "file2.txt"]
            for file_name in files_to_create:
                with open(file_name, "w") as f:
                    f.write(f"Content of {file_name}")

            try:
                with patch('runtime.muxi.runtime.llm.ChatCompletion.create') as mock_create:
                    mock_create.return_value = {
                        "choices": [{"message": {"content": "Analyzed multiple files"}}]
                    }

                    messages = [{"role": "user", "content": "Compare these files."}]
                    response = await llm.chat(messages, files=files_to_create)

                    self.assertEqual(response, "Analyzed multiple files")

                    # Check that both files were processed
                    call_args = mock_create.call_args[1]
                    self.assertIn("files", call_args)
                    self.assertEqual(len(call_args["files"]), 2)

            finally:
                for file_name in files_to_create:
                    if os.path.exists(file_name):
                        os.remove(file_name)

        asyncio.run(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
