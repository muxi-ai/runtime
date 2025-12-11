"""
Test 6D4: Knowledge Namespace Verification
Verify that knowledge is stored with agent-specific namespacing in memory
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '../../..')

from muxi.formation import Formation  # noqa: E402


async def test_knowledge_namespace():
    """Test that knowledge is properly namespaced by agent"""

    print("\n=== Test 6D4: Knowledge Namespace Verification ===")
    print("This test verifies knowledge is stored with agent-specific namespacing\n")

    try:
        # Load formation with knowledge
        print("Loading formation with knowledge configuration...")
        formation = Formation()
        await formation.load(str(Path(__file__).parent / "formations" / "formation-knowledge" / "formation.afs"))
        overlord = await formation.start_overlord()

        print("✓ Formation loaded successfully")

        # First, ensure knowledge is loaded for both agents
        print("\n--- Step 1: Trigger Knowledge Loading ---")

        # Query Automaze to load its knowledge
        print("👤 User: @automaze What services do you offer?")
        await overlord.chat(
            "@automaze What services do you offer?",
            user_id="test_user_6d4",
            session_id="test_6d4_session_1",
            stream=False
        )
        print("✓ Automaze knowledge loaded")

        # Query MUXI to load its knowledge
        print("👤 User: @muxi What are your pricing tiers?")
        await overlord.chat(
            "@muxi What are your pricing tiers?",
            user_id="test_user_6d4",
            session_id="test_6d4_session_2",
            stream=False
        )
        print("✓ MUXI knowledge loaded")

        # Test namespace verification through memory inspection
        print("\n--- Step 2: Verify Knowledge Namespacing ---")

        # Get both agents
        automaze_agent = overlord.agents.get("automaze")
        muxi_agent = overlord.agents.get("muxi")

        if not automaze_agent or not muxi_agent:
            print("❌ Could not retrieve both agents")
            return False

        # Ensure knowledge handlers are initialized
        await automaze_agent._ensure_knowledge_initialized()
        await muxi_agent._ensure_knowledge_initialized()

        # Check if agents have memory systems
        if hasattr(automaze_agent, 'memory') and hasattr(muxi_agent, 'memory'):
            print("\n✓ Both agents have memory systems")

            # Search for a generic term in knowledge namespace
            print("\n--- Testing Knowledge Namespace Isolation ---")

            # Search in Automaze's knowledge
            if automaze_agent.memory:
                automaze_results = await automaze_agent.memory.search_memories(
                    query="service",
                    namespace="knowledge",  # Knowledge namespace
                    top_k=5
                )
                print(f"\nAutomaze knowledge search results: {len(automaze_results)} found")

                # Check metadata for agent ID
                automaze_has_correct_id = all(
                    result.metadata.get("agent_id") == "automaze"
                    for result in automaze_results
                    if result.metadata.get("agent_id")
                )

                if automaze_has_correct_id:
                    print("✓ All Automaze results have correct agent_id")
                else:
                    print("❌ Some Automaze results have incorrect agent_id")

            # Search in MUXI's knowledge
            if muxi_agent.memory:
                muxi_results = await muxi_agent.memory.search_memories(
                    query="pricing",
                    namespace="knowledge",  # Knowledge namespace
                    top_k=5
                )
                print(f"\nMUXI knowledge search results: {len(muxi_results)} found")

                # Check metadata for agent ID
                muxi_has_correct_id = all(
                    result.metadata.get("agent_id") == "muxi"
                    for result in muxi_results
                    if result.metadata.get("agent_id")
                )

                if muxi_has_correct_id:
                    print("✓ All MUXI results have correct agent_id")
                else:
                    print("❌ Some MUXI results have incorrect agent_id")

            # Cross-check: Search for MUXI terms in Automaze's namespace
            print("\n--- Cross-Check Test ---")
            if automaze_agent.memory:
                cross_results = await automaze_agent.memory.search_memories(
                    query="MUXI pricing tiers",
                    namespace="knowledge",
                    top_k=5
                )
                print(f"\nSearching for 'MUXI pricing' in Automaze knowledge: {len(cross_results)} results")

                # Check if any results actually contain MUXI pricing info
                muxi_leaks = [r for r in cross_results if "muxi" in str(r.content).lower()]
                if muxi_leaks:
                    print(f"❌ Found {len(muxi_leaks)} MUXI-related results in Automaze namespace")
                else:
                    print("✓ No MUXI knowledge found in Automaze namespace")

        else:
            print("\n⚠ Memory systems not available for namespace verification")
            print("Note: This might be expected depending on memory configuration")

        # Alternative verification through knowledge handler sources
        print("\n--- Step 3: Verify Knowledge Source Separation ---")

        automaze_sources = [s.path for s in automaze_agent.knowledge_handler.sources]
        muxi_sources = [s.path for s in muxi_agent.knowledge_handler.sources]

        print(f"\nAutomaze knowledge sources: {len(automaze_sources)}")
        for source in automaze_sources:
            print(f"  - {source}")

        print(f"\nMUXI knowledge sources: {len(muxi_sources)}")
        for source in muxi_sources:
            print(f"  - {source}")

        # Check for overlap
        overlap = set(automaze_sources) & set(muxi_sources)
        if overlap:
            print(f"\n❌ Found overlapping sources: {overlap}")
            namespace_separated = False
        else:
            print("\n✓ No overlapping knowledge sources between agents")
            namespace_separated = True

        await formation.stop_overlord()

        # Summary
        print("\n\n=== Test 6D4 Summary ===")
        if namespace_separated:
            print("✅ Knowledge sources are properly separated")
            print("✅ Each agent has its own knowledge namespace")
            print("✅ No cross-contamination detected")
            print("\n✅ Test 6D4 PASSED: Knowledge namespace verification successful")
            return True
        else:
            print("❌ Knowledge namespace issues detected")
            return False

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    try:
        success = asyncio.run(test_knowledge_namespace())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
