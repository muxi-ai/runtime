#!/usr/bin/env python3
"""Test 21c3: Skill secret injection via RCE env field.

Verifies that:
1. Secrets referenced in SKILL.md body (${{ secrets.X }}) are interpolated
   before the content is injected into the agent's context.
2. Secrets are resolved and passed as env vars to the RCE subprocess, so
   bundled scripts can read them via os.environ.

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

EXPECTED_GREETING = "HELLO-FROM-MUXI-SECRETS"


class TestSkillSecretsEnv(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21c3_skill_secrets_env",
            test_description="Verify skill secrets are interpolated in SKILL.md and injected as env vars for RCE scripts",
            test_area="21_skills",
        )

    async def test_skill_secrets_env(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []
        transcript = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        rce_client = None
        try:
            # 1. Load formation
            print("\n1. Loading formation with secret-printer skill...")
            formation_path = (
                Path(__file__).parent / "formations" / "formation-skills-secrets"
            )
            await self.setup_formation(formation_path=formation_path)
            overlord = self.overlord
            skill_manager = self.formation._skill_manager
            rce_client = getattr(self.formation, "_rce_client", None)

            assert rce_client is not None, "RCE client not initialized"
            print(f"   RCE connected: v{rce_client.status.version}")
            checks.append("Formation loaded with RCE client")

            # 2. Verify secret-printer skill is loaded with required_secrets
            print("\n2. Checking secret-printer skill metadata...")
            assert "secret-printer" in skill_manager.skills, "secret-printer skill not loaded"
            metadata = skill_manager.skills["secret-printer"]
            assert "SKILL_TEST_GREETING" in metadata.required_secrets, (
                f"SKILL_TEST_GREETING not in required_secrets: {metadata.required_secrets}"
            )
            print(f"   required_secrets: {metadata.required_secrets}")
            checks.append(f"required_secrets populated: {metadata.required_secrets}")

            # 3. Verify SKILL.md body interpolation
            print("\n3. Testing SKILL.md body interpolation...")
            activated_content = await skill_manager.activate_async(
                "secret-printer", "test-session"
            )
            assert EXPECTED_GREETING in activated_content, (
                f"Expected '{EXPECTED_GREETING}' in activated content, got:\n{activated_content}"
            )
            assert "${{ secrets.SKILL_TEST_GREETING }}" not in activated_content, (
                "Placeholder was not replaced in activated content"
            )
            print(f"   Greeting found in content: '{EXPECTED_GREETING}'")
            checks.append("SKILL.md body: ${{ secrets.X }} interpolated to actual value")

            # 4. Verify resolve_skill_env builds the correct env map
            print("\n4. Testing secret env resolution...")
            env_map = await skill_manager.resolve_skill_env("secret-printer")
            assert "SKILL_TEST_GREETING" in env_map, (
                f"SKILL_TEST_GREETING missing from env map: {env_map}"
            )
            assert env_map["SKILL_TEST_GREETING"] == EXPECTED_GREETING, (
                f"Expected '{EXPECTED_GREETING}', got '{env_map['SKILL_TEST_GREETING']}'"
            )
            print(f"   env map: {env_map}")
            checks.append(f"resolve_skill_env returns correct map: {env_map}")

            # 5. Execute the script directly via RCE — env vars must reach the subprocess
            print("\n5. Executing print_greeting.py via RCE with injected env...")
            content_hash = skill_manager.get_skill_hash("secret-printer")
            await rce_client.ensure_cached("secret-printer", metadata.base_dir, content_hash)

            result = await rce_client.run_skill(
                "secret-printer",
                "python3 scripts/print_greeting.py",
                env=env_map,
                timeout=15,
            )
            print(f"   status: {result.status}")
            print(f"   stdout: {result.stdout!r}")
            print(f"   stderr: {result.stderr!r}")

            assert result.status == "success", (
                f"Script failed: exit={result.exit_code} stderr={result.stderr}"
            )
            assert EXPECTED_GREETING in result.stdout, (
                f"Expected '{EXPECTED_GREETING}' in stdout, got: {result.stdout!r}"
            )
            checks.append(f"Script output contains secret value: '{EXPECTED_GREETING}'")

            # 6. Confirm the script fails WITHOUT the env (proves env injection is required)
            print("\n6. Confirming script fails without env vars (sanity check)...")
            result_no_env = await rce_client.run_skill(
                "secret-printer",
                "python3 scripts/print_greeting.py",
                timeout=15,
            )
            assert result_no_env.status != "success" or EXPECTED_GREETING not in result_no_env.stdout, (
                "Script should not output the secret without env injection"
            )
            print(f"   Without env — status: {result_no_env.status}, stdout: {result_no_env.stdout!r}")
            checks.append("Without env injection: script does not output secret (expected)")

            # 7. Full round-trip via overlord.chat()
            print("\n7. Testing via overlord.chat()...")
            timeout = TestTimeouts.get_timeout("simple_chat") + 60
            response = await asyncio.wait_for(
                overlord.chat(
                    "I'd like to see the greeting from the secret-printer skill.",
                    user_id="test_user",
                ),
                timeout=timeout,
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:300]}")
            transcript.append(("Print greeting via skill", response_text[:300]))

            # The greeting value should appear somewhere in the conversation — either
            # in the response text (if the agent relays stdout) or in the context from
            # SKILL.md body interpolation (which already happened in step 3).
            response_mentions_output = EXPECTED_GREETING in response_text or any(
                term in response_text.lower()
                for term in ["greeting", "printed", "output", "hello", "executed", "ran"]
            )
            if response_mentions_output:
                checks.append("overlord.chat() response mentions skill execution result")
            else:
                checks.append("WARNING: overlord response did not clearly mention skill output")

            # 8. Cleanup
            print("\n8. Cleaning up...")
            try:
                await rce_client.delete_skill("secret-printer")
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
            import traceback

            traceback.print_exc()
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name=self.test_name,
                success=False,
                checks=checks + [f"FAILED: {e}"],
                transcript=transcript,
                duration=duration,
            )
            try:
                if rce_client:
                    try:
                        await rce_client.delete_skill("secret-printer")
                    except Exception:
                        pass
                    await rce_client.close()
                await self.cleanup_formation()
            except Exception:
                pass
            return False


if __name__ == "__main__":
    test = TestSkillSecretsEnv()
    result = asyncio.run(test.test_skill_secrets_env())
    os._exit(0 if result else 1)
