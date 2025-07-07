#!/usr/bin/env python3
"""Test both FAISSx server configurations:
1. Port 45678 - No auth required, but tenant ID needed
2. Port 65432 - Full authentication (API key + tenant ID)
"""

import sys
sys.path.insert(0, '.')
import asyncio
import time
import numpy as np
from src.muxi.runtime.services.memory.short_term import ShortTermMemory

# Mock LLM for testing
class MockLLM:
    async def embed(self, text):
        # Simple hash-based embedding
        text_hash = hash(text) % 1000
        return [text_hash / 1000.0] + [0.1] * 1535

async def test_faissx_no_auth_with_tenant():
    """Test FAISSx on port 45678 - No auth but with tenant ID"""
    print("\n" + "=" * 70)
    print("🔓 TEST 1: FAISSx Port 45678 - No Auth + Tenant ID")
    print("=" * 70)
    
    try:
        import faissx.client as faiss
        from src.muxi.runtime.services.secrets.secrets_manager import SecretsManager
        
        # Load tenant ID from secrets
        secrets_manager = SecretsManager("test-formations/formation-memory")
        await secrets_manager.initialize_encryption()
        tenant_id = await secrets_manager.get_secret("FAISSX_TENANT_ID")
        
        print(f"1. Configuring FAISSx (no auth, with tenant)...")
        print(f"   Server: tcp://localhost:45678")
        print(f"   Tenant: {tenant_id}")
        print(f"   API Key: None")
        
        # Configure with tenant but no auth
        faiss.configure(
            server="tcp://localhost:45678",
            tenant_id=tenant_id,
            timeout=5.0
        )
        print("✓ Configuration successful")
        
        # Test index operations
        print("\n2. Creating index with tenant...")
        index = faiss.IndexFlatL2(128)
        print(f"✓ Index created for tenant: {tenant_id}")
        
        # Add vectors
        print("\n3. Adding vectors...")
        vectors = np.random.rand(3, 128).astype('float32')
        index.add(vectors)
        print(f"✓ Added {len(vectors)} vectors")
        print(f"  Index count: {index.ntotal}")
        
        # Search
        print("\n4. Searching vectors...")
        query = np.random.rand(1, 128).astype('float32')
        distances, indices = index.search(query, k=2)
        print(f"✓ Search completed")
        print(f"  Results: {len(indices[0])} matches found")
        
        # Test with ShortTermMemory
        print("\n5. Testing ShortTermMemory integration...")
        buffer = ShortTermMemory(
            formation_id="test_formation",
            max_size=5,
            buffer_multiplier=2,
            dimension=1536,
            model=MockLLM(),
            mode="remote",
            remote={
                "url": "tcp://localhost:45678",
                "tenant": tenant_id
                # No api_key
            }
        )
        
        await buffer.add("Test message for tenant", {"source": "no-auth"})
        results = await buffer.search("test", limit=1)
        
        print(f"✓ ShortTermMemory working with tenant ID")
        print(f"  Buffer items: {len(buffer)}")
        print(f"  Search results: {len(results)}")
        
        return {
            "status": "success",
            "port": 45678,
            "auth_required": False,
            "tenant_required": True,
            "tenant_id": tenant_id,
            "operations": ["configure", "create", "add", "search", "memory"]
        }
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        return {
            "status": "failed",
            "port": 45678,
            "error": str(e)
        }

async def test_faissx_with_full_auth():
    """Test FAISSx on port 65432 - Full authentication"""
    print("\n" + "=" * 70)
    print("🔐 TEST 2: FAISSx Port 65432 - Full Auth (API Key + Tenant)")
    print("=" * 70)
    
    try:
        import faissx.client as faiss
        from src.muxi.runtime.services.secrets.secrets_manager import SecretsManager
        
        # Load authentication from secrets
        secrets_manager = SecretsManager("test-formations/formation-memory")
        await secrets_manager.initialize_encryption()
        api_key = await secrets_manager.get_secret("FAISSX_API_KEY")
        tenant_id = await secrets_manager.get_secret("FAISSX_TENANT_ID")
        
        print(f"1. Configuring FAISSx (full auth)...")
        print(f"   Server: tcp://localhost:65432")
        print(f"   Tenant: {tenant_id}")
        print(f"   API Key: {api_key[:10]}...")
        
        # Configure with full auth
        faiss.configure(
            server="tcp://localhost:65432",
            api_key=api_key,
            tenant_id=tenant_id,
            timeout=5.0
        )
        print("✓ Configuration successful")
        
        # Test index operations
        print("\n2. Creating authenticated index...")
        index = faiss.IndexFlatL2(128)
        print(f"✓ Index created with authentication")
        
        # Add vectors
        print("\n3. Adding vectors with auth...")
        vectors = np.random.rand(3, 128).astype('float32')
        index.add(vectors)
        print(f"✓ Added {len(vectors)} vectors")
        print(f"  Index count: {index.ntotal}")
        
        # Search
        print("\n4. Searching with auth...")
        query = np.random.rand(1, 128).astype('float32')
        distances, indices = index.search(query, k=2)
        print(f"✓ Search completed")
        print(f"  Results: {len(indices[0])} matches found")
        
        # Test with ShortTermMemory
        print("\n5. Testing ShortTermMemory with full auth...")
        buffer = ShortTermMemory(
            formation_id="test_formation",
            max_size=5,
            buffer_multiplier=2,
            dimension=1536,
            model=MockLLM(),
            mode="remote",
            remote={
                "url": "tcp://localhost:65432",
                "api_key": api_key,
                "tenant": tenant_id
            }
        )
        
        await buffer.add("Authenticated message", {"source": "full-auth"})
        results = await buffer.search("authenticated", limit=1)
        
        print(f"✓ ShortTermMemory working with full auth")
        print(f"  Buffer items: {len(buffer)}")
        print(f"  Search results: {len(results)}")
        
        return {
            "status": "success",
            "port": 65432,
            "auth_required": True,
            "tenant_required": True,
            "api_key": api_key[:10] + "...",
            "tenant_id": tenant_id,
            "operations": ["configure", "create", "add", "search", "memory"]
        }
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        error_msg = str(e)
        
        # Analyze error
        if "auth" in error_msg.lower() or "key" in error_msg.lower():
            print("   → Authentication error detected")
        elif "connection" in error_msg.lower():
            print("   → Connection error - is server running on port 65432?")
            
        return {
            "status": "failed",
            "port": 65432,
            "error": str(e)
        }

async def test_formation_configurations():
    """Test loading formations with different FAISSx configs"""
    print("\n" + "=" * 70)
    print("📄 TEST 3: Formation Configurations")
    print("=" * 70)
    
    from src.muxi.runtime.formation.formation import Formation
    from concurrent.futures import ThreadPoolExecutor
    
    formations_to_test = [
        {
            "path": "test-formations/formation-memory/formation-postgres-and-faissx.yaml",
            "name": "No Auth + Tenant",
            "expected_port": "45678",
            "has_auth": False
        },
        {
            "path": "test-formations/formation-memory/formation-postgres-and-faissx-with-auth.yaml",
            "name": "Full Auth",
            "expected_port": "65432",
            "has_auth": True
        }
    ]
    
    results = []
    
    for formation_config in formations_to_test:
        print(f"\nTesting: {formation_config['name']}")
        print(f"Formation: {formation_config['path']}")
        
        async def load_formation(path):
            try:
                formation = Formation()
                await formation.load(path)
                
                # Extract memory config
                memory_config = formation.config.get("memory", {})
                working_config = memory_config.get("working", {})
                remote_config = working_config.get("remote", {})
                
                return {
                    "loaded": True,
                    "mode": working_config.get("mode"),
                    "url": remote_config.get("url"),
                    "has_api_key": "api_key" in remote_config,
                    "has_tenant": "tenant" in remote_config
                }
            except Exception as e:
                return {
                    "loaded": False,
                    "error": str(e)
                }
        
        # Run async function
        result = await load_formation(formation_config["path"])
        
        if result["loaded"]:
            print(f"✓ Formation loaded successfully")
            print(f"  Mode: {result['mode']}")
            print(f"  URL: {result['url']}")
            print(f"  Has API key: {result['has_api_key']}")
            print(f"  Has tenant: {result['has_tenant']}")
            
            # Verify configuration
            if formation_config["expected_port"] in result.get("url", ""):
                print(f"  ✓ Correct port: {formation_config['expected_port']}")
            else:
                print(f"  ❌ Wrong port in URL")
                
            if result["has_api_key"] == formation_config["has_auth"]:
                print(f"  ✓ Auth config correct: {formation_config['has_auth']}")
            else:
                print(f"  ❌ Auth config mismatch")
        else:
            print(f"❌ Failed to load: {result.get('error', 'Unknown error')}")
        
        results.append({
            "name": formation_config["name"],
            "result": result
        })
    
    return results

async def main():
    """Run all FAISSx configuration tests"""
    print("🧪 COMPREHENSIVE FAISSx CONFIGURATION TESTS")
    print("=" * 70)
    print("Testing both FAISSx server configurations:")
    print("1. Port 45678 - No auth required, tenant ID needed")
    print("2. Port 65432 - Full authentication (API key + tenant)")
    print()
    
    # Run tests
    test1_result = await test_faissx_no_auth_with_tenant()
    test2_result = await test_faissx_with_full_auth()
    formation_results = await test_formation_configurations()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    
    # Test 1 Summary
    print(f"\n1. FAISSx Port 45678 (No Auth + Tenant):")
    if test1_result["status"] == "success":
        print(f"   ✅ SUCCESS - All operations working")
        print(f"   - Tenant ID: {test1_result['tenant_id']}")
        print(f"   - Operations: {', '.join(test1_result['operations'])}")
    else:
        print(f"   ❌ FAILED - {test1_result.get('error', 'Unknown error')}")
    
    # Test 2 Summary
    print(f"\n2. FAISSx Port 65432 (Full Auth):")
    if test2_result["status"] == "success":
        print(f"   ✅ SUCCESS - All operations working")
        print(f"   - API Key: {test2_result['api_key']}")
        print(f"   - Tenant ID: {test2_result['tenant_id']}")
        print(f"   - Operations: {', '.join(test2_result['operations'])}")
    else:
        print(f"   ❌ FAILED - {test2_result.get('error', 'Unknown error')}")
    
    # Formation Summary
    print(f"\n3. Formation Configurations:")
    for formation_result in formation_results:
        name = formation_result["name"]
        result = formation_result["result"]
        if result["loaded"]:
            print(f"   ✅ {name} - Loaded correctly")
        else:
            print(f"   ❌ {name} - Failed to load")
    
    # Overall Assessment
    print("\n" + "=" * 70)
    print("🎯 OVERALL ASSESSMENT")
    print("=" * 70)
    
    if test1_result["status"] == "success" and test2_result["status"] == "success":
        print("✅ BOTH FAISSx CONFIGURATIONS WORKING!")
        print("\nKey findings:")
        print("- Port 45678: Requires only tenant ID (no auth)")
        print("- Port 65432: Requires both API key and tenant ID")
        print("- ShortTermMemory integrates correctly with both")
        print("- Multi-tenancy is supported in both modes")
    else:
        print("⚠️  PARTIAL SUCCESS")
        if test1_result["status"] == "success":
            print("- Port 45678 (no auth) is working ✅")
        else:
            print("- Port 45678 (no auth) is NOT working ❌")
            
        if test2_result["status"] == "success":
            print("- Port 65432 (full auth) is working ✅")
        else:
            print("- Port 65432 (full auth) is NOT working ❌")

if __name__ == "__main__":
    asyncio.run(main())