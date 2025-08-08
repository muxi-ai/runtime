"""Clear buffer memory before testing."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.muxi import Formation


async def clear_buffer():
    try:
        print("Loading formation...")
        formation_path = Path(__file__).parent / "test-formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        print("Clearing buffer memory...")
        if overlord.buffer_memory_manager:
            # Clear the buffer for test user
            await overlord.buffer_memory_manager.clear_buffer_memory(
                filter_metadata={"user_id": "test_user"}
            )
            print("✅ Buffer memory cleared for test_user")
        else:
            print("No buffer memory manager configured")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure we exit cleanly
        import sys
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(clear_buffer())