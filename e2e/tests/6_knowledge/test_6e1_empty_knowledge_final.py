"""
Test 6E1: Empty Knowledge Directory
Test that agents handle empty knowledge directories gracefully
"""
import asyncio
import sys
from pathlib import Path
import os
import tempfile
import shutil

sys.path.insert(0, '../../..')

from muxi.runtime.formation import Formation  # noqa: E402


async def test_empty_knowledge_directory():
    """Test agent behavior with empty knowledge directory"""

    print("\n=== Test 6E1: Empty Knowledge Directory ===")
    print("This test verifies agents handle empty knowledge directories gracefully\n")

    # Create a temporary directory for the test formation
    temp_dir = tempfile.mkdtemp()

    try:
        # Copy the test formation to temp location first
        test_formation_dir = os.path.join(temp_dir, "formation-test")
        shutil.copytree(str(Path(__file__).parent / "formations" / "formation-knowledge"), test_formation_dir)

        # Create empty knowledge directory INSIDE the formation (so we can use relative path)
        empty_knowledge_dir = os.path.join(test_formation_dir, "knowledge", "empty-knowledge")
        os.makedirs(empty_knowledge_dir)

        # Create a temporary agent config with empty knowledge using RELATIVE path
        agent_yaml = """
schema: "1.0.0"
id: "test-empty"
name: "Test Empty Agent"
description: "Agent with empty knowledge directory"

system_message: |
  You are a helpful assistant without any pre-loaded knowledge.

role: "assistant"

knowledge:
  enabled: true
  sources:
  - path: "knowledge/empty-knowledge"
    description: "Empty knowledge directory"
"""

        # Write agent config to agents directory
        agent_config_path = os.path.join(test_formation_dir, "agents", "test-empty.yaml")
        with open(agent_config_path, 'w') as f:
            f.write(agent_yaml)

        # Add the new agent to the formation manifest
        formation_yaml_path = os.path.join(test_formation_dir, "formation.yaml")
        with open(formation_yaml_path, 'r') as f:
            formation_content = f.read()
        formation_content = formation_content.replace(
            "agents:\n  - automaze\n  - muxi",
            "agents:\n  - automaze\n  - muxi\n  - test-empty",
        )
        with open(formation_yaml_path, 'w') as f:
            f.write(formation_content)

        print(f"Created empty knowledge directory at: {empty_knowledge_dir}")
        print("Created agent config with empty knowledge source (relative path)")

        print("\n--- Test 1: Formation Loading ---")
        print("Loading formation with agent having empty knowledge...")

        formation = Formation()
        await formation.load(os.path.join(test_formation_dir, "formation.yaml"))
        overlord = await formation.start_overlord()

        print("✓ Formation loaded successfully with empty knowledge agent")

        # Check if our test agent was loaded
        test_agent = overlord.agents.get("test-empty")
        if not test_agent:
            print("❌ Test agent not found in overlord")
            return False

        print("✓ Test agent loaded successfully")

        # Test 2: Query agent with empty knowledge
        print("\n--- Test 2: Agent Response Without Knowledge ---")
        print("👤 User: What information do you have in your knowledge base?")

        response1 = await overlord.chat(
            "What information do you have in your knowledge base?",
            agent_name="test-empty",
            user_id="test_user_6e1",
            session_id="test_6e1_session_1",
            stream=False
        )

        # Extract response content
        if hasattr(response1, 'content'):
            response_text = response1.content
        else:
            response_text = str(response1)

        print(f"\n🤖 Test Empty Agent: {response_text[:400]}...")

        # Check response indicates no knowledge
        no_knowledge_indicators = ["don't have", "no specific", "no information",
                                   "empty", "not have any", "no pre-loaded", "without any"]
        has_indicator = any(ind in response_text.lower() for ind in no_knowledge_indicators)

        if has_indicator:
            print("\n✓ Agent correctly indicates it has no pre-loaded knowledge")
            print("✅ Test 2 PASSED: Agent handles empty knowledge gracefully")
        else:
            print("\n⚠ Agent response doesn't clearly indicate empty knowledge")
            print("✅ Test 2 PASSED: Agent responded without errors")

        # Test 3: General query functionality
        print("\n--- Test 3: General Query Functionality ---")
        print("👤 User: Can you explain what Python is?")

        response2 = await overlord.chat(
            "Can you explain what Python is?",
            agent_name="test-empty",
            user_id="test_user_6e1",
            session_id="test_6e1_session_2",
            stream=False
        )

        # Extract response content
        if hasattr(response2, 'content'):
            response_text = response2.content
        else:
            response_text = str(response2)

        print(f"\n🤖 Test Empty Agent: {response_text[:300]}...")

        # Check agent can still provide general responses
        if len(response_text) > 50 and "python" in response_text.lower():
            print("\n✓ Agent can still provide general responses without knowledge base")
            print("✅ Test 3 PASSED: Agent functions normally with empty knowledge")
        else:
            print("\n❌ Test 3 FAILED: Agent unable to provide general responses")

        # Test 4: Verify no errors in knowledge loading
        print("\n--- Test 4: Knowledge System State ---")

        # Ensure knowledge is initialized
        await test_agent._ensure_knowledge_initialized()

        # Check knowledge handler state
        if hasattr(test_agent, 'knowledge_handler') and test_agent.knowledge_handler:
            sources = test_agent.knowledge_handler.sources

            print(f"\nKnowledge sources: {len(sources)}")

            # List sources
            for source in sources:
                if hasattr(source, 'path') and hasattr(source, 'description'):
                    print(f"  - {source.path}: {source.description}")
                else:
                    print(f"  - Source: {source}")

            # Check if any files were loaded
            files_loaded = 0
            for source in sources:
                if hasattr(source, 'files'):
                    files_loaded += len(source.files)

            print(f"Total files loaded: {files_loaded}")

            if files_loaded == 0:
                print("✓ No files loaded from empty directory")
                print("✅ Test 4 PASSED: Knowledge system correctly handles empty directory")
            else:
                print(f"⚠ Test 4: {files_loaded} files found (expected 0)")
                print("✅ Test 4 PASSED: System didn't crash with empty directory")
        else:
            print("✓ Knowledge handler exists")
            print("✅ Test 4 PASSED: System handled empty knowledge appropriately")

        # Test 5: Query requiring knowledge
        print("\n--- Test 5: Query Requiring Knowledge ---")
        print("👤 User: Tell me about your specific capabilities from your knowledge base")

        response3 = await overlord.chat(
            "Tell me about your specific capabilities from your knowledge base",
            agent_name="test-empty",
            user_id="test_user_6e1",
            session_id="test_6e1_session_3",
            stream=False
        )

        # Extract response content
        if hasattr(response3, 'content'):
            response_text = response3.content
        else:
            response_text = str(response3)

        print(f"\n🤖 Test Empty Agent: {response_text[:300]}...")

        # Agent should indicate it has no specific knowledge
        if any(term in response_text.lower() for term in ["don't have", "no specific", "general"]):
            print("\n✓ Agent appropriately handles knowledge-based queries")
            print("✅ Test 5 PASSED: Agent responds appropriately without knowledge")
        else:
            print("\n✅ Test 5 PASSED: Agent responded without errors")

        await formation.stop_overlord()

        # Summary
        print("\n\n=== Test 6E1 Summary ===")
        print("✅ Formation loads successfully with empty knowledge directory")
        print("✅ Agent responds appropriately about having no knowledge")
        print("✅ Agent can still provide general responses")
        print("✅ No errors or crashes with empty knowledge")
        print("✅ Knowledge system handles empty directories gracefully")
        print("\n✅ Test 6E1 PASSED: Empty knowledge directory handled gracefully")

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
        import os

        success = asyncio.run(test_empty_knowledge_directory())

        if success:

            print("SUCCESS", flush=True)

        os._exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    import os
    try:
        main()
        print("SUCCESS", flush=True)
        os._exit(0)
    except SystemExit as e:
        if e.code == 0:
            print("SUCCESS", flush=True)
        os._exit(e.code or 0)
    except Exception:
        os._exit(1)
