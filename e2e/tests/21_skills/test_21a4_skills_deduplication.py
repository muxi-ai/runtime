#!/usr/bin/env python3
"""Test 21a4: Skills Deduplication - verify activate_skill is deduplicated within a session."""

import asyncio
import os
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402


class TestSkillsDeduplication(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21a4_skills_deduplication",
            test_description="Verify skill activation is deduplicated within a session",
            test_area="21_skills",
        )

    async def test_skills_deduplication(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            print("\n1. Loading formation...")
            formation_path = Path(__file__).parent / "formations" / "formation-skills"
            await self.setup_formation(formation_path=formation_path)
            skill_manager = self.formation._skill_manager
            checks.append("Formation loaded")

            # 2. Manually activate a skill (simulate what the agent would do)
            print("\n2. Activating pdf-processing (first time)...")
            result1 = skill_manager.activate("pdf-processing", "test-session-1")
            assert '<skill_content name="pdf-processing">' in result1, \
                "First activation should return full content"
            print(f"   First activation: returned {len(result1)} chars of content")
            checks.append("First activation returns full skill content")

            # 3. Activate same skill again in same session
            print("\n3. Activating pdf-processing (second time, same session)...")
            result2 = skill_manager.activate("pdf-processing", "test-session-1")
            assert "already active" in result2, \
                f"Second activation should say 'already active', got: {result2}"
            assert len(result2) < len(result1), \
                "Deduped response should be shorter than full content"
            print(f"   Second activation: '{result2}'")
            checks.append("Second activation returns dedup message")

            # 4. Activate in different session (should work)
            print("\n4. Activating pdf-processing in different session...")
            result3 = skill_manager.activate("pdf-processing", "test-session-2")
            assert '<skill_content name="pdf-processing">' in result3, \
                "Activation in new session should return full content"
            print(f"   New session activation: returned {len(result3)} chars")
            checks.append("Different session gets full content (no cross-session dedup)")

            # 5. Verify is_activated tracking
            print("\n5. Checking is_activated state...")
            assert skill_manager.is_activated("pdf-processing", "test-session-1")
            assert skill_manager.is_activated("pdf-processing", "test-session-2")
            assert not skill_manager.is_activated("data-analysis", "test-session-1")
            assert not skill_manager.is_activated("pdf-processing", "test-session-3")
            print("   Activation tracking correct")
            checks.append("is_activated correctly tracks per-session state")

            print("\n6. Cleaning up...")
            await self.cleanup_formation()
            checks.append("Clean shutdown")

            duration = time.time() - start_time
            formatter.print_test_result(
                test_name=self.test_name,
                success=True,
                checks=checks,
                transcript=[],
                duration=duration,
            )
            return True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name=self.test_name,
                success=False,
                checks=checks + [f"FAILED: {e}"],
                transcript=[],
                duration=duration,
            )
            try:
                await self.cleanup_formation()
            except Exception:
                pass
            return False


if __name__ == "__main__":
    test = TestSkillsDeduplication()
    result = asyncio.run(test.test_skills_deduplication())
    os._exit(0 if result else 1)
