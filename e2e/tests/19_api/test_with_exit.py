#!/usr/bin/env python3
"""Test using sys.exit() to force clean exit."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest

class TestWithExit(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_with_exit",
            test_description="Test with forced exit",
            test_area="19_api",
        )

    async def run_test(self):
        try:
            print("Setting up formation...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            await self.formation.start_server(block=False)
            print("✅ Server started")
            
            print("Cleaning up...")
            await self.cleanup_formation()
            print("✅ Cleanup complete")
            
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False

async def main():
    test = TestWithExit()
    result = await test.run_test()
    return 0 if result else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    
    print(f"\nTest completed with code: {exit_code}")
    print("Forcing exit with sys.exit()...")
    
    # Force exit immediately - don't wait for threads
    import os; os._exit(exit_code)
