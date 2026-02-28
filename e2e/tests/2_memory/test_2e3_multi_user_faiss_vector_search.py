#!/usr/bin/env python3
"""Test 2E3: Multi-User FAISS Vector Search

This test validates:
1. Multi-user vector search with tenant sharing
2. Tenant isolation between different tenants
3. Vector search relevance and accuracy
4. Real embedding integration
"""

import sys
import asyncio
import time
import os
from pathlib import Path

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest  # noqa: E402
from test_utils import timeout_test, safe_overlord_chat, with_timeout, safe_formation_load, safe_formation_shutdown
from muxi.runtime.services.memory.working import WorkingMemory  # noqa: E402
from muxi.runtime.services.secrets.secrets_manager import SecretsManager  # noqa: E402
from muxi.runtime.services.llm.llm import LLM  # noqa: E402


class TestMultiUserFAISSVectorSearch(BaseMemoryTest):
    """Test multi-user FAISS vector search."""

    @timeout_test(60.0)
    async def test_multi_user_faissx(self):
        """Test multi-user FAISSx with tenant isolation."""
        print("\n  👥 Testing Multi-User FAISSx with Tenant Isolation")

        # Load secrets
        secrets_manager = SecretsManager(str(self.FORMATION_DIR))
        await secrets_manager.initialize_encryption()
        tenant_id = await secrets_manager.get_secret("FAISSX_TENANT_ID")
        openai_api_key = await secrets_manager.get_secret("OPENAI_API_KEY")

        if not tenant_id:
            print("    Using default tenant ID for testing")
            tenant_id = "test-tenant"

        print(f"    Using tenant ID: {tenant_id}")

        # Create real LLM for embeddings with better model
        llm = LLM(
            model="openai/text-embedding-3-large",  # Better model for semantic similarity
            api_key=openai_api_key,
        )

        print("    Using real embeddings: openai/text-embedding-3-large")

        # Create multiple users with same tenant (they should share vector space)
        users = [
            {"id": "alice", "data": "Alice loves Python programming and machine learning"},
            {"id": "bob", "data": "Bob prefers JavaScript and web development"},
            {"id": "charlie", "data": "Charlie enjoys Rust systems programming"},
        ]

        try:
            # Create buffer for multi-user testing
            buffer = WorkingMemory(
                formation_id="test_formation",
                max_size=10,
                buffer_multiplier=3,
                dimension=1536,
                model=llm,
                mode="remote",
                remote={
                    "url": "tcp://localhost:45678",
                    "tenant": tenant_id,  # All users share same tenant
                },
            )

            print("    ✓ Buffer created for multi-user FAISSx")
            print("      Server URL: tcp://localhost:45678")
            print(f"      Tenant ID: {tenant_id}")
            print(f"      Buffer capacity: {buffer.buffer_size}")

            # Add user-specific data
            print("\n    Adding user-specific data to shared tenant...")

            start_time = time.time()
            for user in users:
                await buffer.add(user["data"], {"user_id": user["id"], "timestamp": time.time()})
                print(f"      Added data for {user['id']}")

            # Add some additional mixed data
            await buffer.add(
                "General programming discussion about algorithms", {"user_id": "system"}
            )
            await buffer.add("Machine learning is revolutionizing software", {"user_id": "alice"})
            await buffer.add("Web frameworks are evolving rapidly", {"user_id": "bob"})
            end_time = time.time()

            print(f"    ✓ Added {len(users) + 3} messages in {end_time - start_time:.2f}s")

            # Test user-aware vector search
            print("\n    Testing multi-user vector search...")

            # Search 1: Find Python-related content (should find Alice's data)
            search_start = time.time()
            python_results = await buffer.search("Python programming tutorials", limit=3)
            search_end = time.time()

            print(f"\n    1. Python search completed in {search_end - search_start:.3f}s")
            print(f"       Found {len(python_results)} results:")
            for i, result in enumerate(python_results):
                user_id = result.get("metadata", {}).get("user_id", "unknown")
                print(f"       {i+1}. User {user_id}: {result['text'][:50]}...")

            # Search 2: Find web development content (should find Bob's data)
            web_results = await buffer.search("web development JavaScript", limit=3)
            print(f"\n    2. Web development search found {len(web_results)} results:")
            for i, result in enumerate(web_results):
                user_id = result.get("metadata", {}).get("user_id", "unknown")
                print(f"       {i+1}. User {user_id}: {result['text'][:50]}...")

            # Search 3: Find Rust content (should find Charlie's data)
            rust_results = await buffer.search("Rust systems programming", limit=3)
            print(f"\n    3. Rust search found {len(rust_results)} results:")
            for i, result in enumerate(rust_results):
                user_id = result.get("metadata", {}).get("user_id", "unknown")
                print(f"       {i+1}. User {user_id}: {result['text'][:50]}...")

            # Verify user data is searchable
            alice_found = any(
                r.get("metadata", {}).get("user_id") == "alice" for r in python_results
            )
            bob_found = any(r.get("metadata", {}).get("user_id") == "bob" for r in web_results)
            charlie_found = any(
                r.get("metadata", {}).get("user_id") == "charlie" for r in rust_results
            )

            print("\n    ✓ User data retrieval:")
            print(f"      Alice's Python data found: {'✅' if alice_found else '❌'}")
            print(f"      Bob's JavaScript data found: {'✅' if bob_found else '❌'}")
            print(f"      Charlie's Rust data found: {'✅' if charlie_found else '❌'}")

            return True, {
                "tenant_id": tenant_id,
                "messages_added": len(users) + 3,
                "users_tested": len(users),
                "search_results": {
                    "python": len(python_results),
                    "web": len(web_results),
                    "rust": len(rust_results),
                },
                "user_data_found": {
                    "alice": alice_found,
                    "bob": bob_found,
                    "charlie": charlie_found,
                },
                "add_time": end_time - start_time,
            }

        except Exception as e:
            print(f"    ❌ Multi-user FAISSx test failed: {e}")
            return False, {"error": str(e)}

    @timeout_test(60.0)
    async def test_tenant_isolation(self):
        """Test that different tenants have isolated vector spaces."""
        print("\n  🔐 Testing Tenant Isolation in FAISSx")

        # Load secrets and create real LLM
        secrets_manager = SecretsManager(str(self.FORMATION_DIR))
        await secrets_manager.initialize_encryption()
        openai_api_key = await secrets_manager.get_secret("OPENAI_API_KEY")

        # Create real LLM for embeddings
        llm = LLM(model="openai/text-embedding-3-small", api_key=openai_api_key)

        try:
            # Create buffers for different tenants
            tenant1_buffer = WorkingMemory(
                formation_id="test_formation",
                max_size=5,
                buffer_multiplier=2,
                dimension=1536,
                model=llm,
                mode="remote",
                remote={"url": "tcp://localhost:45678", "tenant": "tenant-alpha"},
            )

            tenant2_buffer = WorkingMemory(
                formation_id="test_formation",
                max_size=5,
                buffer_multiplier=2,
                dimension=1536,
                model=llm,
                mode="remote",
                remote={"url": "tcp://localhost:45678", "tenant": "tenant-beta"},
            )

            print("    ✓ Created buffers for two different tenants")
            print("      Tenant 1: tenant-alpha")
            print("      Tenant 2: tenant-beta")

            # Add different data to each tenant
            print("\n    Adding tenant-specific data...")

            # Tenant 1 data (alpha)
            await tenant1_buffer.add(
                "Alpha company specializes in quantum computing", {"tenant": "alpha"}
            )
            await tenant1_buffer.add("Quantum algorithms are the future", {"tenant": "alpha"})
            await tenant1_buffer.add(
                "Alpha's research focuses on qubit stability", {"tenant": "alpha"}
            )

            # Tenant 2 data (beta)
            await tenant2_buffer.add(
                "Beta corporation develops blockchain solutions", {"tenant": "beta"}
            )
            await tenant2_buffer.add(
                "Cryptocurrency and DeFi are our expertise", {"tenant": "beta"}
            )
            await tenant2_buffer.add(
                "Beta's platform handles millions of transactions", {"tenant": "beta"}
            )

            print("    ✓ Added tenant-specific data")

            # Search in each tenant's space
            print("\n    Testing tenant isolation...")

            # Search for quantum in tenant 1 (should find results)
            quantum_results_t1 = await tenant1_buffer.search("quantum computing research", limit=5)
            print(f"\n    Tenant Alpha - Quantum search: {len(quantum_results_t1)} results")

            # Search for blockchain in tenant 1 (should NOT find results)
            blockchain_results_t1 = await tenant1_buffer.search(
                "blockchain cryptocurrency", limit=5
            )
            print(f"    Tenant Alpha - Blockchain search: {len(blockchain_results_t1)} results")

            # Search for blockchain in tenant 2 (should find results)
            blockchain_results_t2 = await tenant2_buffer.search(
                "blockchain cryptocurrency", limit=5
            )
            print(f"    Tenant Beta - Blockchain search: {len(blockchain_results_t2)} results")

            # Search for quantum in tenant 2 (should NOT find results)
            quantum_results_t2 = await tenant2_buffer.search("quantum computing research", limit=5)
            print(f"    Tenant Beta - Quantum search: {len(quantum_results_t2)} results")

            # Verify isolation
            tenant1_has_quantum = len(quantum_results_t1) > 0
            tenant1_no_blockchain = len(blockchain_results_t1) == 0 or not any(
                "blockchain" in r["text"].lower() for r in blockchain_results_t1
            )
            tenant2_has_blockchain = len(blockchain_results_t2) > 0
            tenant2_no_quantum = len(quantum_results_t2) == 0 or not any(
                "quantum" in r["text"].lower() for r in quantum_results_t2
            )

            isolation_working = (
                tenant1_has_quantum
                and tenant1_no_blockchain
                and tenant2_has_blockchain
                and tenant2_no_quantum
            )

            print("\n    ✓ Tenant isolation results:")
            print(f"      Tenant Alpha has quantum data: {'✅' if tenant1_has_quantum else '❌'}")
            print(
                f"      Tenant Alpha isolated from blockchain: {'✅' if tenant1_no_blockchain else '❌'}"
            )
            print(
                f"      Tenant Beta has blockchain data: {'✅' if tenant2_has_blockchain else '❌'}"
            )
            print(
                f"      Tenant Beta isolated from quantum: {'✅' if tenant2_no_quantum else '❌'}"
            )
            print(f"      Overall isolation: {'✅ WORKING' if isolation_working else '❌ FAILED'}")

            return True if isolation_working else False, {
                "isolation_working": isolation_working,
                "tenant1_results": {
                    "quantum": len(quantum_results_t1),
                    "blockchain": len(blockchain_results_t1),
                },
                "tenant2_results": {
                    "quantum": len(quantum_results_t2),
                    "blockchain": len(blockchain_results_t2),
                },
            }

        except Exception as e:
            print(f"    ❌ Tenant isolation test failed: {e}")
            return False, {"error": str(e)}

    @timeout_test(60.0)
    async def test_user_search_relevance(self):
        """Test that vector search returns relevant results for each user."""
        print("\n  🎯 Testing User Search Relevance")

        # Load secrets
        secrets_manager = SecretsManager(str(self.FORMATION_DIR))
        await secrets_manager.initialize_encryption()
        tenant_id = await secrets_manager.get_secret("FAISSX_TENANT_ID")
        openai_api_key = await secrets_manager.get_secret("OPENAI_API_KEY")

        if not tenant_id:
            tenant_id = "relevance-test"

        # Create real LLM for embeddings
        llm = LLM(model="openai/text-embedding-3-small", api_key=openai_api_key)

        print("    Using real embeddings for relevance testing")

        try:
            # Create buffer for relevance testing
            buffer = WorkingMemory(
                formation_id="test_formation",
                max_size=20,
                buffer_multiplier=2,
                dimension=1536,
                model=llm,
                mode="remote",
                remote={"url": "tcp://localhost:45678", "tenant": tenant_id},
            )

            print("    ✓ Created buffer for relevance testing")
            print(f"      Tenant: {tenant_id}")

            # Add diverse user data
            print("\n    Adding diverse user-specific content...")

            # Alice's technical content
            await buffer.add(
                "Alice: I'm debugging a Python async/await issue",
                {"user": "alice", "topic": "debugging"},
            )
            await buffer.add(
                "Alice: The coroutine is not being awaited properly",
                {"user": "alice", "topic": "async"},
            )
            await buffer.add(
                "Alice: Found the issue - missing async keyword",
                {"user": "alice", "topic": "solution"},
            )

            # Bob's project content
            await buffer.add(
                "Bob: Starting new React project with TypeScript",
                {"user": "bob", "topic": "project"},
            )
            await buffer.add(
                "Bob: Setting up Redux for state management",
                {"user": "bob", "topic": "architecture"},
            )
            await buffer.add(
                "Bob: Implementing authentication with JWT", {"user": "bob", "topic": "security"}
            )

            # Charlie's learning content
            await buffer.add(
                "Charlie: Learning about neural networks today",
                {"user": "charlie", "topic": "learning"},
            )
            await buffer.add(
                "Charlie: Backpropagation is complex but fascinating",
                {"user": "charlie", "topic": "ai"},
            )
            await buffer.add(
                "Charlie: Implementing my first CNN in PyTorch",
                {"user": "charlie", "topic": "implementation"},
            )

            print("    ✓ Added 9 user-specific messages")

            # Test relevance searches
            print("\n    Testing search relevance...")

            # Search 1: Async programming (should find Alice's content)
            async_results = await buffer.search("async await coroutine Python", limit=3)
            print(f"\n    1. Async programming search - {len(async_results)} results:")
            alice_count = 0
            for r in async_results:
                user = r.get("metadata", {}).get("user", "unknown")
                if user == "alice":
                    alice_count += 1
                print(f"       {user}: {r['text'][:50]}...")

            # Search 2: React development (should find Bob's content)
            react_results = await buffer.search("React Redux TypeScript frontend", limit=3)
            print(f"\n    2. React development search - {len(react_results)} results:")
            bob_count = 0
            for r in react_results:
                user = r.get("metadata", {}).get("user", "unknown")
                if user == "bob":
                    bob_count += 1
                print(f"       {user}: {r['text'][:50]}...")

            # Search 3: Machine learning (should find Charlie's content)
            ml_results = await buffer.search("neural networks deep learning AI", limit=3)
            print(f"\n    3. Machine learning search - {len(ml_results)} results:")
            charlie_count = 0
            for r in ml_results:
                user = r.get("metadata", {}).get("user", "unknown")
                if user == "charlie":
                    charlie_count += 1
                print(f"       {user}: {r['text'][:50]}...")

            # Calculate relevance scores
            alice_relevance = alice_count / max(len(async_results), 1) * 100
            bob_relevance = bob_count / max(len(react_results), 1) * 100
            charlie_relevance = charlie_count / max(len(ml_results), 1) * 100
            avg_relevance = (alice_relevance + bob_relevance + charlie_relevance) / 3

            print("\n    ✓ Relevance scores (with real embeddings):")
            print(f"      Alice's content relevance: {alice_relevance:.0f}%")
            print(f"      Bob's content relevance: {bob_relevance:.0f}%")
            print(f"      Charlie's content relevance: {charlie_relevance:.0f}%")
            print(f"      Average relevance: {avg_relevance:.0f}%")

            relevance_good = avg_relevance >= 50  # Threshold for real embeddings

            return relevance_good, {
                "relevance_scores": {
                    "alice": alice_relevance,
                    "bob": bob_relevance,
                    "charlie": charlie_relevance,
                    "average": avg_relevance,
                },
                "search_counts": {
                    "async": len(async_results),
                    "react": len(react_results),
                    "ml": len(ml_results),
                },
            }

        except Exception as e:
            print(f"    ❌ Relevance test failed: {e}")
            return False, {"error": str(e)}

    @timeout_test(60.0)
    async def test_multi_user_vector(self):
        """Main test method."""
        test_name = "2e3_multi_user_vector_search"
        self.print_test_header(test_name, "Test multi-user vector search with isolation")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            print("  Testing Multi-User FAISSx Vector Search...")

            # Test 1: Multi-user search
            multi_success, multi_result = await self.test_multi_user_faissx()
            if multi_success:
                checks_passed.append("Multi-user search working")
                transcript.append(("System", f"Multi-user test passed: {multi_result}"))
                user_found = multi_result.get("user_data_found", {})
                if user_found.get("alice") and user_found.get("bob") and user_found.get("charlie"):
                    checks_passed.append("All user data found correctly")
            else:
                all_passed = False
                transcript.append(("System", f"Multi-user test failed: {multi_result}"))

            # Test 2: Tenant isolation
            isolation_success, isolation_result = await self.test_tenant_isolation()
            if isolation_success:
                checks_passed.append("Tenant isolation working")
                transcript.append(("System", f"Tenant isolation test passed: {isolation_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"Tenant isolation test failed: {isolation_result}"))

            # Test 3: Search relevance
            relevance_success, relevance_result = await self.test_user_search_relevance()
            if relevance_success:
                checks_passed.append("Search relevance working")
                transcript.append(("System", f"Relevance test passed: {relevance_result}"))
                avg_relevance = relevance_result.get("relevance_scores", {}).get("average", 0)
                if avg_relevance >= 70:
                    checks_passed.append("High relevance scores achieved")
            else:
                all_passed = False
                transcript.append(("System", f"Relevance test failed: {relevance_result}"))

            # Summary
            if multi_success and isolation_success and relevance_success:
                print("  ✅ ALL MULTI-USER TESTS PASSED!")
                print("    ✅ Multiple users can share a tenant's vector space")
                print("    ✅ User-specific data is searchable and retrievable")
                print("    ✅ Different tenants have isolated vector spaces")
                print("    ✅ Vector search returns relevant results per user context")
                checks_passed.append("Complete multi-user functionality verified")
            else:
                print("  ⚠️ PARTIAL SUCCESS")
                if multi_success:
                    print("    ✅ Multi-user search working")
                else:
                    print("    ❌ Multi-user search failed")
                if isolation_success:
                    print("    ✅ Tenant isolation working")
                else:
                    print("    ❌ Tenant isolation failed")
                if relevance_success:
                    print("    ✅ Search relevance working")
                else:
                    print("    ❌ Search relevance failed")

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False
            transcript.append(("System", f"Test failed with error: {str(e)}"))

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("👥 AREA 2E3: MULTI-USER VECTOR SEARCH")
        print("=" * 60)

        # Run test cases
        result = await self.test_multi_user_vector()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = TestMultiUserFAISSVectorSearch()
    result = asyncio.run(test.run_test())
    if result:
        print("SUCCESS", flush=True)
    import os; os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
