#!/usr/bin/env python3
"""Test 1a8: Formation init hook - single command, multiline, and fail-fast."""

import asyncio
import tempfile
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402
from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_TEMPLATE = """\
schema: "1.0.0"
id: init-hook-test
description: Test formation init hook

{init_block}

llm:
  api_keys:
    openai: "sk-fake-key-for-init-test"
  models:
    - text: "openai/gpt-4o-mini"

agents:
  - id: assistant
    name: Test Assistant
    description: Test assistant
    system_message: "You are a test assistant."
"""


class TestFormationInitHook(BaseE2ETest):
    """Test formation init hook execution."""

    def __init__(self):
        super().__init__(
            test_name="test_1a8_formation_init_hook",
            test_description="Test formation init hook (single, multiline, fail-fast)",
            test_area="1_foundation",
        )

    async def test_1a8_formation_init_hook(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False
        tests_passed = []
        tests_failed = []

        formatter.print_test_header(
            test_name="test_1a8_formation_init_hook",
            description="Test formation init hook (single, multiline, fail-fast)",
        )

        try:
            # Test 1: Single init command creates a directory
            print("\n1. Testing single init command...")
            with tempfile.TemporaryDirectory() as tmpdir:
                target_dir = Path(tmpdir) / "workspace"
                yaml_content = FORMATION_TEMPLATE.format(
                    init_block=f'init: "mkdir -p {target_dir}"'
                )
                yaml_path = Path(tmpdir) / "formation.yaml"
                yaml_path.write_text(yaml_content)

                formation = Formation()
                try:
                    await formation.load(str(yaml_path))
                except Exception:
                    pass  # LLM init will fail with fake key, that's OK

                if target_dir.is_dir():
                    print(f"   Created {target_dir}")
                    print("   ✅ Single init command worked")
                    tests_passed.append("Single init command")
                else:
                    tests_failed.append("Single init command - directory not created")
                    print("   FAIL: directory was not created")

            # Test 2: Multiline init command
            print("\n2. Testing multiline init command...")
            with tempfile.TemporaryDirectory() as tmpdir:
                dir1 = Path(tmpdir) / "dir_one"
                dir2 = Path(tmpdir) / "dir_two"
                marker = Path(tmpdir) / "marker.txt"
                init_block = (
                    "init: |\n"
                    f"  mkdir -p {dir1}\n"
                    f"  mkdir -p {dir2}\n"
                    f'  echo "init-done" > {marker}\n'
                )
                yaml_content = FORMATION_TEMPLATE.format(init_block=init_block)
                yaml_path = Path(tmpdir) / "formation.yaml"
                yaml_path.write_text(yaml_content)

                formation = Formation()
                try:
                    await formation.load(str(yaml_path))
                except Exception:
                    pass

                all_created = dir1.is_dir() and dir2.is_dir() and marker.is_file()
                if all_created:
                    content = marker.read_text().strip()
                    assert content == "init-done", f"Unexpected marker content: {content}"
                    print(f"   Created {dir1}, {dir2}, and {marker}")
                    print("   ✅ Multiline init command worked")
                    tests_passed.append("Multiline init command")
                else:
                    tests_failed.append("Multiline init - not all targets created")
                    print(
                        f"   FAIL: dir1={dir1.is_dir()}, dir2={dir2.is_dir()}, marker={marker.is_file()}"
                    )

            # Test 3: Failed init command prevents formation loading (fail-fast)
            print("\n3. Testing fail-fast on bad init command...")
            with tempfile.TemporaryDirectory() as tmpdir:
                init_block = 'init: "exit 42"'
                yaml_content = FORMATION_TEMPLATE.format(init_block=init_block)
                yaml_path = Path(tmpdir) / "formation.yaml"
                yaml_path.write_text(yaml_content)

                formation = Formation()
                failed_correctly = False
                try:
                    await formation.load(str(yaml_path))
                    tests_failed.append("Failed init should raise")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "init hook failed" in error_msg or "init" in error_msg:
                        print(f"   Correctly raised: {e}")
                        print("   ✅ Fail-fast on bad init command")
                        tests_passed.append("Fail-fast on bad init")
                        failed_correctly = True
                    else:
                        tests_failed.append(f"Wrong error type: {e}")
                        print(f"   FAIL: wrong exception: {e}")

                if not failed_correctly:
                    tests_failed.append("Init failure not detected")

            if tests_failed:
                raise AssertionError(f"Some tests didn't pass: {tests_failed}")

            print(f"\n✅ All {len(tests_passed)} init hook tests passed")

            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a8_formation_init_hook",
                success=True,
                checks=tests_passed,
                transcript=[],
                duration=duration,
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a8_formation_init_hook",
                success=False,
                checks=[f"Failed: {str(e)}"] + tests_failed,
                transcript=[],
                duration=duration,
            )
            raise
        finally:
            return 0 if success else 1

    def run_test(self):
        return asyncio.run(self.test_1a8_formation_init_hook())


if __name__ == "__main__":
    import os

    test = TestFormationInitHook()
    exit_code = test.run_test()
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
