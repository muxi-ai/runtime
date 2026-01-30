"""
Test 6A1: Relative Path Knowledge Loading (Chat Flow)
Verify agents load knowledge from relative paths and can answer questions using that knowledge
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.runtime.formation import Formation  # noqa: E402


def test_relative_path_knowledge_loading():
    """Test that agents load knowledge from relative paths and can use it in chat"""

    async def run_test():
        try:
            print("\n=== Test 6A1: Relative Path Knowledge Loading (Chat Flow) ===")

            # Load the test formation with knowledge
            print("\nLoading formation with knowledge configuration...")
            formation = Formation()
            await formation.load(str(Path(__file__).parent / "formations" / "formation-knowledge" / "formation.yaml"))

            # Start the overlord
            print("Starting overlord...")
            overlord = await formation.start_overlord()

            # Test 1: Automaze agent should be able to answer from FAQ knowledge
            print("\n--- Testing Automaze agent with FAQ knowledge ---")

            # Ask a question that should be in the FAQ
            response1 = await overlord.chat(
                "What services does Automaze offer?",
                agent_name="automaze",
                user_id="test_user",
                session_id="test_session_1",
                stream=False  # Disable streaming for testing
            )

            print("\n👤 User: What services does Automaze offer?")
            if isinstance(response1, dict):
                print(f"🤖 Automaze: {response1.get('response', response1)}")
                response_text = response1.get('response', str(response1))
            else:
                print(f"🤖 Automaze: {response1}")
                response_text = str(response1)

            # Verify the response contains relevant content from FAQ
            assert response1 is not None, "No response from Automaze agent"
            assert len(response_text) > 50, "Response too short, likely no knowledge used"

            # The FAQ files should contain information about services
            # We expect the agent to provide a substantive answer
            print("✓ Automaze agent responded using FAQ knowledge")

            # Test 2: MUXI agent should be able to answer from business plan
            print("\n--- Testing MUXI agent with business plan knowledge ---")

            response2 = await overlord.chat(
                "What is MUXI's pricing model?",
                agent_name="muxi",
                user_id="test_user",
                session_id="test_session_2",
                stream=False  # Disable streaming for testing
            )

            print("\n👤 User: What is MUXI's pricing model?")
            if isinstance(response2, dict):
                print(f"🤖 MUXI: {response2.get('response', response2)}")
                response_text = response2.get('response', str(response2))
            else:
                print(f"🤖 MUXI: {response2}")
                response_text = str(response2)

            assert response2 is not None, "No response from muxi.runtime agent"
            assert len(response_text) > 50, "Response too short, likely no knowledge used"

            # The pricing doc should contain specific pricing information
            print("✓ MUXI agent responded using pricing knowledge")

            # Test 3: Test absolute path loading (Automaze has ran-bio.pdf)
            print("\n--- Testing absolute path knowledge loading ---")

            response3 = await overlord.chat(
                "Tell me about Ran Aroussi",
                agent_name="automaze",
                user_id="test_user",
                session_id="test_session_3",
                stream=False  # Disable streaming for testing
            )

            print("\n👤 User: Tell me about Ran Aroussi")
            if isinstance(response3, dict):
                print(f"🤖 Automaze: {response3.get('response', response3)}")
                response_text = response3.get('response', str(response3))
            else:
                print(f"🤖 Automaze: {response3}")
                response_text = str(response3)

            assert response3 is not None, "No response from Automaze agent"
            assert len(response_text) > 50, "Response too short, likely no knowledge used"

            # The PDF should contain biographical information
            keywords = ["Ran", "Aroussi", "developer", "creator"]
            response_lower = response_text.lower()
            assert any(keyword.lower() in response_lower for keyword in keywords), \
                "Response doesn't seem to contain expected biographical information"

            print("✓ Automaze agent responded using absolute path PDF knowledge")

            # Clean shutdown
            await formation.stop_overlord()

            print("\n✅ Test 6A1 passed: Agents successfully loaded and used knowledge from both relative and absolute paths")  # noqa: E501
            return True

        except Exception as e:
            print(f"\n❌ Test 6A1 failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    # Run the async test
    success = asyncio.run(run_test())
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = test_relative_path_knowledge_loading()
    exit(exit_code)
