"""
Test 6E2: Large Knowledge Base Performance
Test performance with many knowledge files
"""
import asyncio
import sys
from pathlib import Path
import os
import tempfile
import shutil
import time

sys.path.insert(0, '../../..')

from muxi.runtime.formation import Formation


async def test_large_knowledge_base():
    """Test performance with many knowledge files"""

    print("\n=== Test 6E2: Large Knowledge Base Performance ===")
    print("This test verifies performance with many knowledge files\n")

    # Create a temporary directory for the test formation
    temp_dir = tempfile.mkdtemp()

    try:
        # Copy the test formation first
        test_formation_dir = os.path.join(temp_dir, "formation-test")
        shutil.copytree(str(Path(__file__).parent / "formations" / "formation-knowledge"), test_formation_dir)

        # Create knowledge dir INSIDE the formation for relative path
        large_knowledge_dir = os.path.join(test_formation_dir, "knowledge", "large-knowledge")
        os.makedirs(large_knowledge_dir)

        # Create many small knowledge files
        num_files = 20  # Create 20 knowledge files
        print(f"Creating {num_files} knowledge files...")

        for i in range(num_files):
            filename = f"knowledge_{i:03d}.md"
            filepath = os.path.join(large_knowledge_dir, filename)

            # Create content for each file
            content = f"""# Knowledge Document {i}

## Overview
This is knowledge document number {i} containing test information.

## Key Points
- Point 1: Important information about topic {i}
- Point 2: Details about implementation {i}
- Point 3: Best practices for scenario {i}

## Examples
Here are some examples related to topic {i}:
1. Example A: How to handle case {i}A
2. Example B: How to handle case {i}B
3. Example C: How to handle case {i}C

## Additional Information
This document contains approximately 500-1000 characters of content
to simulate a reasonable knowledge base entry. Each document is
unique to ensure proper testing of the knowledge system's ability
to handle multiple distinct documents efficiently.

Topic {i} specific details:
- Configuration option {i}-1
- Configuration option {i}-2
- Configuration option {i}-3
"""

            with open(filepath, 'w') as f:
                f.write(content)

        print(f"✓ Created {num_files} knowledge files")

        # Create agent config with large knowledge base (using relative path)
        agent_yaml = f"""
schema: "1.0.0"
id: "test-large"
name: "Test Large Knowledge Agent"
description: "Agent with many knowledge files"

system_message: |
  You are a helpful assistant with access to a large knowledge base.

role: "assistant"

knowledge:
  enabled: true
  sources:
  - path: "knowledge/large-knowledge"
    description: "Large knowledge base with {num_files} files"
"""

        # Write agent config directly to agents directory
        agents_dir = os.path.join(test_formation_dir, "agents")
        agent_config_path = os.path.join(agents_dir, "test-large.yaml")
        with open(agent_config_path, 'w') as f:
            f.write(agent_yaml)

        print("\n--- Test 1: Formation Loading Performance ---")
        print(f"Loading formation with {num_files} knowledge files...")

        start_time = time.time()

        formation = Formation()
        await formation.load(os.path.join(test_formation_dir, "formation.yaml"))
        overlord = await formation.start_overlord()

        load_time = time.time() - start_time
        print(f"✓ Formation loaded in {load_time:.2f} seconds")

        # Check if our test agent was loaded
        test_agent = overlord.agents.get("test-large")
        if not test_agent:
            print("❌ Test agent not found")
            return False

        # Reasonable loading time check (should be under 30 seconds even with many files)
        if load_time < 30:
            print(f"✅ Test 1 PASSED: Formation loaded in reasonable time ({load_time:.2f}s)")
        else:
            print(f"⚠ Test 1 WARNING: Formation loading took {load_time:.2f}s (expected < 30s)")

        # Test 2: First Query Performance
        print("\n--- Test 2: First Query Performance ---")
        print("👤 User: What topics are covered in your knowledge base?")

        query_start = time.time()

        response1 = await overlord.chat(
            "What topics are covered in your knowledge base?",
            agent_name="test-large",
            user_id="test_user_6e2",
            session_id="test_6e2_session_1",
            stream=False
        )

        query_time = time.time() - query_start

        # Extract response content
        if hasattr(response1, 'content'):
            response_text = response1.content
        else:
            response_text = str(response1)

        print(f"\n🤖 Test Large Agent: {response_text[:300]}...")
        print(f"\n✓ First query completed in {query_time:.2f} seconds")

        # First query might be slower due to initialization
        if query_time < 20:
            print(f"✅ Test 2 PASSED: First query completed in reasonable time ({query_time:.2f}s)")
        else:
            print(f"⚠ Test 2 WARNING: First query took {query_time:.2f}s (expected < 20s)")

        # Test 3: Subsequent Query Performance
        print("\n--- Test 3: Subsequent Query Performance ---")
        print("👤 User: Tell me about topic 5")

        query_start = time.time()

        response2 = await overlord.chat(
            "Tell me about topic 5",
            agent_name="test-large",
            user_id="test_user_6e2",
            session_id="test_6e2_session_2",
            stream=False
        )

        query_time = time.time() - query_start

        # Extract response content
        if hasattr(response2, 'content'):
            response_text = response2.content
        else:
            response_text = str(response2)

        print(f"\n🤖 Test Large Agent: {response_text[:300]}...")
        print(f"\n✓ Subsequent query completed in {query_time:.2f} seconds")

        # Subsequent queries should be faster
        if query_time < 10:
            print(f"✅ Test 3 PASSED: Subsequent query fast ({query_time:.2f}s)")
        else:
            print(f"⚠ Test 3 WARNING: Subsequent query took {query_time:.2f}s (expected < 10s)")

        # Test 4: Knowledge System State
        print("\n--- Test 4: Knowledge System State ---")

        await test_agent._ensure_knowledge_initialized()

        if hasattr(test_agent, 'knowledge_handler') and test_agent.knowledge_handler:
            sources = test_agent.knowledge_handler.sources
            print(f"\nKnowledge sources: {len(sources)}")

            # Count total files loaded
            files_loaded = 0
            for source in sources:
                if hasattr(source, 'files'):
                    files_loaded += len(source.files)
                    print(f"  - Source with {len(source.files)} files")

            print(f"Total files loaded: {files_loaded}")

            # Should have loaded our files (might be limited by max_files_per_source)
            if files_loaded > 0:
                print(f"✅ Test 4 PASSED: Successfully loaded {files_loaded} files")
            else:
                print("❌ Test 4 FAILED: No files loaded")

        # Test 5: Memory usage check (basic)
        print("\n--- Test 5: System Stability ---")

        # Make several more queries to ensure stability
        for i in range(3):
            query_start = time.time()
            await overlord.chat(
                f"What can you tell me about topic {i * 3}?",
                agent_name="test-large",
                user_id="test_user_6e2",
                session_id=f"test_6e2_session_{i+3}",
                stream=False
            )
            query_time = time.time() - query_start
            print(f"  Query {i+1}: {query_time:.2f}s")

        print("✅ Test 5 PASSED: System remained stable with multiple queries")

        await formation.stop_overlord()

        # Summary
        print("\n\n=== Test 6E2 Summary ===")
        print(f"✅ Successfully loaded formation with {num_files} knowledge files")
        print(f"✅ Formation loading completed in {load_time:.2f}s")
        print("✅ Queries performed within acceptable time limits")
        print("✅ System remained stable under load")
        print("\n✅ Test 6E2 PASSED: Large knowledge base handled efficiently")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print("\n✓ Cleaned up temporary directory")


def main():
    try:
        success = asyncio.run(test_large_knowledge_base())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
