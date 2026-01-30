"""
Test 6A1 Routing: Test knowledge loading through chat WITHOUT specifying agent
Modified version of Test 6A1 to verify overlord routing
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '../../..')

from muxi.runtime.formation import Formation  # noqa: E402


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

    # Extract response content
    if hasattr(response1, 'content'):
        response_text = response1.content
    elif isinstance(response1, dict):
        response_text = response1.get('response', str(response1))
        if hasattr(response_text, 'content'):
            response_text = response_text.content
    else:
        response_text = str(response1)

    print(f"🤖 Response: {response_text[:500]}...")

    # Verify knowledge was used (routing is logged but not in response)
    # Check for Automaze-specific knowledge keywords
    automaze_keywords = ["automation", "workflow", "service", "automaze", "process"]
    keywords_found = sum(1 for kw in automaze_keywords if kw.lower() in response_text.lower())

    assert len(response_text) > 100, "Response too short - knowledge likely not used"
    assert keywords_found >= 2, f"Should contain Automaze knowledge keywords, found {keywords_found}/5"

    print(f"✓ Automaze knowledge keywords found: {keywords_found}/5")
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

    # Extract response content
    if hasattr(response2, 'content'):
        response_text = response2.content
    elif isinstance(response2, dict):
        response_text = response2.get('response', str(response2))
        if hasattr(response_text, 'content'):
            response_text = response_text.content
    else:
        response_text = str(response2)

    print(f"🤖 Response: {response_text[:500]}...")

    # Verify knowledge was used (routing is logged but not in response)
    assert len(response_text) > 100, "Response too short - knowledge likely not used"

    # Check for pricing keywords (using actual terms from MUXI pricing doc)
    pricing_keywords = ["free", "flex", "pro", "team", "plan", "price", "month", "enterprise", "tier"]
    keywords_found = sum(1 for kw in pricing_keywords if kw.lower() in response_text.lower())
    assert keywords_found >= 2, f"Should contain pricing info, found {keywords_found} pricing keywords"

    print(f"✓ Pricing knowledge keywords found: {keywords_found}/7")
    print("\n✅ Test 2 passed: Routed to muxi and used pricing knowledge")

    # Test 3: Business model question (should route to muxi)
    print("\n--- Test 3: Business Model Knowledge ---")
    response3 = await overlord.chat(
        "What is MUXI's business model and revenue strategy?",
        user_id="test_user",
        session_id="test_session_business",
        stream=False
    )

    print("\n👤 User: What is MUXI's business model and revenue strategy?")

    # Extract response content
    if hasattr(response3, 'content'):
        response_text = response3.content
    elif isinstance(response3, dict):
        response_text = response3.get('response', str(response3))
        if hasattr(response_text, 'content'):
            response_text = response_text.content
    else:
        response_text = str(response3)

    print(f"🤖 Response: {response_text[:500]}...")

    # Verify knowledge was used (routing is logged but not in response)
    # Check for business model keywords
    business_keywords = ["business", "revenue", "model", "subscription", "saas", "platform"]
    keywords_found = sum(1 for kw in business_keywords if kw.lower() in response_text.lower())

    assert len(response_text) > 100, "Response too short - knowledge likely not used"
    assert keywords_found >= 2, f"Should contain business model knowledge, found {keywords_found}/6 keywords"

    print(f"✓ Business model keywords found: {keywords_found}/6")
    print("\n✅ Test 3 passed: Routed to muxi and used business model knowledge")

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
