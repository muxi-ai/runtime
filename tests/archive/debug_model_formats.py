#!/usr/bin/env python3
"""
Debug script to test various model name formats with the MUXI runtime LLM class.
"""

import os
import sys
from pathlib import Path

# Add runtime directory to path for imports
runtime_dir = Path(__file__).parent.parent / "runtime"
sys.path.insert(0, str(runtime_dir))

from src.muxi.runtime.llm.llm import LLM  # noqa: E402


def test_model_formats():
    """Test different model name formats to see what works."""

    print("=" * 80)
    print("MODEL FORMAT TESTING")
    print("=" * 80)

    # Test cases for different formats
    test_cases = [
        # OpenAI formats
        ("openai/gpt-4", "OpenAI with slash"),
        ("gpt-4", "OpenAI without prefix"),

        # Anthropic formats
        ("anthropic/claude-3-opus-20240229", "Anthropic with slash"),
        ("claude-3-opus-20240229", "Anthropic without prefix"),

        # Ollama formats
        ("ollama/llama2", "Ollama with slash"),
        ("llama2", "Ollama without prefix"),
    ]

    results = []

    for model_name, description in test_cases:
        print(f"\nTesting: {model_name} ({description})")
        print("-" * 60)

        # Try creating model with LLM class
        try:
            # Test with OpenAI key for OpenAI models
            if "gpt" in model_name or "openai" in model_name:
                api_key = os.getenv("OPENAI_API_KEY") or "test-key"
            elif "claude" in model_name or "anthropic" in model_name:
                api_key = os.getenv("ANTHROPIC_API_KEY") or "test-key"
            else:
                api_key = "test-key"

            model = LLM(
                model=model_name,
                api_key=api_key,
                temperature=0.7,
                max_tokens=100
            )
            print("✅ SUCCESS with LLM class")
            print(f"   Model: {model.model}")
            print(f"   Provider: {getattr(model, 'provider', 'unknown')}")
            results.append((model_name, "LLM", "SUCCESS", model.model))
        except Exception as e:
            print(f"❌ FAILED with LLM class: {e}")
            results.append((model_name, "LLM", "FAILED", str(e)))

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY OF RESULTS")
    print("=" * 80)
    print(f"{'Model Name':<40} {'Method':<20} {'Result':<10} {'Details':<30}")
    print("-" * 100)
    for model_name, method, result, details in results:
        print(f"{model_name:<40} {method:<20} {result:<10} {details:<30}")

    # Check environment variables
    print("\n" + "=" * 80)
    print("ENVIRONMENT VARIABLES")
    print("=" * 80)
    env_vars = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_HOST"]
    for var in env_vars:
        value = os.getenv(var)
        if value:
            print(f"{var}: {'*' * 10} (set)")
        else:
            print(f"{var}: NOT SET")


def test_model_creation_with_config():
    """Test model creation with different configuration approaches."""

    print("\n" + "=" * 80)
    print("TESTING MODEL CREATION WITH CONFIG")
    print("=" * 80)

    # Test 1: Using LLM directly
    print("\nTest 1: Direct LLM creation")
    try:
        model = LLM(
            model="openai/gpt-4",
            api_key=os.getenv("OPENAI_API_KEY") or "test-key",
            temperature=0.7,
            max_tokens=100
        )
        print("✅ SUCCESS: Created LLM model directly")
        print(f"   Model: {model.model}")
        print(f"   Provider: {getattr(model, 'provider', 'unknown')}")
    except Exception as e:
        print(f"❌ FAILED: {e}")

    # Test 2: Using Agent with LLM
    print("\nTest 2: Agent with LLM model")
    try:
        from src.muxi.runtime.agent import Agent

        model = LLM(
            model="gpt-4",
            api_key=os.getenv("OPENAI_API_KEY") or "test-key",
            temperature=0.7,
            max_tokens=100
        )

        # Create a mock overlord for the test
        class MockOverlord:
            def __init__(self):
                self.request_timeout = 60

        mock_overlord = MockOverlord()

        agent = Agent(
            agent_id="test-agent",
            model=model,
            overlord=mock_overlord,
            system_message="Test agent"
        )
        print("✅ SUCCESS: Created agent with LLM model")
        print(f"   Agent model type: {type(agent.model).__name__}")
    except Exception as e:
        print(f"❌ FAILED: {e}")


if __name__ == "__main__":
    test_model_formats()
    test_model_creation_with_config()
