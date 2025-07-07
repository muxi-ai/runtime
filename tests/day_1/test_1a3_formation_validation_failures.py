"""
Debug test to understand formation loading issues.
"""
import traceback
import asyncio
from muxi.runtime.formation import Formation


async def test_debug_loading():
    """Debug formation loading step by step"""
    print("\n=== Starting debug test ===")
    
    try:
        formation = Formation()
        print("✓ Formation instance created")
        
        print("Loading formation...")
        await formation.load("test-formations/formation-basic/")
        print("✓ Formation loaded successfully!")
        
        print(f"Formation ID: {formation.formation_id}")
        print(f"Config keys: {list(formation.config.keys()) if formation.config else 'None'}")
        
        # Check what was loaded
        if formation._agents_config:
            print(f"Agents loaded: {len(formation._agents_config)}")
            for agent in formation._agents_config:
                print(f"  - Agent: {agent.get('id', 'unknown')}")
        
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(test_debug_loading())