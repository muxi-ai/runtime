#!/usr/bin/env python3
"""Test 21b1: Explicit Skill Request - verify agent activates skill when explicitly asked."""

import asyncio
import os
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestExplicitSkillRequest(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21b1_explicit_skill_request",
            test_description="Verify agent activates skill when user explicitly asks to use it",
            test_area="21_skills",
        )

    async def test_explicit_skill_request(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []
        transcript = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            print("\n1. Loading formation...")
            formation_path = Path(__file__).parent / "formations" / "formation-skills"
            await self.setup_formation(formation_path=formation_path)
            overlord = self.overlord
            skill_manager = self.formation._skill_manager
            checks.append("Formation loaded")

            # 2. Send explicit request to use a skill by name
            print("\n2. Sending explicit skill activation request via overlord.chat()...")
            timeout = TestTimeouts.get_timeout("simple_chat") + 60
            response = await asyncio.wait_for(
                overlord.chat(
                    "Use the data-analysis skill to help me understand how to analyze a sales dataset.",
                    user_id="test_user",
                ),
                timeout=timeout,
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:200]}...")
            transcript.append(("Use data-analysis skill", response_text[:200]))
            checks.append("Got response to explicit skill request")

            # 3. Verify data-analysis was activated
            print("\n3. Checking if data-analysis was activated...")
            activated = False
            for session_id, activated_skills in skill_manager._activated.items():
                if "data-analysis" in activated_skills:
                    activated = True
                    print(f"   data-analysis activated in session {session_id}")
                    break

            assert activated, (
                "data-analysis skill was NOT activated despite explicit request. "
                "The LLM should call activate_skill when the user explicitly names the skill."
            )
            checks.append("data-analysis skill activated (explicit request worked)")

            # 4. Verify skill content was injected into agent's context
            print("\n4. Verifying content injection...")
            injected = False
            for agent_id, agent in overlord.agents.items():
                if agent._messages and len(agent._messages) > 0:
                    system_content = agent._messages[0].get("content", "")
                    if '<skill_content name="data-analysis">' in system_content:
                        print(f"   Skill content found in {agent_id}'s system prompt")
                        assert "Data Analysis" in system_content
                        injected = True
                        break

            assert injected, "Skill content was not injected into any agent's system prompt"
            checks.append("Skill content injected into agent context")

            # 5. Verify the response is relevant to data analysis
            print("\n5. Checking response relevance...")
            response_lower = response_text.lower()
            relevant = any(term in response_lower for term in [
                "data", "analysis", "dataset", "sales", "chart", "statistic", "csv",
                "pandas", "visualiz", "column", "row",
            ])
            assert relevant, f"Response doesn't seem relevant to data analysis: {response_text[:200]}"
            print("   Response is relevant to data analysis")
            checks.append("Response is relevant to the skill domain")

            print("\n6. Cleaning up...")
            await self.cleanup_formation()
            checks.append("Clean shutdown")

            duration = time.time() - start_time
            formatter.print_test_result(
                test_name=self.test_name,
                success=True,
                checks=checks,
                transcript=transcript,
                duration=duration,
            )
            return True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name=self.test_name,
                success=False,
                checks=checks + [f"FAILED: {e}"],
                transcript=transcript,
                duration=duration,
            )
            try:
                await self.cleanup_formation()
            except Exception:
                pass
            return False


if __name__ == "__main__":
    test = TestExplicitSkillRequest()
    result = asyncio.run(test.test_explicit_skill_request())
    os._exit(0 if result else 1)
