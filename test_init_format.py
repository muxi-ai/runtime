#!/usr/bin/env python3
"""Quick test to verify init formatting works."""

import asyncio
from src.muxi.formation.formation import Formation

async def test_init_output():
    """Test that formation initialization shows clean formatted output."""
    print("\n" + "="*80)
    print("Testing Init Event Formatting")
    print("="*80 + "\n")

    formation_path = "e2e/tests/7_orchestration/formations/formation-multi-agent-segregated/formation.yaml"

    try:
        # Initialize formation
        print("Starting formation initialization...\n")
        formation = await Formation.create(formation_path)

        print("\n" + "="*80)
        print("Init formatting test completed successfully!")
        print("="*80)

        # Cleanup
        await formation.stop_overlord()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_init_output())
