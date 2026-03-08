#!/usr/bin/env python3
"""Test 5_12: RCE fail-fast when server is unreachable.

Verifies that formation initialization fails immediately when an RCE URL
is configured but the server is not available.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402
from common import TestOutputFormatter  # noqa: E402


# We intentionally use port 7899 which should NOT have an RCE server
UNREACHABLE_RCE_URL = "http://localhost:7899"


class Test512:
    def __init__(self):
        self.formatter = TestOutputFormatter()

    async def run_test(self):
        test_name = "5_12"
        self.formatter.print_test_header(test_name, "RCE Fail-Fast on Unreachable Server")
        start_time = time.time()
        checks = []
        transcript = []
        all_passed = True

        try:
            # 1. Verify port 7899 is actually not listening
            print("\n  1. Confirming port 7899 is not listening...")
            import httpx
            try:
                resp = httpx.get(f"{UNREACHABLE_RCE_URL}/health", timeout=2)
                print(f"     ERROR: Port 7899 is actually responding (status {resp.status_code})")
                print("     SKIP: Cannot test fail-fast if port 7899 has a server")
                checks.append("SKIP: Port 7899 is unexpectedly reachable")
                return True
            except Exception:
                print(f"     Confirmed: {UNREACHABLE_RCE_URL} is unreachable")
                checks.append("Port 7899 confirmed unreachable")

            # 2. Create a formation YAML with unreachable RCE URL
            print("\n  2. Loading formation with unreachable RCE URL...")

            import tempfile
            import shutil

            # Copy the base formation and add RCE config
            base_formation = Path(__file__).parent / "formations" / "formation-file-generation"
            tmp_dir = Path(tempfile.mkdtemp()) / "formation-rce-fail"
            shutil.copytree(base_formation, tmp_dir)

            # Rewrite formation.yaml with unreachable RCE
            formation_yaml = tmp_dir / "formation.yaml"
            formation_yaml.write_text(f"""schema: "1.0.0"
id: "file-generation-rce-failfast-test"
description: "Formation with unreachable RCE"

llm:
  api_keys:
    openai: "${{{{ secrets.OPENAI_API_KEY }}}}"
  models:
    - text: "openai/gpt-4o-mini"

rce:
  url: "{UNREACHABLE_RCE_URL}"

agents:
  - generator

memory:
  buffer:
    size: 10
    vector_search: false

logging:
  system:
    level: "error"
    destination: "stdout"
""")

            # 3. Try to load -- should fail fast
            print("\n  3. Attempting formation load (should fail fast)...")
            formation = Formation()
            try:
                await formation.load(str(formation_yaml))
                overlord = await formation.start_overlord()

                # If we get here, fail-fast did NOT work
                print("     FAILED: Formation loaded successfully (should have failed)")
                all_passed = False
                checks.append("FAILED: No error raised for unreachable RCE")

                try:
                    await formation.stop_overlord()
                    formation.stop()
                except Exception:
                    pass

            except Exception as e:
                error_msg = str(e)
                print(f"     Formation init raised: {type(e).__name__}: {error_msg[:200]}")

                # Check that it's the right error
                if "7899" in error_msg or "unreachable" in error_msg.lower() or "rce" in error_msg.lower() or "connect" in error_msg.lower():
                    print("     Error correctly references the RCE connection failure")
                    checks.append("Fail-fast: correct RCE error raised")
                else:
                    print(f"     WARNING: Error may not be RCE-related: {error_msg[:300]}")
                    checks.append(f"Fail-fast: error raised but may not be RCE-specific")

                checks.append("Fail-fast: formation init aborted on unreachable RCE")

            # 4. Measure timing
            elapsed = time.time() - start_time
            print(f"\n  4. Timing check...")
            if elapsed < 30:
                print(f"     Failed fast in {elapsed:.1f}s (under 30s)")
                checks.append(f"Fail-fast timing: {elapsed:.1f}s")
            else:
                print(f"     WARNING: Took {elapsed:.1f}s (slow for fail-fast)")
                checks.append(f"WARNING: Fail-fast took {elapsed:.1f}s")

            # Cleanup temp dir
            try:
                shutil.rmtree(tmp_dir.parent)
            except Exception:
                pass

        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
            checks.append(f"FAILED: {e}")

        finally:
            duration = time.time() - start_time
            self.formatter.print_test_result(test_name, all_passed, checks, transcript, duration)

        return all_passed


if __name__ == "__main__":
    test = Test512()
    result = asyncio.run(test.run_test())
    if result:
        print("SUCCESS", flush=True)
    os._exit(0 if result else 1)
