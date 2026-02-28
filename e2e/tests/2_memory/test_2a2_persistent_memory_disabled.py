#!/usr/bin/env python3
"""Test 2A2: Persistent Memory Disabled

This test validates:
1. persistent: false disables persistent memory
2. persistent: { enabled: false } disables persistent memory but preserves config
3. Buffer memory still works when persistent is disabled
4. Default SQLite is created when persistent is not specified
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest


class TestPersistentMemoryDisabled(BaseMemoryTest):
    """Test persistent memory disable functionality."""

    MEMORY_CONFIGS = {
        **BaseMemoryTest.MEMORY_CONFIGS,
        "persistent_disabled": "formation-persistent-disabled.yaml",
        "persistent_disabled_enabled_flag": "formation-persistent-disabled-enabled-flag.yaml",
    }

    async def test_persistent_false_disables_memory(self):
        """Test that persistent: false disables persistent memory."""
        test_name = "2a2_persistent_false"
        self.print_test_header(test_name, "Test persistent: false disables persistent memory")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_memory_formation("persistent_disabled")

            # Check that persistent memory is NOT initialized
            has_long_term = (
                hasattr(self.formation, "_long_term_memory")
                and self.formation._long_term_memory is not None
            )

            if has_long_term:
                print("  ✗ Persistent memory should be disabled but was initialized")
                all_passed = False
            else:
                print("  ✓ Persistent memory is correctly disabled")
                checks_passed.append("Persistent memory disabled with persistent: false")

            # Verify buffer memory still works
            buffer_config = self.formation.config.get("memory", {}).get("buffer", {})
            if buffer_config.get("size") == 10:
                print("  ✓ Buffer memory configuration is present")
                checks_passed.append("Buffer memory works when persistent disabled")
            else:
                print("  ✗ Buffer memory configuration missing")
                all_passed = False

            # Verify formation can still chat (basic functionality)
            response = await self.overlord.chat(
                "Say hello",
                user_id="test_user",
                use_async=False,
                stream=False,
            )
            if response:
                print("  ✓ Formation can chat without persistent memory")
                checks_passed.append("Chat works without persistent memory")
            else:
                print("  ✗ Chat failed")
                all_passed = False

            await self.cleanup()

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)
        return all_passed

    async def test_enabled_false_disables_memory(self):
        """Test that persistent: { enabled: false } disables persistent memory."""
        test_name = "2a2_enabled_false"
        self.print_test_header(
            test_name, "Test persistent: { enabled: false } disables persistent memory"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_memory_formation("persistent_disabled_enabled_flag")

            # Check that persistent memory is NOT initialized
            has_long_term = (
                hasattr(self.formation, "_long_term_memory")
                and self.formation._long_term_memory is not None
            )

            if has_long_term:
                print("  ✗ Persistent memory should be disabled but was initialized")
                all_passed = False
            else:
                print("  ✓ Persistent memory is correctly disabled")
                checks_passed.append("Persistent memory disabled with enabled: false")

            # Verify the config is preserved in the formation config
            memory_config = self.formation.config.get("memory", {})
            persistent_config = memory_config.get("persistent", {})

            if isinstance(persistent_config, dict):
                if persistent_config.get("enabled") is False:
                    print("  ✓ enabled: false is preserved in config")
                    checks_passed.append("enabled: false preserved in config")
                else:
                    print("  ✗ enabled: false not found in config")
                    all_passed = False

                if "connection_string" in persistent_config:
                    print("  ✓ connection_string preserved for later use")
                    checks_passed.append("connection_string preserved in config")
                if "embedding_model" in persistent_config:
                    print("  ✓ embedding_model preserved for later use")
                    checks_passed.append("embedding_model preserved in config")
            else:
                print("  ✗ Persistent config should be dict with enabled: false")
                all_passed = False

            await self.cleanup()

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)
        return all_passed

    async def test_default_sqlite_when_omitted(self):
        """Test that default SQLite is created when persistent is omitted."""
        test_name = "2a2_default_sqlite"
        self.print_test_header(test_name, "Test default SQLite when persistent is omitted")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Use basic formation which doesn't specify persistent memory
            await self.setup_memory_formation("basic")

            # Check that persistent memory IS initialized (default SQLite)
            has_long_term = (
                hasattr(self.formation, "_long_term_memory")
                and self.formation._long_term_memory is not None
            )

            if has_long_term:
                print("  ✓ Default SQLite persistent memory is initialized")
                checks_passed.append("Default SQLite created when persistent omitted")

                # Check that db file exists next to formation
                formation_path = self.formation.get_formation_path()
                if formation_path:
                    formation_dir = (
                        Path(formation_path).parent
                        if Path(formation_path).is_file()
                        else Path(formation_path)
                    )
                    db_file = formation_dir / "memory.db"
                    if db_file.exists():
                        print(f"  ✓ SQLite db file created at: {db_file}")
                        checks_passed.append("DB file created: memory.db")
                    else:
                        print(f"  ✗ Expected db file not found: {db_file}")
                        all_passed = False
            else:
                print("  ✗ Default persistent memory should be initialized but wasn't")
                all_passed = False

            await self.cleanup()

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            import traceback

            traceback.print_exc()
            all_passed = False

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)
        return all_passed


async def main():
    """Run all persistent memory disabled tests."""
    test = TestPersistentMemoryDisabled()
    results = []

    print("\n" + "=" * 60)
    print("Area 2A2: Persistent Memory Disabled Tests")
    print("=" * 60)

    # Run tests
    results.append(await test.test_persistent_false_disables_memory())
    results.append(await test.test_enabled_false_disables_memory())
    results.append(await test.test_default_sqlite_when_omitted())

    # Summary
    passed = sum(results)
    total = len(results)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{total} tests passed")
    print("=" * 60)

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    if success:
        print("SUCCESS", flush=True)
    import os; os._exit(0 if success else 1)
