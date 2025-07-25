"""
Quick test for agent knowledge isolation
"""
import asyncio
import sys

sys.path.insert(0, '../..')

from src.muxi.runtime.formation import Formation


async def quick_isolation_test():
    print("\n=== Quick Knowledge Isolation Test ===")
    
    formation = Formation()
    await formation.load("../../test-formations/formation-knowledge/formation.yaml")
    overlord = await formation.start_overlord()
    
    # Ask Automaze about MUXI pricing (should not have access)
    print("\n1. Testing: Automaze asked about MUXI pricing")
    response = await overlord.chat(
        "What are the exact pricing tiers for MUXI including the dollar amounts?",
        agent_name="automaze",  # Force routing to wrong agent
        user_id="test",
        session_id="iso1",
        stream=False
    )
    
    content = response.content if hasattr(response, 'content') else str(response)
    print(f"\nAutomaze response preview: {content[:300]}...")
    
    # Check for specific MUXI pricing details that should NOT be accessible
    has_muxi_pricing = any(keyword in content.lower() for keyword in [
        "$99", "$299", "$999", "basic tier", "professional tier", "enterprise tier"
    ])
    
    if has_muxi_pricing:
        print("❌ FAIL: Automaze has access to MUXI's knowledge!")
    else:
        print("✅ PASS: Automaze does NOT have access to MUXI's pricing knowledge")
    
    await formation.stop_overlord()
    return not has_muxi_pricing


if __name__ == "__main__":
    success = asyncio.run(quick_isolation_test())
    exit(0 if success else 1)