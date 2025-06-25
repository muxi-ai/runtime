#!/usr/bin/env python3
"""Test remote FAISSx without authentication"""

import sys
sys.path.insert(0, '.')
import asyncio
import time
import numpy as np

async def test_faissx_no_auth():
    """Test connection to FAISSx server without authentication"""
    print("🔓 Testing FAISSx WITHOUT Authentication")
    print("=" * 60)
    
    try:
        import faissx.client as faiss
        
        print("1. Configuring FAISSx connection (no auth)...")
        print(f"   Server: tcp://localhost:65432")
        print(f"   No API key provided")
        
        # Configure without authentication
        faiss.configure(
            server="tcp://localhost:65432",
            timeout=5.0
        )
        print("✓ faiss.configure() without auth completed")
        
        print("\n2. Creating index without auth...")
        start_time = time.time()
        index = faiss.IndexFlatL2(128)  # Small dimension for testing
        end_time = time.time()
        
        print(f"✓ Index created in {end_time - start_time:.3f}s")
        print(f"  Index type: {type(index)}")
        print(f"  Initial count: {index.ntotal}")
        
        print("\n3. Testing add operation without auth...")
        test_vectors = np.random.rand(5, 128).astype('float32')
        add_start = time.time()
        index.add(test_vectors)
        add_end = time.time()
        
        print(f"✓ Added {len(test_vectors)} vectors in {add_end - add_start:.3f}s")
        print(f"  Index count: {index.ntotal}")
        
        print("\n4. Testing search operation without auth...")
        query = np.random.rand(1, 128).astype('float32')
        search_start = time.time()
        distances, indices = index.search(query, k=3)
        search_end = time.time()
        
        print(f"✓ Search completed in {search_end - search_start:.3f}s")
        print(f"  Found {len(indices[0])} results")
        print(f"  Distances: {distances[0]}")
        
        print("\n✅ SUCCESS: FAISSx works WITHOUT authentication!")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ FAISSx without auth failed: {error_msg}")
        
        # Check if it's an auth error
        if "auth" in error_msg.lower() or "key" in error_msg.lower():
            print("\n⚠️  Server appears to REQUIRE authentication")
            print("   This means the server is configured with auth enabled")
        else:
            print("\n⚠️  Connection/server error (not auth-related)")
            
        return False

async def test_shorttermemory_no_auth():
    """Test ShortTermMemory with FAISSx without auth"""
    print("\n\n🧠 Testing ShortTermMemory with FAISSx (no auth)")
    print("=" * 60)
    
    try:
        # Mock LLM
        class MockLLM:
            async def embed(self, text):
                return [0.1] * 1536
        
        from src.muxi.runtime.services.memory.short_term import ShortTermMemory
        
        print("1. Creating ShortTermMemory with remote (no auth)...")
        buffer = ShortTermMemory(
            max_size=5,
            buffer_multiplier=2,
            dimension=1536,
            model=MockLLM(),
            mode="remote",
            remote={
                "url": "tcp://localhost:65432"
                # No api_key or tenant
            }
        )
        
        print(f"✓ ShortTermMemory created")
        print(f"  Mode: {buffer.mode}")
        print(f"  Remote URL: {buffer.remote.get('url')}")
        print(f"  Has API key: {'api_key' in buffer.remote}")
        
        print("\n2. Testing add operation...")
        await buffer.add("Test message without auth", {"test": True})
        await buffer.add("Another message", {"test": True})
        
        print(f"✓ Added 2 messages to buffer")
        
        print("\n3. Testing search operation...")
        results = await buffer.search("test", limit=2)
        
        print(f"✓ Search returned {len(results)} results")
        if results:
            print(f"  First result: {results[0]['text'][:50]}...")
            
        print("\n✅ SUCCESS: ShortTermMemory works with FAISSx (no auth)!")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ ShortTermMemory without auth failed: {error_msg}")
        
        if "auth" in error_msg.lower() or "key" in error_msg.lower():
            print("\n⚠️  FAISSx server requires authentication")
        
        return False

async def main():
    """Run all no-auth tests"""
    print("🔓 FAISSx NO-AUTHENTICATION TEST")
    print("=" * 60)
    print("Testing if FAISSx server works WITHOUT authentication")
    print("Server: tcp://localhost:65432")
    print()
    
    # Run tests
    basic_ok = await test_faissx_no_auth()
    memory_ok = await test_shorttermemory_no_auth()
    
    # Summary
    print("\n\n" + "=" * 60)
    print("📋 NO-AUTH TEST SUMMARY")
    print("=" * 60)
    
    if basic_ok and memory_ok:
        print("✅ FAISSx server is running WITHOUT authentication!")
        print("   - Basic operations work without API key")
        print("   - ShortTermMemory integrates without auth")
        print("\n⚠️  NOTE: This may be a security risk in production!")
    elif not basic_ok and not memory_ok:
        print("❌ FAISSx server REQUIRES authentication")
        print("   - Cannot connect without API key")
        print("   - Server is properly secured")
        print("\n💡 To use this server, provide:")
        print("   - api_key in remote configuration")
        print("   - tenant_id if multi-tenancy is enabled")
    else:
        print("⚠️  PARTIAL SUCCESS")
        print(f"   Basic test: {'✅ PASS' if basic_ok else '❌ FAIL'}")
        print(f"   Memory test: {'✅ PASS' if memory_ok else '❌ FAIL'}")

if __name__ == "__main__":
    asyncio.run(main())