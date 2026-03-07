#!/usr/bin/env python3
"""Test 21c1: Skill script execution via RCE.

Verifies that an agent can execute a skill's script through the RCE service
when both the skill manager and RCE client are configured.

Requires: Skills RCE server running on localhost:7891.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Skip if RCE server is not running
try:
    import httpx

    resp = httpx.get("http://localhost:7891/health", timeout=2)
    if resp.status_code != 200:
        print("SKIP: RCE server not healthy on localhost:7891")
        sys.exit(0)
except Exception:
    print("SKIP: RCE server not running on localhost:7891")
    sys.exit(0)

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestSkillExecution(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21c1_skill_execution",
            test_description="Verify skill script execution via RCE service",
            test_area="21_skills",
        )

    async def test_skill_execution(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []
        transcript = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            # 1. Load formation with RCE config
            print("\n1. Loading formation with RCE config...")
            formation_path = Path(__file__).parent / "formations" / "formation-skills-rce"
            await self.setup_formation(formation_path=formation_path)
            overlord = self.overlord
            skill_manager = self.formation._skill_manager
            rce_client = getattr(self.formation, "_rce_client", None)

            assert rce_client is not None, "RCE client not initialized"
            assert rce_client.status is not None, "RCE status not fetched"
            print(f"   RCE connected: v{rce_client.status.version}")
            print(f"   Languages: {rce_client.languages}")
            checks.append("Formation loaded with RCE client")

            # 2. Verify run_skill tool is registered
            print("\n2. Checking run_skill tool availability...")
            run_tool = skill_manager.build_run_skill_tool("general-agent")
            assert run_tool is not None, "run_skill tool not built"
            enum = run_tool["function"]["parameters"]["properties"]["skill_name"]["enum"]
            assert "pdf-processing" in enum, "pdf-processing not in run_skill enum"
            print(f"   Executable skills: {enum}")
            checks.append(f"run_skill tool available (skills: {enum})")

            # 3. Verify overlord has RCE client
            print("\n3. Checking overlord RCE client...")
            assert hasattr(overlord, "rce_client"), "Overlord missing rce_client"
            assert overlord.rce_client is not None, "Overlord rce_client is None"
            checks.append("Overlord has RCE client")

            # 4. Direct skill execution test (bypass LLM, test the machinery)
            print("\n4. Testing direct skill execution...")
            agent = overlord.agents.get("general-agent")
            assert agent is not None, "general-agent not found"

            result = await agent.invoke_tool(
                tool_name="run_skill",
                parameters={
                    "skill_name": "pdf-processing",
                    "command": "python3 scripts/extract.py test.pdf",
                },
            )
            print(f"   Result: {result}")
            assert result.get("status") == "success", f"Expected success, got: {result}"
            assert "Extracted text from test.pdf" in result.get("stdout", ""), \
                f"Unexpected stdout: {result.get('stdout')}"
            checks.append("Direct skill execution works")

            # 5. Test execution through overlord.chat()
            print("\n5. Sending skill execution request via overlord.chat()...")
            timeout = TestTimeouts.get_timeout("simple_chat") + 60
            response = await asyncio.wait_for(
                overlord.chat(
                    "Use the pdf-processing skill to extract text from my document. "
                    "Run the extract script on input.pdf.",
                    user_id="test_user",
                ),
                timeout=timeout,
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:200]}...")
            transcript.append(("Extract text via skill", response_text[:200]))
            checks.append("Got response from overlord.chat()")

            # 6. Check response quality
            print("\n6. Checking response...")
            response_lower = response_text.lower()
            relevant = any(term in response_lower for term in [
                "extract", "pdf", "text", "document", "process",
            ])
            if relevant:
                checks.append("Response is relevant to PDF extraction")
            else:
                checks.append("WARNING: Response relevance unclear")

            print("\n7. Cleaning up...")
            # Clean up RCE cache
            try:
                await rce_client.delete_skill("pdf-processing")
            except Exception:
                pass
            await rce_client.close()
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
                rce_client = getattr(self.formation, "_rce_client", None)
                if rce_client:
                    await rce_client.close()
                await self.cleanup_formation()
            except Exception:
                pass
            return False


if __name__ == "__main__":
    test = TestSkillExecution()
    result = asyncio.run(test.test_skill_execution())
    sys.exit(0 if result else 1)
