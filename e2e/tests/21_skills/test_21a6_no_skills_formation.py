#!/usr/bin/env python3
"""Test 21a6: No Skills Formation - verify formations without skills work unchanged."""

import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestNoSkillsFormation(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21a6_no_skills_formation",
            test_description="Verify formations without skills work identically to before",
            test_area="21_skills",
        )

    async def test_no_skills_formation(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []
        transcript = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            # Use the standard base formation (no skills)
            print("\n1. Loading formation WITHOUT skills...")
            formation_path = Path(__file__).parent.parent / "1_foundation" / "formations" / "formation-base"
            await self.setup_formation(formation_path=formation_path)
            overlord = self.overlord
            checks.append("Formation loaded (no skills)")

            # 2. Verify no skill manager
            print("\n2. Checking no skill manager...")
            skill_manager = getattr(self.formation, "_skill_manager", None)
            assert skill_manager is None, "Skill manager should not exist for no-skills formation"
            print("   No skill manager (correct)")
            checks.append("No skill manager initialized")

            # 3. Verify overlord has no skill_manager (or it's None)
            print("\n3. Checking overlord...")
            overlord_sm = getattr(overlord, "skill_manager", None)
            assert overlord_sm is None, "Overlord should not have skill manager"
            print("   Overlord skill_manager is None (correct)")
            checks.append("Overlord has no skill manager")

            # 4. Verify agents don't have activate_skill in system prompt
            print("\n4. Checking agent system prompts...")
            for agent_id, agent in overlord.agents.items():
                if agent._messages and agent._messages[0]["role"] == "system":
                    content = agent._messages[0]["content"]
                    assert "<available_skills>" not in content, \
                        f"Agent {agent_id} should not have skills catalog"
                print(f"   {agent_id}: no skills catalog (correct)")
            checks.append("No skills catalog in agent system prompts")

            # 5. Basic chat still works
            print("\n5. Testing basic chat...")
            timeout = TestTimeouts.get_timeout("simple_chat")
            response = await asyncio.wait_for(
                overlord.chat("Hello, how are you?", user_id="test_user"),
                timeout=timeout,
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            assert len(response_text) > 10, "Response too short"
            print(f"   Response: {response_text[:100]}...")
            transcript.append(("Hello", response_text[:100]))
            checks.append("Chat works normally without skills")

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
    test = TestNoSkillsFormation()
    result = asyncio.run(test.test_no_skills_formation())
    sys.exit(0 if result else 1)
