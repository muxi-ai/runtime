"""
Test 6A2: Absolute Path Knowledge Loading
Verify agents load knowledge from absolute paths
"""
import asyncio
import os
from pathlib import Path
from muxi.runtime.formation import Formation


def test_absolute_path_knowledge_loading():
    """Test that agents load knowledge from absolute paths"""
    
    async def run_test():
        try:
            print("\n=== Test 6A2: Absolute Path Knowledge Loading ===")
            
            # Load the test formation with knowledge
            print("Loading formation with knowledge configuration...")
            formation = Formation()
            await formation.load("test-formations/formation-knowledge/formation.yaml")
            
            # Start the overlord
            print("Starting overlord...")
            overlord = await formation.start_overlord()
            
            # Get the agents
            print("\nChecking agent knowledge with absolute paths...")
            
            # Check Automaze agent - should have absolute path PDF
            automaze_agent = overlord.agents.get("automaze")
            assert automaze_agent is not None, "Automaze agent not found"
            print(f"✓ Found Automaze agent: {automaze_agent.name}")
            
            # Initialize knowledge handler (it's lazy loaded)
            await automaze_agent._ensure_knowledge_initialized()
            
            # Check knowledge sources for absolute path
            sources = automaze_agent.knowledge_handler.sources
            print(f"\nAutomaze knowledge sources: {len(sources)} found")
            
            # Should have an absolute path PDF
            absolute_path_found = False
            pdf_found = False
            
            for source in sources:
                print(f"  - {source.path} ({source.description})")
                # Check if path is absolute
                if os.path.isabs(source.path):
                    absolute_path_found = True
                    print(f"    ✓ Absolute path detected: {source.path}")
                if source.path.endswith(".pdf"):
                    pdf_found = True
                    print(f"    ✓ PDF file detected: {os.path.basename(source.path)}")
            
            assert absolute_path_found, "No absolute path found in Automaze knowledge sources"
            assert pdf_found, "PDF file not found in Automaze knowledge sources"
            print("✓ Absolute path PDF loaded successfully")
            
            # Test that absolute path knowledge is accessible
            print("\n\nTesting absolute path knowledge access via chat...")
            
            # Test query that might use the PDF knowledge
            response_stream = await overlord.chat(
                "Tell me about Ran's background or bio",
                user_id="test_user_6a2"
            )
            
            # Collect the streaming response
            response = ""
            async for chunk in response_stream:
                response += chunk
            
            print(f"\n👤 User: Tell me about Ran's background or bio")
            print(f"🤖 Overlord: {response[:200]}..." if len(response) > 200 else f"🤖 Overlord: {response}")
            
            # Should have some response (PDF might not be accessible if path doesn't exist)
            assert len(response) > 50, "Response should be meaningful"
            print("✓ Agent processed query (absolute path knowledge may or may not exist)")
            
            # Verify path resolution
            print("\n\nVerifying path resolution logic...")
            
            # Get formation directory
            formation_dir = Path(formation._formation_path)
            knowledge_dir = formation_dir / "knowledge"
            
            print(f"Formation directory: {formation_dir}")
            print(f"Knowledge directory: {knowledge_dir}")
            
            # Check that relative paths would resolve to knowledge dir
            for source in sources:
                if not os.path.isabs(source.path):
                    expected_base = str(knowledge_dir)
                    # The source path should start with the knowledge directory
                    assert expected_base in source.path or source.path.startswith("faq"), \
                        f"Relative path {source.path} not properly resolved"
                    print(f"✓ Relative path properly resolved: {source.path}")
                else:
                    # Absolute paths should remain unchanged
                    assert source.path.startswith("/"), f"Absolute path {source.path} was modified"
                    print(f"✓ Absolute path unchanged: {source.path}")
            
            # Stop the overlord
            await formation.stop_overlord()
            print("\n✅ Test 6A2 passed: Absolute path knowledge loading verified")
            
        except Exception as e:
            print(f"\n❌ Test 6A2 failed: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    # Run the async test
    asyncio.run(run_test())


if __name__ == "__main__":
    test_absolute_path_knowledge_loading()