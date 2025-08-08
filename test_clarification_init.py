"""Quick test to check if clarification system is initialized."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.muxi import Formation


async def test():
    try:
        print("Loading formation...")
        formation_path = Path(__file__).parent / "test-formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Check if clarification components are initialized
        print(f"\n=== Clarification System Check ===")
        print(f"Has information_analyzer: {hasattr(overlord, 'information_analyzer')}")
        if hasattr(overlord, 'information_analyzer'):
            print(f"  - information_analyzer is None: {overlord.information_analyzer is None}")
            if overlord.information_analyzer:
                print(f"  - Type: {type(overlord.information_analyzer)}")
        
        print(f"Has clarification_config: {hasattr(overlord, 'clarification_config')}")
        if hasattr(overlord, 'clarification_config'):
            print(f"  - clarification_config: {overlord.clarification_config}")
        
        print(f"Has _pending_clarifications: {hasattr(overlord, '_pending_clarifications')}")
        if hasattr(overlord, '_pending_clarifications'):
            print(f"  - _pending_clarifications: {overlord._pending_clarifications}")
        
        # Check other components
        components = [
            'clarification_manager',
            'question_generator',
            'response_parser',
            'parameter_enricher',
            'proactive_detector',
            'mode_manager',
            'plan_analyzer'
        ]
        
        print(f"\nOther clarification components:")
        for comp in components:
            if hasattr(overlord, comp):
                val = getattr(overlord, comp)
                print(f"  - {comp}: {'✅ Initialized' if val else '❌ None'}")
            else:
                print(f"  - {comp}: ❌ Not found")
        
        if overlord.information_analyzer:
            print("\n✅ CLARIFICATION SYSTEM INITIALIZED!")
        else:
            print("\n❌ CLARIFICATION SYSTEM NOT INITIALIZED")
            
        # Exit cleanly
        return
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())