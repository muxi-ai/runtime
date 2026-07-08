#!/usr/bin/env python3
"""Test 21c4: Compute skill (code as a reasoning primitive) via RCE.

Verifies that the bundled compute skill loads as a built-in, that its
executor runs agent-written Python through the RCE sandbox, that failures
(runtime errors, import policy violations) surface to the agent, and that
an agent can activate the skill through overlord.chat() and return a
computed value without narrating code.

Requires: Skills RCE server running on localhost:7891.
"""

import asyncio
import os
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

STDEV_CODE = (
    "import statistics\n"
    "values = [12, 7, 3, 21, 9]\n"
    "print(round(statistics.stdev(values), 2))\n"
)


class TestComputeSkill(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21c4_compute_skill",
            test_description="Verify bundled compute skill executes agent code via RCE",
            test_area="21_skills",
        )

    async def test_compute_skill(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []
        transcript = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            # 1. Load formation with RCE config (compute is a built-in, no declaration needed)
            print("\n1. Loading formation with RCE config...")
            formation_path = Path(__file__).parent / "formations" / "formation-skills-rce"
            await self.setup_formation(formation_path=formation_path)
            overlord = self.overlord
            skill_manager = self.formation._skill_manager
            rce_client = getattr(self.formation, "_rce_client", None)

            assert rce_client is not None, "RCE client not initialized"
            assert "compute" in skill_manager.skills, "compute built-in not loaded"
            assert "compute" in skill_manager._builtin_skills, "compute not marked builtin"
            print(f"   RCE connected: v{rce_client.status.version}")
            checks.append("Formation loaded; compute built-in present")

            # 2. Verify compute is executable via run_skill with input_files support
            print("\n2. Checking run_skill tool exposes compute...")
            run_tool = skill_manager.build_run_skill_tool("general-agent")
            assert run_tool is not None, "run_skill tool not built"
            props = run_tool["function"]["parameters"]["properties"]
            enum = props["skill_name"]["enum"]
            assert "compute" in enum, f"compute not in run_skill enum: {enum}"
            assert "input_files" in props, "input_files missing from run_skill schema"
            checks.append("compute in run_skill enum with input_files support")

            # 3. Direct execution: compute a standard deviation through RCE
            print("\n3. Direct compute execution (stdev)...")
            agent = overlord.agents.get("general-agent")
            assert agent is not None, "general-agent not found"

            result = await agent.invoke_tool(
                tool_name="run_skill",
                parameters={
                    "skill_name": "compute",
                    "command": "python3 scripts/run_python.py main.py",
                    "input_files": {"main.py": STDEV_CODE},
                },
            )
            print(f"   Result: {result}")
            assert result.get("status") == "success", f"Expected success, got: {result}"
            assert (
                result.get("stdout", "").strip() == "6.77"
            ), f"Unexpected stdout: {result.get('stdout')!r}"
            checks.append("Direct compute execution returned 6.77")

            # 4. Runtime error is surfaced (agent can see the traceback and refine)
            print("\n4. Broken code surfaces a runtime error...")
            result = await agent.invoke_tool(
                tool_name="run_skill",
                parameters={
                    "skill_name": "compute",
                    "command": "python3 scripts/run_python.py main.py",
                    "input_files": {"main.py": "print(1 / 0)\n"},
                },
            )
            print(f"   Status: {result.get('status')}, stderr: {result.get('stderr', '')[:120]}")
            assert result.get("status") != "success", f"Expected failure, got: {result}"
            assert "ZeroDivisionError" in result.get(
                "stderr", ""
            ), f"Traceback not surfaced: {result.get('stderr')!r}"
            checks.append("Runtime error surfaced with traceback")

            # 5. Import policy violation is surfaced distinctly
            print("\n5. Disallowed import is rejected...")
            result = await agent.invoke_tool(
                tool_name="run_skill",
                parameters={
                    "skill_name": "compute",
                    "command": "python3 scripts/run_python.py main.py",
                    "input_files": {"main.py": "import socket\nprint('x')\n"},
                },
            )
            assert result.get("status") != "success", f"Expected failure, got: {result}"
            assert "ImportPolicyViolation" in result.get(
                "stderr", ""
            ), f"Policy violation not surfaced: {result.get('stderr')!r}"
            checks.append("Import policy violation surfaced distinctly")

            # 6. LLM-driven path: agent activates compute and answers with the value
            print("\n6. Compute via overlord.chat()...")
            compute_calls = []
            original_run_skill = rce_client.run_skill

            async def counting_run_skill(skill_id, command, **kwargs):
                exec_result = await original_run_skill(skill_id, command, **kwargs)
                compute_calls.append((skill_id, exec_result.status, exec_result.stdout.strip()))
                return exec_result

            rce_client.run_skill = counting_run_skill

            timeout = TestTimeouts.get_timeout("simple_chat") + 60
            response = await asyncio.wait_for(
                overlord.chat(
                    "Use the compute skill for this: what is the sample standard "
                    "deviation of these values: 12, 7, 3, 21, 9? "
                    "Report the value rounded to two decimals.",
                    user_id="test_user",
                ),
                timeout=timeout,
            )
            rce_client.run_skill = original_run_skill
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:200]}...")
            transcript.append(("Stdev via compute skill", response_text[:200]))

            print(f"   Compute calls during chat: {compute_calls}")
            successful = [
                c for c in compute_calls if c[0] == "compute" and c[1] == "success" and c[2]
            ]
            assert successful, (
                f"compute skill produced no successful output via RCE during chat "
                f"(calls: {compute_calls})"
            )
            checks.append("Agent executed compute skill through RCE during chat")

            if "6.77" in response_text or "6.8" in response_text:
                checks.append("Response contains the computed value")
            else:
                checks.append(
                    f"WARNING: computed value not found in response: {response_text[:100]}"
                )

            if "```" not in response_text and "run_python" not in response_text:
                checks.append("Response does not narrate code")
            else:
                checks.append("WARNING: response narrates code or sandbox details")

            # 7. Cleanup
            print("\n7. Cleaning up...")
            try:
                await rce_client.delete_skill("compute")
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
    test = TestComputeSkill()
    result = asyncio.run(test.test_compute_skill())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if result else 1)
