#!/usr/bin/env python3
"""Test with forced exit using os._exit()"""

import asyncio
import sys
import os
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest

class TestForceExit(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_force_exit",
            test_description="Test with forced exit",
            test_area="19_api",
        )

    async def run_test(self):
        try:
            print("Setting up...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            await self.formation.start_server(block=False)
            print("✅ Server started")
            
            print("Cleaning up...")
            await self.cleanup_formation()
            print("✅ Cleanup complete")
            return 0
        except Exception as e:
            print(f"❌ Error: {e}")
            return 1

def force_exit_handler(signum, frame):
    print("\n⏰ Force exiting after 2s...")
    os._exit(0)

async def main():
    # Set a 2-second timer after asyncio.run completes
    test = TestForceExit()
    result = await test.run_test()
    return result

if __name__ == "__main__":
    # Run test
    exit_code = asyncio.run(main())
    print(f"\n✅ Test completed with code {exit_code}")
    print("Exiting with os._exit()...")
    
    # Force exit immediately - don't wait for anything
    os._exit(exit_code)
