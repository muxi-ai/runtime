#!/usr/bin/env python3
"""Debug script to check for background tasks."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation

async def debug_with_cleanup():
    """Load formation and check for background tasks."""
    print("="*60)
    print("DEBUG: Background Tasks Check")
    print("="*60)

    try:
        print("\n[1] Creating and loading formation...")
        formation = Formation()
        formation_path = Path(__file__).parent / "formation-api"

        # Load with logging
        await formation.load(str(formation_path))
        print("✅ Formation loaded successfully\n")

        # Check for running tasks
        print("[2] Checking for background tasks...")
        loop = asyncio.get_event_loop()
        all_tasks = asyncio.all_tasks(loop)
        print(f"   Total async tasks: {len(all_tasks)}")

        for i, task in enumerate(all_tasks, 1):
            if not task.done():
                print(f"   Task {i}: {task.get_name()} - {task.get_coro()}")

        # Explicitly stop formation
        print("\n[3] Stopping formation...")
        await formation.stop()
        print("✅ Formation stopped\n")

        # Check tasks again
        print("[4] Checking tasks after stop...")
        all_tasks = asyncio.all_tasks(loop)
        print(f"   Total async tasks: {len(all_tasks)}")

        for i, task in enumerate(all_tasks, 1):
            if not task.done():
                print(f"   Task {i}: {task.get_name()} - {task.get_coro()}")

        print("\n" + "="*60)
        print("✅ DEBUG COMPLETE")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\nStarting background task debug...\n")

    # Use asyncio.run which should clean up tasks
    try:
        success = asyncio.run(debug_with_cleanup())
        print("\n✅ Process exiting cleanly")
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
        sys.exit(1)
