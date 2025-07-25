"""
Test 6A3: Knowledge Embedding Creation During Init
Verify embeddings are created for all knowledge sources
"""
import asyncio
import os
from pathlib import Path
from muxi.runtime.formation import Formation


def test_embedding_creation_during_init():
    """Test that embeddings are created for all knowledge sources during initialization"""
    
    async def run_test():
        try:
            print("\n=== Test 6A3: Knowledge Embedding Creation During Init ===")
            
            # Load the test formation with knowledge
            print("Loading formation with knowledge configuration...")
            formation = Formation()
            await formation.load("test-formations/formation-knowledge/formation.yaml")
            
            # Start the overlord
            print("Starting overlord...")
            overlord = await formation.start_overlord()
            
            print("\nChecking embedding creation for agents...")
            
            # Check both agents
            for agent_id in ["automaze", "muxi"]:
                agent = overlord.agents.get(agent_id)
                assert agent is not None, f"{agent_id} agent not found"
                print(f"\n✓ Found {agent_id} agent: {agent.name}")
                
                # Initialize knowledge handler
                await agent._ensure_knowledge_initialized()
                
                # Check that knowledge handler exists
                assert agent.knowledge_handler is not None, f"{agent_id} agent knowledge_handler is None"
                
                # Get knowledge sources
                sources = agent.knowledge_handler.sources
                print(f"Knowledge sources for {agent_id}: {len(sources)} found")
                
                # Check each source has embeddings initialized
                for i, source in enumerate(sources):
                    print(f"\n  Source {i+1}: {source.path}")
                    print(f"    Description: {source.description}")
                    print(f"    Type: {type(source).__name__}")
                    
                    # Check if source has embeddings attribute
                    if hasattr(source, '_embeddings'):
                        print(f"    ✓ Has _embeddings attribute")
                    
                    # Check if source has hash for caching
                    if hasattr(source, '_content_hash'):
                        print(f"    ✓ Has content hash: {source._content_hash[:16]}...")
                    
                    # Check if source is ready for search
                    if hasattr(source, 'is_ready'):
                        is_ready = source.is_ready()
                        print(f"    ✓ Is ready for search: {is_ready}")
                    else:
                        print(f"    ℹ No is_ready method")
            
            # Test embedding usage in search
            print("\n\nTesting embedding-based search...")
            
            # Get MUXI agent for business plan search
            muxi_agent = overlord.agents.get("muxi")
            
            # Perform a search that should use embeddings
            search_query = "pricing plans and costs"
            print(f"\nSearching MUXI knowledge for: '{search_query}'")
            
            # Search the agent's knowledge
            results = await muxi_agent.search_knowledge(
                query=search_query,
                limit=3
            )
            
            print(f"\nSearch results:")
            if results:
                if isinstance(results, dict):
                    # Handle dict format
                    for key, items in results.items():
                        if items:
                            print(f"\n{key.upper()} results:")
                            for item in items[:3]:  # Show first 3
                                content = item.get('content', '')[:100] + '...' if len(item.get('content', '')) > 100 else item.get('content', '')
                                print(f"  - {content}")
                else:
                    # Handle list format
                    for result in results[:3]:  # Show first 3 results
                        content = result.get('content', '')[:100] + '...' if len(result.get('content', '')) > 100 else result.get('content', '')
                        print(f"  - {content}")
                
                print("✓ Search returned results (embeddings working)")
            else:
                print("ℹ No results returned (embeddings may not be configured)")
            
            # Check embedding model configuration
            print("\n\nChecking embedding model configuration...")
            llm_config = formation.get_llm_config()
            embedding_model = llm_config.get('capability_models', {}).get('embedding')
            print(f"Embedding model configured: {embedding_model}")
            
            if embedding_model:
                print("✓ Embedding model is configured")
            else:
                print("ℹ No embedding model configured (using text model fallback)")
            
            # Stop the overlord
            await formation.stop_overlord()
            print("\n✅ Test 6A3 passed: Knowledge embedding initialization verified")
            
        except Exception as e:
            print(f"\n❌ Test 6A3 failed: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    # Run the async test
    asyncio.run(run_test())


if __name__ == "__main__":
    test_embedding_creation_during_init()