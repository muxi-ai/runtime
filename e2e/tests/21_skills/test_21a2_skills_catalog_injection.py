#!/usr/bin/env python3
"""Test 21a2: Skills Catalog Injection - verify skill catalog is injected into agent system prompts."""

import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402


class TestSkillsCatalogInjection(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21a2_skills_catalog_injection",
            test_description="Verify skill catalog XML is injected into agent system prompts",
            test_area="21_skills",
        )

    async def test_skills_catalog_injection(self):
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
            overlord = self.overlord
            checks.append("Formation loaded")

            # 2. Check general-agent gets public skills in system prompt
            print("\n2. Checking general-agent system prompt...")
            general_agent = overlord.agents.get("general-agent")
            assert general_agent is not None, "general-agent not found"

            system_msg = general_agent._messages[0]["content"] if general_agent._messages else ""
            assert "## Available Skills" in system_msg, "Catalog not in general-agent system prompt"
            assert "**pdf-processing**" in system_msg
            assert "**data-analysis**" in system_msg
            # general-agent should NOT see ticket-handling (private to support-agent)
            assert "**ticket-handling**" not in system_msg, \
                "ticket-handling should not be in general-agent catalog"
            print("   general-agent: has pdf-processing + data-analysis, NOT ticket-handling")
            checks.append("General agent catalog: public skills only")

            # 3. Check support-agent gets public + private skills
            print("\n3. Checking support-agent system prompt...")
            support_agent = overlord.agents.get("support-agent")
            assert support_agent is not None, "support-agent not found"

            system_msg = support_agent._messages[0]["content"] if support_agent._messages else ""
            assert "## Available Skills" in system_msg, "Catalog not in support-agent system prompt"
            assert "**pdf-processing**" in system_msg
            assert "**data-analysis**" in system_msg
            assert "**ticket-handling**" in system_msg
            print("   support-agent: has pdf-processing + data-analysis + ticket-handling")
            checks.append("Support agent catalog: public + private skills")

            # 4. Verify catalog has activation instruction
            print("\n4. Checking catalog instruction text...")
            assert "activate_skill" in system_msg, "Catalog should mention activate_skill tool"
            print("   Catalog contains activation instruction")
            checks.append("Catalog contains activation instruction")

            # 5. Verify specialties were enhanced
            print("\n5. Checking specialty enhancement...")
            general_specialties = general_agent.specialties
            print(f"   general-agent specialties: {general_specialties}")
            # Should have original + skill descriptions
            assert any("PDF" in s or "pdf" in s.lower() for s in general_specialties), \
                "pdf-processing description not in general-agent specialties"
            assert any("data" in s.lower() or "chart" in s.lower() or "analy" in s.lower() for s in general_specialties), \
                "data-analysis description not in general-agent specialties"
            checks.append("Agent specialties enhanced with skill descriptions")

            support_specialties = support_agent.specialties
            print(f"   support-agent specialties: {support_specialties}")
            assert any("ticket" in s.lower() for s in support_specialties), \
                "ticket-handling description not in support-agent specialties"
            checks.append("Support agent specialties include ticket-handling")

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
    test = TestSkillsCatalogInjection()
    result = asyncio.run(test.test_skills_catalog_injection())
    sys.exit(0 if result else 1)
