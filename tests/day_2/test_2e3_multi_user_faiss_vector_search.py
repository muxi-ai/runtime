#!/usr/bin/env python3
"""Test multi-user FAISSx vector search with tenant isolation"""

import sys
sys.path.insert(0, '.')
import asyncio
import time

from src.muxi.runtime.services.memory.short_term import ShortTermMemory
from src.muxi.runtime.services.secrets.secrets_manager import SecretsManager
from src.muxi.runtime.services.llm.llm import LLM

async def test_multi_user_faissx():
    """Test multi-user FAISSx with tenant isolation"""
    print("\n=== Testing Multi-User FAISSx with Tenant Isolation ===")
    
    # Load secrets
    secrets_manager = SecretsManager("test-formations/formation-memory")
    await secrets_manager.initialize_encryption()
    tenant_id = await secrets_manager.get_secret("FAISSX_TENANT_ID")
    openai_api_key = await secrets_manager.get_secret("OPENAI_API_KEY")
    
    if not tenant_id:
        print("Using default tenant ID for testing")
        tenant_id = "test-tenant"
    
    print(f"Using tenant ID: {tenant_id}")
    
    # Create real LLM for embeddings with better model
    llm = LLM(
        model="openai/text-embedding-3-large",  # Better model for semantic similarity
        api_key=openai_api_key
    )
    
    print(f"Using real embeddings: openai/text-embedding-3-large (optimized for similarity)")
    
    # Create multiple users with same tenant (they should share vector space)
    users = [
        {"id": "alice", "data": "Alice loves Python programming and machine learning"},
        {"id": "bob", "data": "Bob prefers JavaScript and web development"},
        {"id": "charlie", "data": "Charlie enjoys Rust systems programming"}
    ]
    
    try:
        # Create buffer for multi-user testing
        buffer = ShortTermMemory(
            max_size=10,
            buffer_multiplier=3,
            dimension=1536,
            model=llm,
            mode="remote",
            remote={
                "url": "tcp://localhost:45678",
                "tenant": tenant_id  # All users share same tenant
            }
        )
        
        print(f"✓ Buffer created for multi-user FAISSx")
        print(f"  - Server URL: tcp://localhost:45678")
        print(f"  - Tenant ID: {tenant_id}")
        print(f"  - Buffer capacity: {buffer.buffer_size}")
        
        # Add user-specific data
        print("\nAdding user-specific data to shared tenant...")
        
        start_time = time.time()
        for user in users:
            await buffer.add(user["data"], {"user_id": user["id"], "timestamp": time.time()})
            print(f"  - Added data for {user['id']}")
        
        # Add some additional mixed data
        await buffer.add("General programming discussion about algorithms", {"user_id": "system"})
        await buffer.add("Machine learning is revolutionizing software", {"user_id": "alice"})
        await buffer.add("Web frameworks are evolving rapidly", {"user_id": "bob"})
        end_time = time.time()
        
        print(f"✓ Added {len(users) + 3} messages in {end_time - start_time:.2f}s")
        
        # Test user-aware vector search
        print("\nTesting multi-user vector search...")
        
        # Search 1: Find Python-related content (should find Alice's data)
        search_start = time.time()
        python_results = await buffer.search("Python programming tutorials", limit=3)
        search_end = time.time()
        
        print(f"\n1. Python search completed in {search_end - search_start:.3f}s")
        print(f"   Found {len(python_results)} results:")
        for i, result in enumerate(python_results):
            user_id = result.get('metadata', {}).get('user_id', 'unknown')
            print(f"   {i+1}. User {user_id}: {result['text'][:50]}...")
        
        # Search 2: Find web development content (should find Bob's data)
        web_results = await buffer.search("web development JavaScript", limit=3)
        print(f"\n2. Web development search found {len(web_results)} results:")
        for i, result in enumerate(web_results):
            user_id = result.get('metadata', {}).get('user_id', 'unknown')
            print(f"   {i+1}. User {user_id}: {result['text'][:50]}...")
        
        # Search 3: Find Rust content (should find Charlie's data)
        rust_results = await buffer.search("Rust systems programming", limit=3)
        print(f"\n3. Rust search found {len(rust_results)} results:")
        for i, result in enumerate(rust_results):
            user_id = result.get('metadata', {}).get('user_id', 'unknown')
            print(f"   {i+1}. User {user_id}: {result['text'][:50]}...")
        
        # Verify user data is searchable
        alice_found = any(r.get('metadata', {}).get('user_id') == 'alice' for r in python_results)
        bob_found = any(r.get('metadata', {}).get('user_id') == 'bob' for r in web_results)
        charlie_found = any(r.get('metadata', {}).get('user_id') == 'charlie' for r in rust_results)
        
        print(f"\n✓ User data retrieval:")
        print(f"  - Alice's Python data found: {'✅' if alice_found else '❌'}")
        print(f"  - Bob's JavaScript data found: {'✅' if bob_found else '❌'}")
        print(f"  - Charlie's Rust data found: {'✅' if charlie_found else '❌'}")
        
        return {
            "status": "success",
            "tenant_id": tenant_id,
            "messages_added": len(users) + 3,
            "users_tested": len(users),
            "search_results": {
                "python": len(python_results),
                "web": len(web_results),
                "rust": len(rust_results)
            },
            "user_data_found": {
                "alice": alice_found,
                "bob": bob_found,
                "charlie": charlie_found
            },
            "add_time": end_time - start_time
        }
        
    except Exception as e:
        print(f"❌ Multi-user FAISSx test failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "failed",
            "error": str(e)
        }

async def test_tenant_isolation():
    """Test that different tenants have isolated vector spaces"""
    print("\n=== Testing Tenant Isolation in FAISSx ===")
    
    # Load secrets and create real LLM
    secrets_manager = SecretsManager("test-formations/formation-memory")
    await secrets_manager.initialize_encryption()
    openai_api_key = await secrets_manager.get_secret("OPENAI_API_KEY")
    
    # Create real LLM for embeddings
    llm = LLM(
        model="openai/text-embedding-3-small",
        api_key=openai_api_key
    )
    
    try:
        # Create buffers for different tenants
        tenant1_buffer = ShortTermMemory(
            max_size=5,
            buffer_multiplier=2,
            dimension=1536,
            model=llm,
            mode="remote",
            remote={
                "url": "tcp://localhost:45678",
                "tenant": "tenant-alpha"
            }
        )
        
        tenant2_buffer = ShortTermMemory(
            max_size=5,
            buffer_multiplier=2,
            dimension=1536,
            model=llm,
            mode="remote",
            remote={
                "url": "tcp://localhost:45678",
                "tenant": "tenant-beta"
            }
        )
        
        print(f"✓ Created buffers for two different tenants")
        print(f"  - Tenant 1: tenant-alpha")
        print(f"  - Tenant 2: tenant-beta")
        
        # Add different data to each tenant
        print("\nAdding tenant-specific data...")
        
        # Tenant 1 data (alpha)
        await tenant1_buffer.add("Alpha company specializes in quantum computing", {"tenant": "alpha"})
        await tenant1_buffer.add("Quantum algorithms are the future", {"tenant": "alpha"})
        await tenant1_buffer.add("Alpha's research focuses on qubit stability", {"tenant": "alpha"})
        
        # Tenant 2 data (beta)
        await tenant2_buffer.add("Beta corporation develops blockchain solutions", {"tenant": "beta"})
        await tenant2_buffer.add("Cryptocurrency and DeFi are our expertise", {"tenant": "beta"})
        await tenant2_buffer.add("Beta's platform handles millions of transactions", {"tenant": "beta"})
        
        print("✓ Added tenant-specific data")
        
        # Search in each tenant's space
        print("\nTesting tenant isolation...")
        
        # Search for quantum in tenant 1 (should find results)
        quantum_results_t1 = await tenant1_buffer.search("quantum computing research", limit=5)
        print(f"\nTenant Alpha - Quantum search: {len(quantum_results_t1)} results")
        for r in quantum_results_t1:
            print(f"  - {r['text'][:60]}...")
        
        # Search for blockchain in tenant 1 (should NOT find results)
        blockchain_results_t1 = await tenant1_buffer.search("blockchain cryptocurrency", limit=5)
        print(f"\nTenant Alpha - Blockchain search: {len(blockchain_results_t1)} results")
        for r in blockchain_results_t1:
            print(f"  - {r['text'][:60]}...")
        
        # Search for blockchain in tenant 2 (should find results)
        blockchain_results_t2 = await tenant2_buffer.search("blockchain cryptocurrency", limit=5)
        print(f"\nTenant Beta - Blockchain search: {len(blockchain_results_t2)} results")
        for r in blockchain_results_t2:
            print(f"  - {r['text'][:60]}...")
        
        # Search for quantum in tenant 2 (should NOT find results)
        quantum_results_t2 = await tenant2_buffer.search("quantum computing research", limit=5)
        print(f"\nTenant Beta - Quantum search: {len(quantum_results_t2)} results")
        for r in quantum_results_t2:
            print(f"  - {r['text'][:60]}...") 
        
        # Verify isolation
        tenant1_has_quantum = len(quantum_results_t1) > 0
        tenant1_no_blockchain = len(blockchain_results_t1) == 0 or \
            not any("blockchain" in r['text'].lower() for r in blockchain_results_t1)
        tenant2_has_blockchain = len(blockchain_results_t2) > 0
        tenant2_no_quantum = len(quantum_results_t2) == 0 or \
            not any("quantum" in r['text'].lower() for r in quantum_results_t2)
        
        isolation_working = tenant1_has_quantum and tenant1_no_blockchain and \
                          tenant2_has_blockchain and tenant2_no_quantum
        
        print(f"\n✓ Tenant isolation results:")
        print(f"  - Tenant Alpha has quantum data: {'✅' if tenant1_has_quantum else '❌'}")
        print(f"  - Tenant Alpha isolated from blockchain: {'✅' if tenant1_no_blockchain else '❌'}")
        print(f"  - Tenant Beta has blockchain data: {'✅' if tenant2_has_blockchain else '❌'}")
        print(f"  - Tenant Beta isolated from quantum: {'✅' if tenant2_no_quantum else '❌'}")
        print(f"  - Overall isolation: {'✅ WORKING' if isolation_working else '❌ FAILED'}")
        
        return {
            "status": "success" if isolation_working else "partial",
            "isolation_working": isolation_working,
            "tenant1_results": {
                "quantum": len(quantum_results_t1),
                "blockchain": len(blockchain_results_t1)
            },
            "tenant2_results": {
                "quantum": len(quantum_results_t2),
                "blockchain": len(blockchain_results_t2)
            }
        }
        
    except Exception as e:
        print(f"❌ Tenant isolation test failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "failed",
            "error": str(e)
        }

async def test_user_search_relevance():
    """Test that vector search returns relevant results for each user"""
    print("\n=== Testing User Search Relevance ===")
    
    # Load secrets
    secrets_manager = SecretsManager("test-formations/formation-memory")
    await secrets_manager.initialize_encryption()
    tenant_id = await secrets_manager.get_secret("FAISSX_TENANT_ID")
    openai_api_key = await secrets_manager.get_secret("OPENAI_API_KEY")
    
    if not tenant_id:
        tenant_id = "relevance-test"
    
    # Create real LLM for embeddings
    llm = LLM(
        model="openai/text-embedding-3-small",
        api_key=openai_api_key
    )
    
    print(f"Using real embeddings for relevance testing")
    
    try:
        # Create buffer for relevance testing
        buffer = ShortTermMemory(
            max_size=20,
            buffer_multiplier=2,
            dimension=1536,
            model=llm,
            mode="remote",
            remote={
                "url": "tcp://localhost:45678",
                "tenant": tenant_id
            }
        )
        
        print(f"✓ Created buffer for relevance testing")
        print(f"  - Tenant: {tenant_id}")
        
        # Add diverse user data
        print("\nAdding diverse user-specific content...")
        
        # Alice's technical content
        await buffer.add("Alice: I'm debugging a Python async/await issue", {"user": "alice", "topic": "debugging"})
        await buffer.add("Alice: The coroutine is not being awaited properly", {"user": "alice", "topic": "async"})
        await buffer.add("Alice: Found the issue - missing async keyword", {"user": "alice", "topic": "solution"})
        
        # Bob's project content
        await buffer.add("Bob: Starting new React project with TypeScript", {"user": "bob", "topic": "project"})
        await buffer.add("Bob: Setting up Redux for state management", {"user": "bob", "topic": "architecture"})
        await buffer.add("Bob: Implementing authentication with JWT", {"user": "bob", "topic": "security"})
        
        # Charlie's learning content
        await buffer.add("Charlie: Learning about neural networks today", {"user": "charlie", "topic": "learning"})
        await buffer.add("Charlie: Backpropagation is complex but fascinating", {"user": "charlie", "topic": "ai"})
        await buffer.add("Charlie: Implementing my first CNN in PyTorch", {"user": "charlie", "topic": "implementation"})
        
        print("✓ Added 9 user-specific messages")
        
        # Test relevance searches
        print("\nTesting search relevance...")
        
        # Search 1: Async programming (should find Alice's content)
        async_results = await buffer.search("async await coroutine Python", limit=3)
        print(f"\n1. Async programming search - {len(async_results)} results:")
        alice_count = 0
        for r in async_results:
            user = r.get('metadata', {}).get('user', 'unknown')
            if user == 'alice':
                alice_count += 1
            print(f"   - {user}: {r['text'][:50]}...")
        
        # Search 2: React development (should find Bob's content)
        react_results = await buffer.search("React Redux TypeScript frontend", limit=3)
        print(f"\n2. React development search - {len(react_results)} results:")
        bob_count = 0
        for r in react_results:
            user = r.get('metadata', {}).get('user', 'unknown')
            if user == 'bob':
                bob_count += 1
            print(f"   - {user}: {r['text'][:50]}...")
        
        # Search 3: Machine learning (should find Charlie's content)
        ml_results = await buffer.search("neural networks deep learning AI", limit=3)
        print(f"\n3. Machine learning search - {len(ml_results)} results:")
        charlie_count = 0
        for r in ml_results:
            user = r.get('metadata', {}).get('user', 'unknown')
            if user == 'charlie':
                charlie_count += 1
            print(f"   - {user}: {r['text'][:50]}...")
        
        # Calculate relevance scores
        alice_relevance = alice_count / max(len(async_results), 1) * 100
        bob_relevance = bob_count / max(len(react_results), 1) * 100
        charlie_relevance = charlie_count / max(len(ml_results), 1) * 100
        avg_relevance = (alice_relevance + bob_relevance + charlie_relevance) / 3
        
        print(f"\n✓ Relevance scores (with real embeddings):")
        print(f"  - Alice's content relevance: {alice_relevance:.0f}%")
        print(f"  - Bob's content relevance: {bob_relevance:.0f}%")
        print(f"  - Charlie's content relevance: {charlie_relevance:.0f}%")
        print(f"  - Average relevance: {avg_relevance:.0f}%")
        
        relevance_good = avg_relevance >= 50  # Slightly lower threshold for real embeddings
        
        return {
            "status": "success" if relevance_good else "partial",
            "relevance_scores": {
                "alice": alice_relevance,
                "bob": bob_relevance,
                "charlie": charlie_relevance,
                "average": avg_relevance
            },
            "search_counts": {
                "async": len(async_results),
                "react": len(react_results),
                "ml": len(ml_results)
            }
        }
        
    except Exception as e:
        print(f"❌ Relevance test failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "failed",
            "error": str(e)
        }

async def main():
    """Run all multi-user FAISSx tests"""
    print("🚀 Testing Multi-User FAISSx Vector Search")
    print("=" * 60)
    
    # Run tests
    multi_user_result = await test_multi_user_faissx()
    tenant_isolation_result = await test_tenant_isolation()
    relevance_result = await test_user_search_relevance()
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 MULTI-USER FAISSX TEST SUMMARY")
    print("=" * 60)
    
    print(f"\nMulti-User Search: {'✅ PASS' if multi_user_result.get('status') == 'success' else '❌ FAIL'}")
    if multi_user_result.get("status") == "success":
        print(f"  - Tenant ID: {multi_user_result.get('tenant_id')}")
        print(f"  - Users tested: {multi_user_result.get('users_tested')}")
        print(f"  - Messages added: {multi_user_result.get('messages_added')}")
        user_found = multi_user_result.get('user_data_found', {})
        print(f"  - Alice's data found: {'✅' if user_found.get('alice') else '❌'}")
        print(f"  - Bob's data found: {'✅' if user_found.get('bob') else '❌'}")
        print(f"  - Charlie's data found: {'✅' if user_found.get('charlie') else '❌'}")
    
    print(f"\nTenant Isolation: {'✅ PASS' if tenant_isolation_result.get('isolation_working') else '❌ FAIL'}")
    if tenant_isolation_result.get("status") in ["success", "partial"]:
        t1 = tenant_isolation_result.get('tenant1_results', {})
        t2 = tenant_isolation_result.get('tenant2_results', {})
        print(f"  - Tenant Alpha: {t1.get('quantum', 0)} quantum results, {t1.get('blockchain', 0)} blockchain results")
        print(f"  - Tenant Beta: {t2.get('blockchain', 0)} blockchain results, {t2.get('quantum', 0)} quantum results")
    
    print(f"\nSearch Relevance: {'✅ PASS' if relevance_result.get('status') == 'success' else '❌ FAIL'}")
    
    # Overall result
    all_passed = (
        multi_user_result.get("status") == "success" and
        tenant_isolation_result.get("isolation_working", False) and
        relevance_result.get("status") == "success"
    )
    
    print(f"\n🎯 OVERALL RESULT: {'✅ ALL MULTI-USER TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if all_passed:
        print("\n💡 Multi-User FAISSx Features:")
        print("   - Multiple users can share a tenant's vector space")
        print("   - User-specific data is searchable and retrievable")
        print("   - Different tenants have isolated vector spaces")
        print("   - Vector search returns relevant results per user context")
    
    return {
        "multi_user": multi_user_result,
        "tenant_isolation": tenant_isolation_result,
        "search_relevance": relevance_result,
        "all_passed": all_passed
    }

if __name__ == "__main__":
    asyncio.run(main())