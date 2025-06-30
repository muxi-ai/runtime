#!/usr/bin/env python3
"""Test that ShortTermMemory now has built-in embedding normalization"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.services.memory.short_term import ShortTermMemory
from src.muxi.runtime.services.secrets.secrets_manager import SecretsManager
from src.muxi.runtime.services.llm.llm import LLM

async def test_builtin_normalization():
    """Test that developers get good results without any special wrapper"""
    print("\n=== Testing Built-in Embedding Normalization ===")
    
    # Load secrets
    secrets_manager = SecretsManager("test-formations/formation-memory")
    await secrets_manager.initialize_encryption()
    openai_api_key = await secrets_manager.get_secret("OPENAI_API_KEY")
    
    # Create a REGULAR LLM - no special wrapper needed!
    llm = LLM(
        model="openai/text-embedding-3-small",
        api_key=openai_api_key
    )
    
    print("Using standard LLM without any normalization wrapper")
    
    # Create buffer - it will normalize automatically
    buffer = ShortTermMemory(
        formation_id="test_formation",
        max_size=10,
        buffer_multiplier=2,
        dimension=1536,
        model=llm,
        mode="local"  # Using local for simplicity
    )
    
    # Add distinct content
    print("\nAdding test content...")
    await buffer.add("I love Python programming and machine learning", {"user": "alice"})
    await buffer.add("JavaScript and React are great for web development", {"user": "bob"})
    await buffer.add("Rust provides memory safety for systems programming", {"user": "charlie"})
    
    # Test searches - should get good relevance without any wrapper
    print("\nTesting searches with built-in normalization...")
    
    # Search for Python content
    python_results = await buffer.search("Python machine learning", limit=1)
    python_user = python_results[0].get('metadata', {}).get('user') if python_results else None
    print(f"Python search returned: {python_user} (expected: alice)")
    
    # Search for JavaScript content  
    js_results = await buffer.search("JavaScript React web", limit=1)
    js_user = js_results[0].get('metadata', {}).get('user') if js_results else None
    print(f"JavaScript search returned: {js_user} (expected: bob)")
    
    # Search for Rust content
    rust_results = await buffer.search("Rust memory safety systems", limit=1)
    rust_user = rust_results[0].get('metadata', {}).get('user') if rust_results else None
    print(f"Rust search returned: {rust_user} (expected: charlie)")
    
    # Calculate success
    correct = sum([
        python_user == "alice",
        js_user == "bob", 
        rust_user == "charlie"
    ])
    
    print(f"\n✓ Built-in normalization results: {correct}/3 correct")
    print(f"{'✅ SUCCESS' if correct == 3 else '⚠️  PARTIAL'}: Developers can use ShortTermMemory directly!")
    
    return correct == 3

async def main():
    """Run built-in normalization test"""
    print("🚀 Testing ShortTermMemory Built-in Normalization")
    print("=" * 60)
    print("Goal: Developers should get good results without any wrapper")
    print("=" * 60)
    
    success = await test_builtin_normalization()
    
    print("\n" + "=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    
    if success:
        print("\n✅ Built-in normalization is working!")
        print("   - Developers can use any LLM directly")
        print("   - No special wrapper or configuration needed")
        print("   - ShortTermMemory handles normalization automatically")
        print("   - Vector search achieves good relevance out of the box")
    else:
        print("\n⚠️  Built-in normalization needs improvement")
    
    print("\n💡 What changed:")
    print("   1. ShortTermMemory now normalizes embeddings before storing")
    print("   2. Query embeddings are normalized before searching")
    print("   3. Handles different LLM response formats automatically")
    print("   4. Works with any embedding model (OpenAI, Cohere, etc.)")

if __name__ == "__main__":
    asyncio.run(main())