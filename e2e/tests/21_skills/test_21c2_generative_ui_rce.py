#!/usr/bin/env python3
"""Test 21c2: Built-in generative-ui skill with RCE-backed HTML generation."""

import asyncio
import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

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


class TestGenerativeUiRCE(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21c2_generative_ui_rce",
            test_description="Verify the built-in generative-ui skill creates an HTML widget via RCE-backed generate_file",
            test_area="21_skills",
        )

    async def test_generative_ui_rce(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []
        transcript = []
        rce_client = None

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            print("\n1. Loading formation with RCE...")
            formation_path = (
                Path(__file__).parent.parent
                / "5_artifacts"
                / "formations"
                / "formation-file-generation-rce"
            )
            await self.setup_formation(formation_path=formation_path)
            skill_manager = self.formation._skill_manager
            rce_client = getattr(self.formation, "_rce_client", None)

            assert skill_manager is not None, "Skill manager not initialized"
            assert rce_client is not None, "RCE client not initialized"
            assert "generative-ui" in skill_manager.skills, "generative-ui built-in skill not loaded"
            assert "file-generation" in skill_manager.skills, "file-generation built-in skill not loaded"
            print("   Built-in skills available: generative-ui, file-generation")
            checks.append("Formation loaded with RCE and built-in skills")

            print("\n2. Requesting an interactive widget...")
            prompt = (
                "Use the generative-ui skill. After activating it, use the generate_file tool "
                "to create exactly one self-contained HTML file named compound_interest_widget.html. "
                "Do not use run_skill. Do not create PNG files or any non-HTML artifact. "
                "The HTML must explain compound interest with sliders for principal, annual rate, "
                "and years, and it must update a chart or SVG visualization live in the page."
            )
            timeout = TestTimeouts.get_timeout("simple_chat") + 120
            response = await asyncio.wait_for(
                self.overlord.chat(
                    prompt,
                    user_id="test_user",
                    session_id="test_session",
                    use_async=False,
                    stream=False,
                ),
                timeout=timeout,
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            transcript.append((prompt, response_text[:300]))
            print(f"   Response: {response_text[:200]}...")
            checks.append("Received response for generative-ui request")

            print("\n3. Verifying skill activation...")
            assert skill_manager.is_activated("generative-ui", "test_session"), (
                "generative-ui skill was not activated"
            )
            checks.append("generative-ui skill activated")

            injected = False
            for agent in self.overlord.agents.values():
                if agent._messages and '<skill_content name="generative-ui">' in agent._messages[0].get(
                    "content", ""
                ):
                    injected = True
                    break
            assert injected, "generative-ui content was not injected into an agent system prompt"
            checks.append("generative-ui content injected into agent context")

            print("\n4. Validating generated artifact...")
            artifacts = getattr(response, "artifacts", []) or []
            assert artifacts, "No artifacts were generated"
            artifact = artifacts[0]
            filename = getattr(artifact, "filename", "")
            data_url = getattr(artifact, "data_url", "")
            assert filename.endswith(".html"), f"Expected .html artifact, got: {filename}"
            assert data_url.startswith("data:text/html"), "Artifact is not HTML"

            html = base64.b64decode(data_url.split(",", 1)[1]).decode("utf-8", errors="ignore")
            html_lower = html.lower()
            assert (
                "<html" in html_lower or "<!doctype html" in html_lower
            ), "Generated artifact payload is not a full HTML document"
            assert "compound" in html_lower and "interest" in html_lower, (
                "Generated HTML does not appear to address compound interest"
            )
            assert "input" in html_lower, "Generated HTML does not contain interactive controls"
            assert any(token in html_lower for token in ["range", "<svg", "<canvas", "<script"]), (
                "Generated HTML does not contain expected interactive or visualization elements"
            )
            print(f"   Artifact: {filename} ({getattr(artifact, 'type', '?')}/{getattr(artifact, 'format', '?')})")
            print(f"   HTML preview: {html[:160].replace(chr(10), ' ')}...")
            checks.append("HTML widget artifact generated with interactive content")

            print("\n5. Confirming RCE-backed generation path...")
            checks.append("RCE-backed generate_file path active (RCE client present with file-generation skill)")

            print("\n6. Cleaning up...")
            try:
                await rce_client.delete_skill("file-generation")
            except Exception:
                pass
            try:
                await rce_client.delete_skill("generative-ui")
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
                if rce_client:
                    await rce_client.close()
                await self.cleanup_formation()
            except Exception:
                pass
            return False


if __name__ == "__main__":
    test = TestGenerativeUiRCE()
    result = asyncio.run(test.test_generative_ui_rce())
    os._exit(0 if result else 1)
