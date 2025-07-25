"""
Test 6A1: Relative Path Knowledge Loading
Verify agents load knowledge from relative paths during initialization
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from muxi.runtime.formation import Formation


def test_relative_path_knowledge_loading():
    """Test that agents load knowledge from relative paths during initialization"""
    
    async def run_test():
        try:
            print("\n=== Test 6A1: Relative Path Knowledge Loading ===")
            
            # Load the test formation with knowledge
            print("Loading formation with knowledge configuration...")
            formation = Formation()
            await formation.load("test-formations/formation-knowledge/formation.yaml")
            
            # Start the overlord
            print("Starting overlord...")
            overlord = await formation.start_overlord()
            
            # Get the agents
            print("\nChecking agent knowledge handlers...")
            
            # Check Automaze agent
            automaze_agent = overlord.agents.get("automaze")
            
            assert automaze_agent is not None, "Automaze agent not found"
            print(f"✓ Found Automaze agent: {automaze_agent.name}")
            
            # Initialize knowledge handler (it's lazy loaded)
            await automaze_agent._ensure_knowledge_initialized()
            
            # Check knowledge handler exists
            assert hasattr(automaze_agent, 'knowledge_handler'), "Automaze agent missing knowledge_handler"
            assert automaze_agent.knowledge_handler is not None, "Automaze agent knowledge_handler is None"
            print("✓ Automaze agent has knowledge handler")
            
            # Check knowledge sources
            sources = automaze_agent.knowledge_handler.sources
            print(f"\nAutomaze knowledge sources: {len(sources)} found")
            
            # Should have FAQ directory loaded
            faq_found = False
            pdf_found = False
            
            for source in sources:
                print(f"  - {source.path} ({source.description})")
                if "faq" in source.path:
                    faq_found = True
                if "ran-bio.pdf" in source.path:
                    pdf_found = True
            
            assert faq_found, "FAQ directory not found in Automaze knowledge sources"
            print("✓ FAQ directory loaded (relative path)")
            
            # Check MUXI agent
            muxi_agent = overlord.agents.get("muxi")
            
            assert muxi_agent is not None, "MUXI agent not found"
            print(f"\n✓ Found MUXI agent: {muxi_agent.name}")
            
            # Initialize knowledge handler (it's lazy loaded)
            await muxi_agent._ensure_knowledge_initialized()
            
            # Check knowledge handler
            assert hasattr(muxi_agent, 'knowledge_handler'), "MUXI agent missing knowledge_handler"
            assert muxi_agent.knowledge_handler is not None, "MUXI agent knowledge_handler is None"
            print("✓ MUXI agent has knowledge handler")
            
            # Check MUXI knowledge sources
            muxi_sources = muxi_agent.knowledge_handler.sources
            print(f"\nMUXI knowledge sources: {len(muxi_sources)} found")
            
            business_plan_found = False
            pricing_found = False
            
            for source in muxi_sources:
                print(f"  - {source.path} ({source.description})")
                if "muxi-business-plan.md" in source.path:
                    business_plan_found = True
                if "muxi-pricing.md" in source.path:
                    pricing_found = True
            
            assert business_plan_found, "Business plan not found in MUXI knowledge sources"
            assert pricing_found, "Pricing doc not found in MUXI knowledge sources"
            print("✓ Business plan and pricing docs loaded (relative paths)")
            
            # Test that knowledge is accessible via chat
            print("\n\nTesting knowledge access via chat...")
            
            # Test Automaze FAQ knowledge
            response_stream = await overlord.chat(
                "What services does Automaze offer?",
                user_id="test_user_6a1"
            )
            
            # Collect the streaming response
            response = ""
            async for chunk in response_stream:
                response += chunk
            
            print(f"\n👤 User: What services does Automaze offer?")
            print(f"🤖 Overlord: {response}")
            
            # Should route to Automaze agent and use FAQ knowledge
            assert "automaze" in response.lower(), "Response should mention Automaze"
            assert len(response) > 100, "Response should be detailed from knowledge"
            print("✓ Automaze agent used FAQ knowledge")
            
            # Stop the overlord
            await formation.stop_overlord()
            print("\n✅ Test 6A1 passed: Relative path knowledge loading verified")
            
        except Exception as e:
            print(f"\n❌ Test 6A1 failed: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    # Run the async test
    asyncio.run(run_test())


if __name__ == "__main__":
    test_relative_path_knowledge_loading()