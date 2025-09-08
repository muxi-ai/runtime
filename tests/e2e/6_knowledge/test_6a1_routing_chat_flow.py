"""
Test 6A1 Routing: Test knowledge loading through chat WITHOUT specifying agent
Modified version of Test 6A1 to verify overlord routing
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '../../..')

from muxi.formation import Formation  # noqa: E402


async def test_knowledge_with_routing():
    """Test knowledge system with overlord routing"""

    print("\n=== Test 6A1 Routing: Knowledge Loading with Overlord Routing ===")

    # Load formation
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-knowledge" / "formation.yaml"))
    overlord = await formation.start_overlord()

    print("\n✓ Formation loaded successfully")

    # Test 1: FAQ question (should route to automaze)
    print("\n--- Test 1: FAQ Knowledge ---")
    response1 = await overlord.chat(
        "What services does Automaze offer?",
        user_id="test_user",
        session_id="test_session_faq",
        stream=False
    )

    print("\n👤 User: What services does Automaze offer?")

    if isinstance(response1, dict):
        agent_used = response1.get('agent_id', 'unknown')
        response_text = response1.get('response', '')
        if hasattr(response_text, 'content'):
            response_text = response_text.content
    else:
        agent_used = 'unknown'
        response_text = str(response1)

    print(f"🤖 Routed to: {agent_used}")
    print(f"🤖 Response: {response_text[:500]}...")

    # Verify it routed correctly and used knowledge
    assert agent_used == "automaze", f"Should route to automaze, but routed to {agent_used}"
    assert len(response_text) > 100, "Response too short - knowledge likely not used"
    assert "automaze" in response_text.lower(), "Response should mention Automaze"

    print("\n✅ Test 1 passed: Routed to automaze and used FAQ knowledge")

    # Test 2: Pricing question (should route to muxi)
    print("\n--- Test 2: Pricing Knowledge ---")
    response2 = await overlord.chat(
        "What pricing plans does MUXI offer?",
        user_id="test_user",
        session_id="test_session_pricing",
        stream=False
    )

    print("\n👤 User: What pricing plans does MUXI offer?")

    if isinstance(response2, dict):
        agent_used = response2.get('agent_id', 'unknown')
        response_text = response2.get('response', '')
        if hasattr(response_text, 'content'):
            response_text = response_text.content
    else:
        agent_used = 'unknown'
        response_text = str(response2)

    print(f"🤖 Routed to: {agent_used}")
    print(f"🤖 Response: {response_text[:500]}...")

    # Verify it routed correctly and used knowledge
    assert agent_used == "muxi", f"Should route to muxi, but routed to {agent_used}"
    assert len(response_text) > 100, "Response too short - knowledge likely not used"

    # Check for pricing keywords
    pricing_keywords = ["basic", "professional", "enterprise", "tier", "plan", "price", "$"]
    keywords_found = sum(1 for kw in pricing_keywords if kw.lower() in response_text.lower())
    assert keywords_found >= 2, f"Should contain pricing info, found {keywords_found} pricing keywords"

    print("\n✅ Test 2 passed: Routed to muxi and used pricing knowledge")

    # Test 3: PDF content question (should route to automaze)
    print("\n--- Test 3: PDF Knowledge ---")
    response3 = await overlord.chat(
        "What is the Automaze platform architecture?",
        user_id="test_user",
        session_id="test_session_pdf",
        stream=False
    )

    print("\n👤 User: What is the Automaze platform architecture?")

    if isinstance(response3, dict):
        agent_used = response3.get('agent_id', 'unknown')
        response_text = response3.get('response', '')
        if hasattr(response_text, 'content'):
            response_text = response_text.content
    else:
        agent_used = 'unknown'
        response_text = str(response3)

    print(f"🤖 Routed to: {agent_used}")
    print(f"🤖 Response: {response_text[:500]}...")

    # Verify routing and knowledge use
    assert agent_used == "automaze", f"Should route to automaze, but routed to {agent_used}"
    assert len(response_text) > 100, "Response too short - knowledge likely not used"

    print("\n✅ Test 3 passed: Routed to automaze and used PDF knowledge")

    await formation.stop_overlord()

    print("\n\n=== All Tests Passed ===")
    print("✅ Overlord correctly routes queries to appropriate agents")
    print("✅ Agents successfully use their knowledge bases")
    print("✅ Knowledge from different sources (FAQ, MD, PDF) is accessible")

    return True


def main():
    try:
        success = asyncio.run(test_knowledge_with_routing())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
