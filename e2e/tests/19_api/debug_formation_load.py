#!/usr/bin/env python3
"""Debug script to identify where formation loading hangs."""

import asyncio
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation

async def debug_load():
    """Load formation with detailed logging."""
    print("="*60)
    print("DEBUG: Formation Loading Test")
    print("="*60)

    try:
        print("\n[1/10] Creating Formation instance...")
        formation = Formation()
        print("✅ Formation instance created")

        print("\n[2/10] Starting formation.load()...")
        formation_path = Path(__file__).parent / "formation-api"
        print(f"   Path: {formation_path}")

        # Add timeout to detect hang
        print("\n[3/10] Loading with 30s timeout...")
        try:
            await asyncio.wait_for(
                formation.load(str(formation_path)),
                timeout=30.0
            )
            print("✅ Formation loaded successfully!")

            print("\n[4/10] Checking formation state...")
            print(f"   Formation ID: {formation.formation_id}")
            print(f"   Config loaded: {formation.config is not None}")
            print(f"   Has overlord: {hasattr(formation, '_overlord')}")

        except asyncio.TimeoutError:
            print("\n❌ TIMEOUT after 30s")
            print("\nFormation state at timeout:")
            print(f"   Formation ID: {getattr(formation, 'formation_id', 'NOT SET')}")
            print(f"   Config: {formation.config is not None if hasattr(formation, 'config') else 'NO ATTR'}")
            print(f"   Is running: {getattr(formation, '_is_running', 'NOT SET')}")

            # Try to get more debug info
            if hasattr(formation, 'config') and formation.config:
                print(f"   Config keys: {list(formation.config.keys())[:10]}")

            raise

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    print("\nStarting debug session...")
    success = asyncio.run(debug_load())

    if success:
        print("\n" + "="*60)
        print("✅ DEBUG: Formation loaded successfully!")
        print("="*60)
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("❌ DEBUG: Formation loading failed")
        print("="*60)
        sys.exit(1)
