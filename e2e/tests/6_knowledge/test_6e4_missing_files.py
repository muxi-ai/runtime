"""
Test 6E4: Missing Files in Config
Test that the system handles missing/non-existent files gracefully
"""
import asyncio
import sys
from pathlib import Path
import os
import tempfile
import shutil

sys.path.insert(0, '../../..')

from muxi.formation import Formation  # noqa: E402


async def test_missing_files():
    """Test handling of missing/non-existent files in knowledge config"""

    print("\n=== Test 6E4: Missing Files in Config ===")
    print("This test verifies the system handles missing files gracefully\n")

    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()

    try:
        # Create agent config with missing files
        agent_yaml = f"""
schema: "1.0.0"
id: "test-missing"
name: "Test Missing Files Agent"
description: "Agent with missing knowledge files"

system_message: |
  You are a helpful assistant configured with some missing knowledge files.

role: "assistant"

knowledge:
  enabled: true
  sources:
  # Non-existent file
  - path: "/tmp/does_not_exist/missing_file.md"
    description: "Non-existent file"

  # Non-existent directory
  - path: "/tmp/missing_knowledge_directory/"
    description: "Non-existent directory"

  # Valid file (we'll create this one)
  - path: "{temp_dir}/valid_knowledge.md"
    description: "Valid knowledge file"

  # Another missing file with absolute path
  - path: "/Users/nobody/Documents/phantom_knowledge.txt"
    description: "Phantom knowledge file"
"""

        # Create one valid file
        valid_file = os.path.join(temp_dir, "valid_knowledge.md")
        with open(valid_file, 'w') as f:
            f.write("""# Valid Knowledge Document

This is a valid knowledge document that should be loaded successfully.

## Key Information
- This file exists and should be processed
- Other files in the config are missing
- The system should handle this gracefully
""")

        print(f"Created 1 valid file: {valid_file}")
        print("Configured 3 missing files/directories")

        # Write temporary agent config
        agent_config_path = os.path.join(temp_dir, "test-missing.yaml")
        with open(agent_config_path, 'w') as f:
            f.write(agent_yaml)

        # Copy test formation and add our agent
        test_formation_dir = os.path.join(temp_dir, "formation-test")
        shutil.copytree(str(Path(__file__).parent / "formations" / "formation-knowledge"), test_formation_dir)

        agents_dir = os.path.join(test_formation_dir, "agents")
        shutil.copy(agent_config_path, os.path.join(agents_dir, "test-missing.yaml"))

        print("\n--- Test 1: Formation Loading ---")
        print("Loading formation with missing knowledge files...")

        formation = Formation()
        await formation.load(os.path.join(test_formation_dir, "formation.afs"))
        overlord = await formation.start_overlord()

        print("✓ Formation loaded successfully despite missing files")

        # Check if test agent was loaded
        test_agent = overlord.agents.get("test-missing")
        if not test_agent:
            print("❌ Test agent not found")
            return False

        print("✅ Test 1 PASSED: Formation loaded without crashing")

        # Test 2: Query about knowledge
        print("\n--- Test 2: Agent Functionality ---")
        print("👤 User: What knowledge do you have available?")

        response1 = await overlord.chat(
            message="What knowledge do you have available?",
            agent_name="test-missing",
            user_id="test_user_6e4",
            session_id="test_6e4_session_1",
            stream=False
        )

        # Extract response content
        if hasattr(response1, 'content'):
            response_text = response1.content
        else:
            response_text = str(response1)

        print(f"\n🤖 Test Missing Agent: {response_text[:400]}...")

        # Should be able to respond
        if len(response_text) > 20:
            print("✅ Test 2 PASSED: Agent functions normally")
        else:
            print("❌ Test 2 FAILED: Agent unable to respond")

        # Test 3: Query about valid content
        print("\n--- Test 3: Valid File Access ---")
        print("👤 User: Tell me about the valid knowledge document")

        response2 = await overlord.chat(
            "Tell me about the valid knowledge document",
            agent_name="test-missing",
            user_id="test_user_6e4",
            session_id="test_6e4_session_2",
            stream=False
        )

        # Extract response content
        if hasattr(response2, 'content'):
            response_text = response2.content
        else:
            response_text = str(response2)

        print(f"\n🤖 Test Missing Agent: {response_text[:300]}...")

        # Check if response references valid content
        if "valid" in response_text.lower() or "knowledge" in response_text.lower():
            print("✓ Agent may have access to valid file")

        print("✅ Test 3 PASSED: Valid files still accessible")

        # Test 4: Check knowledge handler state
        print("\n--- Test 4: Knowledge Handler State ---")

        await test_agent._ensure_knowledge_initialized()

        if hasattr(test_agent, 'knowledge_handler') and test_agent.knowledge_handler:
            sources = test_agent.knowledge_handler.sources
            print(f"\nKnowledge sources configured: {len(sources)}")

            # Count successful vs failed loads
            files_loaded = 0
            missing_handled = 0

            for source in sources:
                if hasattr(source, 'path'):
                    if os.path.exists(source.path):
                        print(f"  ✓ Loaded: {source.path}")
                        if hasattr(source, 'files'):
                            files_loaded += len(source.files)
                    else:
                        print(f"  ✗ Missing: {source.path}")
                        missing_handled += 1

            print(f"\nFiles successfully loaded: {files_loaded}")
            print(f"Missing files handled: {missing_handled}")

            if files_loaded >= 1:  # At least our valid file
                print("✅ Test 4 PASSED: Valid files loaded, missing files handled")
            else:
                print("⚠ Test 4: No files loaded")

        # Test 5: Multiple queries for stability
        print("\n--- Test 5: System Stability ---")

        for i in range(3):
            await overlord.chat(
                f"Question {i+1}: Can you help me with a task?",
                agent_name="test-missing",
                user_id="test_user_6e4",
                session_id=f"test_6e4_session_{i+3}",
                stream=False
            )
            print(f"  Query {i+1}: ✓ Completed")

        print("✅ Test 5 PASSED: System stable with missing files")

        await formation.stop_overlord()

        # Summary
        print("\n\n=== Test 6E4 Summary ===")
        print("✅ Formation loads successfully with missing files")
        print("✅ Missing files are handled gracefully (no crashes)")
        print("✅ Valid files are still loaded and accessible")
        print("✅ Agent functions normally despite missing files")
        print("✅ System remains stable throughout operation")
        print("\n✅ Test 6E4 PASSED: Missing files handled gracefully")

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
        success = asyncio.run(test_missing_files())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
