#!/usr/bin/env python3
"""Test 21a1: Skills Formation Loading - verify skills are discovered and loaded at startup."""

import asyncio
import os
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402


class TestSkillsFormationLoading(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21a1_skills_formation_loading",
            test_description="Verify skills are discovered and loaded during formation startup",
            test_area="21_skills",
        )

    async def test_skills_formation_loading(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            # 1. Load formation with skills
            print("\n1. Loading formation with skills...")
            formation_path = Path(__file__).parent / "formations" / "formation-skills"
            await self.setup_formation(formation_path=formation_path)
            overlord = self.overlord
            print("   Formation loaded successfully")
            checks.append("Formation loaded with skills config")

            # 2. Verify skill_manager exists on formation
            print("\n2. Checking skill manager...")
            skill_manager = getattr(self.formation, "_skill_manager", None)
            assert skill_manager is not None, "Skill manager not initialized"
            print(f"   Skill manager initialized: {len(skill_manager.skills)} skills")
            checks.append("Skill manager initialized")

            # 3. Verify public skills loaded
            print("\n3. Checking public skills...")
            assert "pdf-processing" in skill_manager.skills, "pdf-processing not loaded"
            assert "data-analysis" in skill_manager.skills, "data-analysis not loaded"
            print(f"   Public skills: {skill_manager.public_skills}")
            checks.append("Public skills loaded (pdf-processing, data-analysis)")

            # 4. Verify agent-specific skills loaded
            print("\n4. Checking agent-specific skills...")
            assert "ticket-handling" in skill_manager.skills, "ticket-handling not loaded"
            assert "support-agent" in skill_manager.agent_skills, "support-agent skills not registered"
            assert "ticket-handling" in skill_manager.agent_skills["support-agent"]
            print(f"   Agent skills: {skill_manager.agent_skills}")
            checks.append("Agent-specific skills loaded (ticket-handling for support-agent)")

            # 5. Verify skill metadata is correct
            print("\n5. Checking skill metadata...")
            pdf_skill = skill_manager.skills["pdf-processing"]
            assert pdf_skill.name == "pdf-processing"
            assert "PDF" in pdf_skill.description or "pdf" in pdf_skill.description.lower()
            assert pdf_skill.license == "MIT"
            print(f"   pdf-processing: desc='{pdf_skill.description[:60]}...', license={pdf_skill.license}")
            checks.append("Skill metadata parsed correctly")

            # 6. Verify skill manager passed to overlord
            print("\n6. Checking overlord integration...")
            assert hasattr(overlord, "skill_manager"), "skill_manager not on overlord"
            assert overlord.skill_manager is skill_manager
            print("   Overlord has skill_manager reference")
            checks.append("Skill manager passed to overlord")

            # 7. Verify agents loaded
            print("\n7. Checking agents...")
            assert len(overlord.agents) >= 2, f"Expected >=2 agents, got {len(overlord.agents)}"
            print(f"   Agents: {list(overlord.agents.keys())}")
            checks.append("Agents loaded successfully")

            # Clean up
            print("\n8. Cleaning up...")
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
    test = TestSkillsFormationLoading()
    result = asyncio.run(test.test_skills_formation_loading())
    os._exit(0 if result else 1)
