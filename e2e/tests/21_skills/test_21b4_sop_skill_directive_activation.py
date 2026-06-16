#!/usr/bin/env python3
"""Test 21b4: SOP Skill Directive - deterministic activation from SOP steps.

Verifies that when an SOP step declares [skill:test-skill], the skill is
activated deterministically by the workflow executor before the agent
processes the task, without requiring the LLM to choose to call
activate_skill.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestSOPSkillDirectiveActivation(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21b4_sop_skill_directive_activation",
            test_description=(
                "Verify SOP step [skill:name] causes deterministic "
                "skill activation without LLM tool choice"
            ),
            test_area="21_skills",
        )

    async def test_sop_skill_directive_activation(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []
        transcript = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            # 1. Load formation with skill + SOP
            print("\n1. Loading formation with skill and SOP...")
            formation_path = Path(__file__).parent / "formations" / "formation-sop-skills"
            await self.setup_formation(formation_path=formation_path)
            overlord = self.overlord
            skill_manager = self.formation._skill_manager
            checks.append("Formation loaded with skill and SOP")

            # 2. Verify SOP loaded
            print("\n2. Verifying SOP loaded...")
            sop_system = getattr(overlord, "sop_system", None)
            assert sop_system is not None, "SOP system not available"
            sop_ids = list(sop_system.sops.keys())
            assert (
                "skill-activation-test" in sop_ids
            ), f"Expected 'skill-activation-test' in {sop_ids}"
            print(f"   SOPs loaded: {sop_ids}")
            checks.append("SOP 'skill-activation-test' loaded")

            # 3. Verify skill loaded
            print("\n3. Verifying skill loaded...")
            assert (
                "test-skill" in skill_manager.skills
            ), f"Expected 'test-skill' in skills. Got: {list(skill_manager.skills.keys())}"
            print(f"   Skills: {list(skill_manager.skills.keys())}")
            checks.append("Skill 'test-skill' loaded")

            # 4. Verify skill is NOT pre-activated
            print("\n4. Checking skill not pre-activated...")
            pre_activated = False
            for session_id, activated_skills in skill_manager._activated.items():
                if "test-skill" in activated_skills:
                    pre_activated = True
                    break
            assert not pre_activated, "test-skill was already activated before chat"
            checks.append("test-skill not pre-activated")

            # 5. Send explicit SOP invocation
            print("\n5. Invoking SOP via overlord.chat()...")
            timeout = TestTimeouts.get_timeout("workflow_decomposition") + 60
            response = await asyncio.wait_for(
                overlord.chat(
                    "Execute the skill-activation-test SOP",
                    user_id="test_user",
                    session_id="sop_skill_test",
                ),
                timeout=timeout,
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:300]}...")
            transcript.append(("Execute SOP", response_text[:300]))
            checks.append("Got response from overlord.chat()")

            # 6. Verify deterministic activation occurred
            print("\n6. Verifying deterministic skill activation...")
            activated = False
            activation_session = None
            for session_id, activated_skills in skill_manager._activated.items():
                if "test-skill" in activated_skills:
                    activated = True
                    activation_session = session_id
                    print(f"   test-skill activated in session {session_id}")
                    break

            assert activated, (
                "test-skill was NOT activated. The SOP step directive "
                "[skill:test-skill] should have caused deterministic activation "
                "by the workflow executor before the agent processed the task."
            )
            checks.append(f"test-skill activated deterministically (session: {activation_session})")

            # 7. Verify skill content was injected into agent context
            print("\n7. Verifying skill content injection...")
            injected = False
            agent = overlord.agents.get("test-agent")
            if agent and agent._messages:
                # Skill content is injected into the task prompt (user messages),
                # not the system message. Search all messages.
                for msg in agent._messages:
                    msg_content = msg.get("content", "")
                    if (
                        "test-skill" in msg_content
                        and "SKILL_ACTIVATED_CONFIRMED_42" in msg_content
                    ):
                        print("   Skill content found in test-agent's messages")
                        injected = True
                        break

            assert injected, (
                "Skill content was not injected into test-agent's messages. "
                "The executor should inject activated skill content into the task prompt."
            )
            checks.append("Skill content injected into agent context with magic phrase")

            # 8. Verify response references the skill (best-effort LLM check)
            print("\n8. Checking response relevance...")
            response_lower = response_text.lower()
            relevant = any(
                term in response_lower
                for term in [
                    "skill",
                    "activated",
                    "instruction",
                    "confirm",
                    "context",
                ]
            )
            if relevant:
                checks.append("Response references skill/context")
            else:
                checks.append("WARNING: Response relevance unclear (LLM variance expected)")

            # 9. Cleanup
            print("\n9. Cleaning up...")
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
    test = TestSOPSkillDirectiveActivation()
    result = asyncio.run(test.test_sop_skill_directive_activation())
    os._exit(0 if result else 1)
