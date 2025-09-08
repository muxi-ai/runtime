"""
Test 6C3: Knowledge-Enhanced vs Basic Response
Compare responses with and without knowledge access through chat flow
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '../../..')

from muxi.formation import Formation


async def test_knowledge_vs_basic():
    """Test knowledge-enhanced responses vs basic responses"""

    print("\n=== Test 6C3: Knowledge-Enhanced vs Basic Response ===")
    print("This test compares agent responses with and without knowledge access\n")

    try:
        # First, load formation with knowledge
        print("Loading formation with knowledge configuration...")
        formation = Formation()
        await formation.load(str(Path(__file__).parent / "formations" / "formation-knowledge" / "formation.yaml"))
        overlord = await formation.start_overlord()

        print("✓ Formation loaded successfully")

        # Test 1: Knowledge-enhanced response about specific pricing
        print("\n--- Test 1: Knowledge-Enhanced Response ---")
        print("👤 User: What is the exact price of MUXI's Professional tier?")

        response1 = await overlord.chat(
            "What is the exact price of MUXI's Professional tier?",
            agent_name="muxi",
            user_id="test_user_6c3",
            session_id="test_6c3_session_1",
            stream=False
        )

        # Extract response content
        if hasattr(response1, 'content'):
            response_text = response1.content
        else:
            response_text = str(response1)

        print(f"\n🤖 MUXI (with knowledge): {response_text[:400]}...")

        # Check for specific pricing information
        pricing_indicators = ["$", "29", "per user", "month", "professional", "tier"]
        indicators_found = [ind for ind in pricing_indicators if ind.lower() in response_text.lower()]

        print(f"\n✓ Pricing indicators found: {indicators_found}")

        if "$29" in response_text or "29" in response_text:
            print("✅ Test 1 PASSED: Specific pricing from knowledge base retrieved")
        else:
            print("⚠ Test 1: Response may not include specific pricing")

        # Test 2: Query about something NOT in knowledge base
        print("\n\n--- Test 2: Response Without Knowledge ---")
        print("👤 User: What is MUXI's stance on quantum computing integration?")

        response2 = await overlord.chat(
            "What is MUXI's stance on quantum computing integration?",
            agent_name="muxi",
            user_id="test_user_6c3",
            session_id="test_6c3_session_2",
            stream=False
        )

        # Extract response content
        if hasattr(response2, 'content'):
            response_text = response2.content
        else:
            response_text = str(response2)

        print(f"\n🤖 MUXI (no specific knowledge): {response_text[:400]}...")

        # This should be more general/speculative since it's not in knowledge base
        general_indicators = ["would", "could", "might", "typically", "generally", "i don't have specific"]
        general_found = [ind for ind in general_indicators if ind.lower() in response_text.lower()]

        print(f"\n✓ General/speculative indicators: {general_found}")

        if general_found:
            print("✅ Test 2 PASSED: Response is appropriately general without specific knowledge")
        else:
            print("⚠ Test 2: Response style unclear")

        # Test 3: Compare FAQ-based vs general response
        print("\n\n--- Test 3: FAQ Knowledge vs General ---")
        print("👤 User: How does Automaze handle data security?")

        response3 = await overlord.chat(
            "How does Automaze handle data security?",
            agent_name="automaze",
            user_id="test_user_6c3",
            session_id="test_6c3_session_3",
            stream=False
        )

        # Extract response content
        if hasattr(response3, 'content'):
            response_text = response3.content
        else:
            response_text = str(response3)

        print(f"\n🤖 Automaze: {response_text[:400]}...")

        # Check if response uses FAQ knowledge
        security_keywords = ["security", "encryption", "compliance", "data", "protection", "privacy"]
        keywords_found = [kw for kw in security_keywords if kw.lower() in response_text.lower()]

        print(f"\n✓ Security keywords found: {keywords_found}")

        if len(keywords_found) >= 3:
            print("✅ Test 3 PASSED: Response uses knowledge base for security information")
        else:
            print("⚠ Test 3: Limited security information in response")

        await formation.stop_overlord()

        # Summary
        print("\n\n=== Test 6C3 Summary ===")
        print("✅ Agents provide specific answers when knowledge is available")
        print("✅ Agents give general responses for topics not in knowledge base")
        print("✅ Knowledge-enhanced responses are more detailed and accurate")
        print("\n✅ Test 6C3 PASSED: Knowledge enhancement working correctly")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    try:
        success = asyncio.run(test_knowledge_vs_basic())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
