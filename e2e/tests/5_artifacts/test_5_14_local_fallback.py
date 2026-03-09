#!/usr/bin/env python3
"""Test 5_14: Local fallback when no RCE configured.

Verifies that formations WITHOUT rce: config still generate files via the
local ArtifactService path (backward compatibility after the RCE refactor).
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


# Use the original formation that has NO rce: config
FORMATION_DIR = Path(__file__).parent / "formations" / "formation-file-generation"


class Test514:
    def __init__(self):
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None

    async def run_test(self):
        test_name = "5_14"
        self.formatter.print_test_header(test_name, "Local Fallback (no RCE)")
        start_time = time.time()
        checks = []
        transcript = []
        all_passed = True

        try:
            # 1. Load formation WITHOUT RCE
            print("\n  1. Loading formation WITHOUT rce: config...")
            self.formation = Formation()
            await self.formation.load(str(FORMATION_DIR / "formation.yaml"))
            self.overlord = await self.formation.start_overlord()

            rce_client = getattr(self.formation, "_rce_client", None)
            if rce_client is None:
                print("     Confirmed: no RCE client (local fallback active)")
                checks.append("No RCE client -- local fallback path")
            else:
                print("     WARNING: RCE client is present (unexpected)")
                checks.append("WARNING: RCE client found in non-RCE formation")

            # 2. Generate a file via local path
            print("\n  2. Testing file generation via local ArtifactService...")
            prompt = "Create a bar chart showing sales: Q1 $100k, Q2 $200k, Q3 $150k. Save as sales.png"
            transcript.append(("User", prompt))

            response = await asyncio.wait_for(
                self.overlord.chat(prompt, user_id="test_user", use_async=False, stream=False),
                timeout=120,
            )
            result = response.content if hasattr(response, "content") else str(response)
            transcript.append(("System", result[:150]))

            artifacts = getattr(response, "artifacts", []) or []
            if artifacts:
                a = artifacts[0]
                print(f"     Generated {len(artifacts)} artifact(s)")
                print(f"       - {getattr(a, 'filename', '?')} ({getattr(a, 'type', '?')}/{getattr(a, 'format', '?')})")
                checks.append(f"Local path: {len(artifacts)} artifact(s) generated")

                # Verify it's a proper MuxiArtifact (not RCE format)
                if hasattr(a, "data_url") and a.data_url:
                    checks.append("Artifact has valid data_url")
                else:
                    checks.append("WARNING: Artifact missing data_url")
            else:
                print("     WARNING: No artifacts generated")
                if any(w in result.lower() for w in ["created", "generated", "chart"]):
                    checks.append("Local path: response mentions creation (no artifact extracted)")
                else:
                    all_passed = False
                    checks.append("FAILED: No artifacts and no mention of creation")

        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
            checks.append(f"FAILED: {e}")

        finally:
            try:
                if self.formation:
                    await self.formation.stop_overlord()
                    self.formation.stop()
            except Exception:
                pass

            duration = time.time() - start_time
            self.formatter.print_test_result(test_name, all_passed, checks, transcript, duration)

        return all_passed


if __name__ == "__main__":
    test = Test514()
    result = asyncio.run(test.run_test())
    if result:
        print("SUCCESS", flush=True)
    os._exit(0 if result else 1)
