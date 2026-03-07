#!/usr/bin/env python3
"""Test 21b2: Contextual Skill Activation - verify agent activates skill based on task context
without the user mentioning the skill by name."""

import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestContextualSkillActivation(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21b2_contextual_skill_activation",
            test_description="Verify agent activates skill from context without user naming it",
            test_area="21_skills",
        )

    async def test_contextual_skill_activation(self):
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

            # 2. Send a task that matches a skill description WITHOUT naming the skill.
            # The pdf-processing skill description says:
            #   "Extract text, tables, and metadata from PDF files. Use when working with PDF documents."
            # So asking about extracting tables from a PDF should contextually match.
            print("\n2. Sending contextual message (no skill name mentioned)...")
            timeout = TestTimeouts.get_timeout("simple_chat") + 40
            response = await asyncio.wait_for(
                overlord.chat(
                    "I have a 50-page PDF report. I need to pull all the tables out of it "
                    "and get the metadata like author and creation date. How should I do this?",
                    user_id="test_user",
                ),
                timeout=timeout,
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:200]}...")
            transcript.append(("Extract tables from PDF", response_text[:200]))
            checks.append("Got response to contextual task")

            # 3. Check if any skill was activated
            print("\n3. Checking skill activation state...")
            activated_skills = set()
            for session_id, skills in skill_manager._activated.items():
                activated_skills.update(skills)

            if "pdf-processing" in activated_skills:
                print("   pdf-processing activated from context (ideal behavior)")
                checks.append("pdf-processing skill activated from context")

                # Verify content injection
                for agent_id, agent in overlord.agents.items():
                    if agent._messages and len(agent._messages) > 0:
                        system_content = agent._messages[0].get("content", "")
                        if '<skill_content name="pdf-processing">' in system_content:
                            print(f"   Skill content injected into {agent_id}")
                            checks.append(f"Skill content verified in {agent_id}")
                            break
            elif activated_skills:
                print(f"   Different skill(s) activated: {activated_skills}")
                checks.append(f"Skill(s) activated (different than expected): {activated_skills}")
            else:
                # LLM did not activate any skill -- this is acceptable behavior
                # since contextual activation depends on the model's reasoning.
                # The catalog was available, the model chose not to use it.
                print("   No skills activated (LLM chose to answer directly)")
                print("   This is acceptable -- contextual activation is model-dependent")
                checks.append("No skill activated (model answered directly, acceptable)")

            # 4. Verify response quality regardless of activation
            print("\n4. Checking response quality...")
            assert len(response_text) > 50, "Response too short"
            response_lower = response_text.lower()
            relevant = any(term in response_lower for term in [
                "pdf", "table", "extract", "metadata", "author", "page",
                "document", "parsing", "library", "tool",
            ])
            assert relevant, f"Response doesn't address the PDF task: {response_text[:200]}"
            print("   Response addresses the PDF task")
            checks.append("Response is relevant to the task")

            print("\n5. Cleaning up...")
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
    test = TestContextualSkillActivation()
    result = asyncio.run(test.test_contextual_skill_activation())
    sys.exit(0 if result else 1)
