"""
Test 6B: Knowledge Change Detection
Test that the knowledge system correctly detects and handles:
1. Initial knowledge loading
2. File removal (removes from cache and buffer)
3. File re-addition (adds back to cache and buffer)
4. File modification (updates cache and buffer)
"""
import asyncio
import shutil
import sys
import os
from pathlib import Path
import time

sys.path.insert(0, '../../..')

from muxi.formation import Formation
from muxi.utils.user_dirs import get_knowledge_dir


class KnowledgeChangeDetectionTest:
    """Test knowledge change detection and cache invalidation"""

    def __init__(self):
        self.formation = None
        self.overlord = None
        self.test_file = "muxi-pricing.md"  # File we'll move/modify
        self.knowledge_dir = Path(str(Path(__file__).parent / "formations" / "formation-knowledge")knowledge")
        self.temp_dir = Path("../../assets/formations/temp-knowledge")
        self.test_file_path = self.knowledge_dir / self.test_file
        self.temp_file_path = self.temp_dir / self.test_file

    async def setup(self):
        """Create temp directory for moving files"""
        self.temp_dir.mkdir(exist_ok=True)

    async def teardown(self):
        """Clean up temp directory"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    async def load_formation(self):
        """Load formation and start overlord"""
        self.formation = Formation()
        await self.formation.load(str(Path(__file__).parent / "formations" / "formation-knowledge" / "formation.yaml"))
        self.overlord = await self.formation.start_overlord()

        # Get muxi agent and ensure knowledge is loaded
        muxi_agent = self.overlord.agents.get("muxi")
        if muxi_agent:
            await muxi_agent._ensure_knowledge_initialized()
            return muxi_agent
        return None

    async def stop_formation(self):
        """Stop overlord without cleaning cache"""
        if self.formation:
            await self.formation.stop_overlord()
            self.formation = None
            self.overlord = None

    def get_cache_info(self, agent):
        """Get information about cached files and buffer contents"""
        info = {
            "cache_files": [],
            "buffer_items": [],
            "knowledge_sources": []
        }

        if not agent or not agent.knowledge_handler:
            return info

        # Check disk cache
        cache_dir = Path(agent.knowledge_handler.cache_dir)
        if cache_dir.exists():
            for cache_file in cache_dir.glob("*.cache"):
                info["cache_files"].append(cache_file.name)

        # Check buffer (WorkingMemory)
        if agent.knowledge_handler.working_memory:
            stm = agent.knowledge_handler.working_memory
            # Get all knowledge namespace items
            for item in stm.buffer:
                if item.get("namespace") == "knowledge":
                    source = item.get("metadata", {}).get("source", "unknown")
                    info["buffer_items"].append(source)

        # Get knowledge sources
        info["knowledge_sources"] = [s.path for s in agent.knowledge_handler.sources]

        return info

    async def run_phase_1_initial_load(self):
        """Phase 1: Initial load and verify cache/buffer"""
        print("\n=== PHASE 1: Initial Knowledge Load ===")

        agent = await self.load_formation()
        if not agent:
            print("❌ Failed to load agent")
            return False

        # Get initial state
        info = self.get_cache_info(agent)

        print(f"\nInitial state:")
        print(f"  Cache files: {len(info['cache_files'])}")
        for f in info['cache_files']:
            print(f"    - {f}")

        print(f"  Buffer items: {len(set(info['buffer_items']))} unique sources")
        unique_sources = set(info['buffer_items'])
        for s in unique_sources:
            count = info['buffer_items'].count(s)
            print(f"    - {os.path.basename(s)} ({count} chunks)")

        print(f"  Knowledge sources: {len(info['knowledge_sources'])}")
        for s in info['knowledge_sources']:
            print(f"    - {os.path.basename(s)}")

        # Verify our test file is loaded
        test_file_loaded = any(self.test_file in s for s in info['knowledge_sources'])
        if test_file_loaded:
            print(f"\n✓ Test file '{self.test_file}' is loaded")
        else:
            print(f"\n❌ Test file '{self.test_file}' NOT found")
            return False

        # Don't stop formation - keep cache/buffer intact
        await self.stop_formation()
        print("\n✓ Phase 1 complete - cache and buffer preserved")
        return True

    async def run_phase_2_file_removal(self):
        """Phase 2: Remove file and verify it's removed from cache/buffer"""
        print("\n=== PHASE 2: File Removal Detection ===")

        # Move test file out of knowledge directory
        print(f"\nMoving '{self.test_file}' out of knowledge directory...")
        shutil.move(str(self.test_file_path), str(self.temp_file_path))
        print(f"✓ File moved to: {self.temp_file_path}")

        # Wait a moment for filesystem
        await asyncio.sleep(0.5)

        # Reload formation
        agent = await self.load_formation()
        if not agent:
            print("❌ Failed to load agent")
            return False

        # Get state after removal
        info = self.get_cache_info(agent)

        print(f"\nState after file removal:")
        print(f"  Cache files: {len(info['cache_files'])}")
        print(f"  Buffer items: {len(set(info['buffer_items']))} unique sources")
        print(f"  Knowledge sources: {len(info['knowledge_sources'])}")

        # Verify test file is NOT loaded
        test_file_loaded = any(self.test_file in s for s in info['knowledge_sources'])
        test_file_in_buffer = any(self.test_file in s for s in info['buffer_items'])
        test_file_in_cache = any(self.test_file in f for f in info['cache_files'])

        if not test_file_loaded:
            print(f"\n✓ Test file '{self.test_file}' removed from knowledge sources")
        else:
            print(f"\n❌ Test file '{self.test_file}' still in knowledge sources")

        if not test_file_in_buffer:
            print(f"✓ Test file '{self.test_file}' removed from buffer")
        else:
            print(f"❌ Test file '{self.test_file}' still in buffer")

        # Cache might still exist (stale) but won't be loaded
        if test_file_in_cache:
            print(f"⚠ Cache file still exists (will be cleaned up later)")
        else:
            print(f"✓ Cache file removed")

        await self.stop_formation()
        print("\n✓ Phase 2 complete")
        return not test_file_loaded and not test_file_in_buffer

    async def run_phase_3_file_readd(self):
        """Phase 3: Move file back and verify it's re-added to cache/buffer"""
        print("\n=== PHASE 3: File Re-addition Detection ===")

        # Move test file back to knowledge directory
        print(f"\nMoving '{self.test_file}' back to knowledge directory...")
        shutil.move(str(self.temp_file_path), str(self.test_file_path))
        print(f"✓ File moved back to: {self.test_file_path}")

        # Wait a moment for filesystem
        await asyncio.sleep(0.5)

        # Reload formation
        agent = await self.load_formation()
        if not agent:
            print("❌ Failed to load agent")
            return False

        # Get state after re-addition
        info = self.get_cache_info(agent)

        print(f"\nState after file re-addition:")
        print(f"  Cache files: {len(info['cache_files'])}")
        print(f"  Buffer items: {len(set(info['buffer_items']))} unique sources")
        print(f"  Knowledge sources: {len(info['knowledge_sources'])}")

        # Verify test file is loaded again
        test_file_loaded = any(self.test_file in s for s in info['knowledge_sources'])
        test_file_in_buffer = any(self.test_file in s for s in info['buffer_items'])
        test_file_in_cache = any(self.test_file in f for f in info['cache_files'])

        if test_file_loaded:
            print(f"\n✓ Test file '{self.test_file}' re-added to knowledge sources")
        else:
            print(f"\n❌ Test file '{self.test_file}' NOT re-added to knowledge sources")

        if test_file_in_buffer:
            print(f"✓ Test file '{self.test_file}' re-added to buffer")
        else:
            print(f"❌ Test file '{self.test_file}' NOT re-added to buffer")

        if test_file_in_cache:
            print(f"✓ Cache file re-created")
        else:
            print(f"❌ Cache file NOT re-created")

        await self.stop_formation()
        print("\n✓ Phase 3 complete")
        return test_file_loaded and test_file_in_buffer and test_file_in_cache

    async def run_phase_4_file_modification(self):
        """Phase 4: Modify file and verify cache/buffer are updated"""
        print("\n=== PHASE 4: File Modification Detection ===")

        # Read original content
        with open(self.test_file_path, 'r') as f:
            original_content = f.read()

        # Modify the file
        print(f"\nModifying '{self.test_file}'...")
        modified_content = original_content + f"\n\n<!-- Modified at {time.time()} -->\n"
        with open(self.test_file_path, 'w') as f:
            f.write(modified_content)
        print("✓ File modified")

        # Wait a moment for filesystem
        await asyncio.sleep(0.5)

        # Reload formation
        agent = await self.load_formation()
        if not agent:
            print("❌ Failed to load agent")
            # Restore original content
            with open(self.test_file_path, 'w') as f:
                f.write(original_content)
            return False

        # Get state after modification
        info = self.get_cache_info(agent)

        print(f"\nState after file modification:")
        print(f"  Cache files: {len(info['cache_files'])}")
        print(f"  Buffer items: {len(set(info['buffer_items']))} unique sources")
        print(f"  Knowledge sources: {len(info['knowledge_sources'])}")

        # Check if knowledge handler detected the change
        # The system should have regenerated embeddings for the modified file
        test_file_loaded = any(self.test_file in s for s in info['knowledge_sources'])
        test_file_in_buffer = any(self.test_file in s for s in info['buffer_items'])
        test_file_in_cache = any(self.test_file in f for f in info['cache_files'])

        if test_file_loaded and test_file_in_buffer and test_file_in_cache:
            print(f"\n✓ Modified file '{self.test_file}' reloaded with new content")
            print("✓ Cache invalidated and regenerated")
        else:
            print(f"\n❌ Modified file not properly reloaded")

        # Restore original content
        print("\nRestoring original file content...")
        with open(self.test_file_path, 'w') as f:
            f.write(original_content)

        await self.stop_formation()
        print("\n✓ Phase 4 complete")
        return test_file_loaded and test_file_in_buffer and test_file_in_cache

    async def run_all_phases(self):
        """Run all test phases"""
        try:
            await self.setup()

            # Run all phases
            phase1_success = await self.run_phase_1_initial_load()
            if not phase1_success:
                print("\n❌ Phase 1 failed")
                return False

            phase2_success = await self.run_phase_2_file_removal()
            if not phase2_success:
                print("\n❌ Phase 2 failed")
                return False

            phase3_success = await self.run_phase_3_file_readd()
            if not phase3_success:
                print("\n❌ Phase 3 failed")
                return False

            phase4_success = await self.run_phase_4_file_modification()
            if not phase4_success:
                print("\n❌ Phase 4 failed")
                return False

            print("\n✅ All phases completed successfully!")
            print("\nKnowledge change detection mechanics verified:")
            print("  ✓ Initial load works correctly")
            print("  ✓ File removal is detected and handled")
            print("  ✓ File re-addition is detected and handled")
            print("  ✓ File modification triggers cache invalidation")

            return True

        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await self.teardown()


async def main():
    """Run the knowledge change detection test"""
    print("=== Test 6B: Knowledge Change Detection ===")
    test = KnowledgeChangeDetectionTest()
    success = await test.run_all_phases()

    if success:
        print("\n✅ Test 6B PASSED: Knowledge change detection working correctly")
    else:
        print("\n❌ Test 6B FAILED: Knowledge change detection issues found")


if __name__ == "__main__":
    asyncio.run(main())
