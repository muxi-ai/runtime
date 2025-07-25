"""
Manual testing scenarios for the MUXI Domain Knowledge System.

These are not automated tests but rather scripts and scenarios for manual validation
of knowledge system functionality in real-world conditions.
"""

import asyncio
import tempfile
import os
import time
from typing import List

from muxi.formation.agents.knowledge import KnowledgeHandler, FileKnowledge


class ManualTestScenarios:
    """Manual testing scenarios for knowledge system validation"""

    def __init__(self, embedding_fn):
        """Initialize with embedding function for testing"""
        self.embedding_fn = embedding_fn

    async def scenario_1_knowledge_augmented_responses(self):
        """
        Scenario 1: Knowledge-Augmented Agent Responses

        Purpose: Validate that agents can provide accurate, knowledge-based responses
        Success Criteria: Responses include relevant information from knowledge sources
        """
        print("=== Scenario 1: Knowledge-Augmented Responses ===")

        # Create test knowledge
        temp_dir = tempfile.mkdtemp()

        knowledge_content = """
        # Product Documentation

        ## Features
        Our platform includes:
        - User management with role-based access control
        - Real-time collaboration tools
        - Advanced analytics dashboard
        - API integration capabilities
        - Mobile app support for iOS and Android

        ## Pricing
        - Basic Plan: $9.99/month (up to 5 users)
        - Pro Plan: $19.99/month (up to 25 users)
        - Enterprise Plan: $49.99/month (unlimited users)

        ## Support
        - Email support: support@example.com
        - Live chat available 9 AM - 5 PM EST
        - Phone support for Enterprise customers
        - Knowledge base at help.example.com
        """

        knowledge_file = os.path.join(temp_dir, "product_docs.md")
        with open(knowledge_file, 'w') as f:
            f.write(knowledge_content)

        # Initialize knowledge handler
        handler = KnowledgeHandler(
            agent_id_or_sources="manual_test_agent",
            embedding_dimension=384,
            enable_query_cache=True
        )

        # Add knowledge
        knowledge = FileKnowledge("product_docs", knowledge_file, "Product documentation")
        await handler.add_file(knowledge, self.embedding_fn)

        # Test queries
        test_queries = [
            "What features does the platform have?",
            "How much does the Pro plan cost?",
            "How can I contact support?",
            "Is there a mobile app?",
            "What's included in the Enterprise plan?"
        ]

        print("Testing knowledge-augmented responses:")

        for query in test_queries:
            print(f"\nQuery: {query}")

            # Search knowledge
            results = await handler.search(query, self.embedding_fn, top_k=3)

            if results:
                print(f"✓ Found {len(results)} relevant results")
                top_result = results[0]
                print(f"  Top result (score: {top_result['score']:.3f}):")
                print(f"  {top_result['content'][:200]}...")

                # Simulate knowledge-augmented response
                knowledge_context = "\n".join([r['content'] for r in results[:2]])
                augmented_prompt = f"""
                Based on the following knowledge:
                {knowledge_context}

                Please answer: {query}
                """

                print(f"  Knowledge-augmented prompt created: {len(augmented_prompt)} chars")
            else:
                print("✗ No relevant knowledge found")

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

        print("\n✓ Scenario 1 completed - Manual validation required")
        print("  Check that responses include relevant information from knowledge sources")

    async def scenario_2_yaml_configuration_loading(self):
        """
        Scenario 2: YAML Configuration Loading

        Purpose: Validate that knowledge can be loaded from YAML configuration
        Success Criteria: Agent loads knowledge sources from configuration file
        """
        print("\n=== Scenario 2: YAML Configuration Loading ===")

        # Create test files
        temp_dir = tempfile.mkdtemp()

        # Create knowledge files
        files_content = {
            "user_manual.md": """
            # User Manual

            ## Getting Started
            1. Sign up for an account
            2. Complete profile setup
            3. Explore the dashboard

            ## Basic Operations
            - Create new projects
            - Invite team members
            - Set up notifications
            """,
            "api_guide.md": """
            # API Guide

            ## Authentication
            Use Bearer tokens for API authentication.

            ## Endpoints
            - GET /api/projects - List projects
            - POST /api/projects - Create project
            - PUT /api/projects/{id} - Update project
            """
        }

        file_paths = []
        for filename, content in files_content.items():
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, 'w') as f:
                f.write(content)
            file_paths.append(file_path)

        # Test configuration loading
        config = {
            "enabled": True,
            "sources": [
                {
                    "path": file_paths[0],
                    "description": "User manual and getting started guide",
                    "max_file_size": 1048576
                },
                {
                    "path": file_paths[1],
                    "description": "API documentation and reference",
                    "max_file_size": 1048576
                }
            ]
        }

        print("Testing configuration-based loading:")
        print(f"  Configuration: {len(config['sources'])} sources defined")

        # Create handler from configuration
        start_time = time.time()
        handler = await KnowledgeHandler.from_agent_config(
            agent_id="config_test_agent",
            knowledge_config=config,
            generate_embeddings_fn=self.embedding_fn,
            embedding_dimension=384
        )
        loading_time = time.time() - start_time

        if handler:
            print(f"✓ Handler created successfully in {loading_time:.2f}s")
            print(f"  Sources loaded: {len(handler.sources)}")

            # Test functionality
            test_result = await handler.search("getting started", self.embedding_fn)
            print(f"  Test search returned {len(test_result)} results")

            # Test performance metrics
            metrics = handler.get_performance_metrics()
            print(f"  Performance: {metrics.total_searches} searches tracked")
        else:
            print("✗ Handler creation failed")

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

        print("✓ Scenario 2 completed - Manual validation required")
        print("  Verify YAML configuration loading works in production environment")

    async def scenario_3_cache_invalidation_behavior(self):
        """
        Scenario 3: Cache Invalidation Behavior

        Purpose: Validate MD5-based cache invalidation works correctly
        Success Criteria: Cache invalidates when file content changes
        """
        print("\n=== Scenario 3: Cache Invalidation Behavior ===")

        # Create test file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        initial_content = """
        # Test Document

        This is the initial content of the test document.
        It contains some basic information for testing.
        """
        temp_file.write(initial_content)
        temp_file.close()

        try:
            # Initialize handler
            handler = KnowledgeHandler(
                agent_id_or_sources="cache_test_agent",
                embedding_dimension=256,
                enable_query_cache=False  # Disable query cache to test file cache
            )

            knowledge = FileKnowledge("test_doc", temp_file.name, "Test document")

            print("Testing cache invalidation:")

            # First load
            print("  First load...")
            start_time = time.time()
            count1 = await handler.add_file(knowledge, self.embedding_fn)
            first_load_time = time.time() - start_time
            print(f"    Processed {count1} documents in {first_load_time:.3f}s")

            # Second load (should use cache)
            print("  Second load (should use cache)...")
            start_time = time.time()
            count2 = await handler.add_file(knowledge, self.embedding_fn)
            second_load_time = time.time() - start_time
            print(f"    Processed {count2} documents in {second_load_time:.3f}s")

            if count2 == 0 and second_load_time < first_load_time:
                print("    ✓ Cache hit detected (faster, no processing)")
            else:
                print("    ⚠ Cache behavior unclear")

            # Modify file content
            print("  Modifying file content...")
            time.sleep(0.1)  # Ensure different timestamp
            modified_content = """
            # Test Document

            This is the MODIFIED content of the test document.
            It contains updated information for cache invalidation testing.
            Additional content has been added to change the MD5 hash.
            """

            with open(temp_file.name, 'w') as f:
                f.write(modified_content)

            # Third load (should invalidate cache)
            print("  Third load (should invalidate cache)...")
            start_time = time.time()
            count3 = await handler.add_file(knowledge, self.embedding_fn)
            third_load_time = time.time() - start_time
            print(f"    Processed {count3} documents in {third_load_time:.3f}s")

            if count3 > 0:
                print("    ✓ Cache invalidation detected (reprocessed content)")
            else:
                print("    ✗ Cache invalidation failed")

            # Test search with updated content
            results = await handler.search("modified content", self.embedding_fn)
            if results:
                print(f"    ✓ Search found {len(results)} results with updated content")
            else:
                print("    ⚠ No results found for updated content")

        finally:
            # Cleanup
            os.unlink(temp_file.name)

        print("✓ Scenario 3 completed - Manual validation required")
        print("  Verify cache invalidation works correctly with file modifications")

    async def scenario_4_error_handling_resilience(self):
        """
        Scenario 4: Error Handling and Resilience

        Purpose: Validate system handles errors gracefully
        Success Criteria: System continues to function despite individual failures
        """
        print("\n=== Scenario 4: Error Handling and Resilience ===")

        # Create mixed valid/invalid knowledge sources
        temp_dir = tempfile.mkdtemp()

        # Valid file
        valid_file = os.path.join(temp_dir, "valid.md")
        with open(valid_file, 'w') as f:
            f.write("# Valid Document\n\nThis is a valid document.")

        # Test sources (mix of valid and invalid)
        test_sources = [
            FileKnowledge("valid", valid_file, "Valid document"),
            FileKnowledge("nonexistent", "/nonexistent/path/file.txt", "Nonexistent file"),
            FileKnowledge("empty_path", "", "Empty path"),
            FileKnowledge("invalid_dir", "/invalid/directory/", "Invalid directory")
        ]

        handler = KnowledgeHandler(
            agent_id_or_sources="error_test_agent",
            embedding_dimension=128
        )

        print("Testing error handling:")

        successful_sources = 0
        failed_sources = 0

        for source in test_sources:
            print(f"  Loading source: {source.name}")

            try:
                count = await handler.add_file(source, self.embedding_fn)
                if count > 0:
                    print(f"    ✓ Success: {count} documents")
                    successful_sources += 1
                else:
                    print(f"    ⚠ No documents processed")

            except Exception as e:
                print(f"    ✗ Failed: {e}")
                failed_sources += 1

        print(f"\nResults: {successful_sources} successful, {failed_sources} failed")

        # Test search functionality with partial data
        if successful_sources > 0:
            print("  Testing search with partial data...")
            results = await handler.search("valid document", self.embedding_fn)
            print(f"    Search returned {len(results)} results")

            if results:
                print("    ✓ System functional despite some failures")
            else:
                print("    ⚠ Search failed with partial data")

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

        print("✓ Scenario 4 completed - Manual validation required")
        print("  Verify system handles errors gracefully and continues functioning")

    async def scenario_5_context_persistence_across_sessions(self):
        """
        Scenario 5: Context Persistence Across Sessions

        Purpose: Validate knowledge context persists across agent sessions
        Success Criteria: Knowledge remains available after handler recreation
        """
        print("\n=== Scenario 5: Context Persistence Across Sessions ===")

        # Create persistent knowledge
        temp_dir = tempfile.mkdtemp()

        knowledge_file = os.path.join(temp_dir, "persistent_knowledge.md")
        with open(knowledge_file, 'w') as f:
            f.write("""
            # Persistent Knowledge

            ## Session Data
            This knowledge should persist across different agent sessions.

            ## Important Information
            - Session ID: TEST_SESSION_001
            - Created: Manual test scenario
            - Purpose: Validate persistence
            """)

        agent_id = "persistence_test_agent"

        print("Testing context persistence:")

        # Session 1: Create and populate knowledge
        print("  Session 1: Creating initial knowledge...")
        handler1 = KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=256,
            enable_query_cache=True
        )

        knowledge = FileKnowledge("persistent", knowledge_file, "Persistent knowledge")
        count = await handler1.add_file(knowledge, self.embedding_fn)
        print(f"    Processed {count} documents")

        # Test initial search
        results1 = await handler1.search("session data", self.embedding_fn)
        print(f"    Initial search: {len(results1)} results")

        # Session 2: Recreate handler (simulating new session)
        print("  Session 2: Recreating handler...")
        handler2 = KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=256,
            enable_query_cache=True
        )

        # Re-add same knowledge (should use cache)
        start_time = time.time()
        count2 = await handler2.add_file(knowledge, self.embedding_fn)
        load_time = time.time() - start_time
        print(f"    Reloaded in {load_time:.3f}s, processed {count2} documents")

        if count2 == 0 and load_time < 0.1:
            print("    ✓ Cache persistence detected")
        else:
            print("    ⚠ Cache persistence unclear")

        # Test search in new session
        results2 = await handler2.search("session data", self.embedding_fn)
        print(f"    Session 2 search: {len(results2)} results")

        if len(results2) == len(results1):
            print("    ✓ Knowledge accessible in new session")
        else:
            print("    ⚠ Knowledge persistence unclear")

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

        print("✓ Scenario 5 completed - Manual validation required")
        print("  Verify knowledge persists correctly across agent sessions")


async def run_manual_test_scenarios(embedding_fn):
    """Run all manual testing scenarios"""

    print("MUXI Domain Knowledge System - Manual Testing Scenarios")
    print("=" * 60)

    scenarios = ManualTestScenarios(embedding_fn)

    # Run all scenarios
    await scenarios.scenario_1_knowledge_augmented_responses()
    await scenarios.scenario_2_yaml_configuration_loading()
    await scenarios.scenario_3_cache_invalidation_behavior()
    await scenarios.scenario_4_error_handling_resilience()
    await scenarios.scenario_5_context_persistence_across_sessions()

    print("\n" + "=" * 60)
    print("All manual testing scenarios completed!")
    print("\nNext steps:")
    print("1. Review output for any failures or warnings")
    print("2. Manually validate knowledge-augmented responses")
    print("3. Test YAML configuration in production environment")
    print("4. Verify cache behavior with real file modifications")
    print("5. Test error handling with various failure conditions")
    print("6. Validate persistence across actual agent restarts")


# Example usage
if __name__ == "__main__":
    # Mock embedding function for testing
    async def mock_embedding_fn(text: str) -> List[float]:
        import hashlib
        import math

        # Create realistic embeddings
        text_hash = hashlib.md5(text.encode()).hexdigest()
        hash2 = hashlib.sha1(text.encode()).hexdigest()

        values = []
        for i in range(384):
            if i < 128:
                source = text_hash[i % len(text_hash)]
            else:
                source = hash2[i % len(hash2)]

            val = (ord(source) / 255.0 - 0.5) * 2
            val = math.tanh(val)
            values.append(val)

        return values

    # Run scenarios
    asyncio.run(run_manual_test_scenarios(mock_embedding_fn))
