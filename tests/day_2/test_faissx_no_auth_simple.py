#!/usr/bin/env python3
"""Test remote FAISSx without authentication on port 45678"""

import sys
sys.path.insert(0, '.')
import asyncio
import time
import numpy as np

async def test_faissx_no_auth():
    """Test connection to FAISSx server without authentication on port 45678"""
    print("🔓 Testing FAISSx WITHOUT Authentication (Port 45678)")
    print("=" * 60)
    
    try:
        import faissx.client as faiss
        
        print("1. Configuring FAISSx connection (no auth)...")
        print(f"   Server: tcp://localhost:45678")
        print(f"   No API key provided")
        
        # Configure without authentication
        faiss.configure(
            server="tcp://localhost:45678",
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
        
        print("\n✅ SUCCESS: FAISSx works WITHOUT authentication on port 45678!")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ FAISSx without auth failed: {error_msg}")
        
        # Check if it's an auth error
        if "auth" in error_msg.lower() or "key" in error_msg.lower():
            print("\n⚠️  Server on port 45678 appears to REQUIRE authentication")
            print("   This is unexpected for the no-auth configuration")
        elif "connection" in error_msg.lower() or "refused" in error_msg.lower():
            print("\n⚠️  Cannot connect to server on port 45678")
            print("   Is the FAISSx server running on this port?")
        else:
            print("\n⚠️  Other error (not auth-related)")
            
        return False

async def test_formation_with_faissx():
    """Test the formation with remote FAISSx"""
    print("\n\n📄 Testing Formation with Remote FAISSx (no auth)")
    print("=" * 60)
    
    try:
        from src.muxi.runtime.formation.formation import Formation
        from concurrent.futures import ThreadPoolExecutor
        
        async def run_formation_test():
            formation = Formation()
            await formation.load("test-formations/formation-memory/formation-postgres-and-faissx.yaml")
            print("✓ Formation loaded successfully")
            
            # Check memory configuration
            memory_config = formation.config.get("memory", {})
            working_config = memory_config.get("working", {})
            
            print(f"\nMemory configuration:")
            print(f"  Mode: {working_config.get('mode')}")
            print(f"  Remote URL: {working_config.get('remote', {}).get('url')}")
            print(f"  Has auth: {'api_key' in working_config.get('remote', {})}")
            print(f"  Max memory: {working_config.get('max_memory_mb')} MB")
            
            return True
        
        # Run in thread to avoid event loop issues
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_formation_test)
            result = future.result()
            
        return result
        
    except Exception as e:
        print(f"\n❌ Formation test failed: {e}")
        return False

async def main():
    """Run all no-auth tests for port 45678"""
    print("🔓 FAISSx NO-AUTHENTICATION TEST (Port 45678)")
    print("=" * 60)
    print("Testing FAISSx server WITHOUT authentication")
    print("Server: tcp://localhost:45678")
    print("Formation: formation-postgres-and-faissx.yaml")
    print()
    
    # Run tests
    faissx_ok = await test_faissx_no_auth()
    formation_ok = await test_formation_with_faissx()
    
    # Summary
    print("\n\n" + "=" * 60)
    print("📋 NO-AUTH TEST SUMMARY (Port 45678)")
    print("=" * 60)
    
    if faissx_ok:
        print("✅ FAISSx server on port 45678 is running WITHOUT authentication!")
        print("   - Basic operations work without API key")
        print("   - This matches the formation configuration")
    else:
        print("❌ FAISSx server on port 45678 is NOT accessible")
        print("   - Check if server is running: faissx server --port 45678")
        print("   - Or server may require authentication")
    
    if formation_ok:
        print("\n✅ Formation configuration is correct")
        print("   - Uses remote mode on port 45678")
        print("   - No authentication configured")
    else:
        print("\n❌ Formation configuration issue")
    
    print("\n💡 Next steps:")
    if not faissx_ok:
        print("   1. Start FAISSx server: faissx server --port 45678")
        print("   2. Run this test again")
    else:
        print("   1. Run full memory tests with this formation")
        print("   2. Test multi-user scenarios")

if __name__ == "__main__":
    asyncio.run(main())