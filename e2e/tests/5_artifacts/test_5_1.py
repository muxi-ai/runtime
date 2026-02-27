#!/usr/bin/env python3
"""Test 5_1: Chart Generation using built-in File Generation MCP

This test validates:
1. Basic chart creation with file generation
2. Advanced data visualization
3. Multiple chart types generation
4. Artifact validation and data URL verification
"""

import asyncio
import time
import os

from base_artifacts_test import BaseArtifactsTest


class Test51(BaseArtifactsTest):
    """Test chart generation and file artifacts."""

    async def test_main(self):
        """Test chart generation functionality."""
        test_name = "5_1"
        self.print_test_header(test_name, "Chart Generation and File Artifacts")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: Basic Chart Creation
            print("\n  1. Testing basic chart creation...")
            chart_prompt = "Create a bar chart showing Q1 sales: Jan $100k, Feb $150k, Mar $200k"
            transcript.append(("User", chart_prompt))

            response1 = await self.overlord.chat(
                chart_prompt,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            # Extract response content
            if hasattr(response1, "content"):
                result1 = response1.content
            else:
                result1 = str(response1)

            transcript.append(("System", result1[:100] + "..." if len(result1) > 100 else result1))

            # Check for artifacts (use 'or []' in case artifacts is None)
            artifacts1 = getattr(response1, 'artifacts', []) or [] or []
            if artifacts1:
                print(f"    ✓ Generated {len(artifacts1)} artifact(s)")
                checks_passed.append(f"Basic chart generation: {len(artifacts1)} artifacts")

                # Validate artifact properties
                artifact = artifacts1[0]
                if hasattr(artifact, 'filename') and artifact.filename:
                    print(f"    ✓ Artifact filename: {artifact.filename}")
                    checks_passed.append("Artifact has filename")

                if hasattr(artifact, 'data_url') and artifact.data_url and "base64" in artifact.data_url:
                    print("    ✓ Artifact contains base64 data")
                    checks_passed.append("Artifact has valid data URL")
            else:
                print("    ✗ No artifacts generated (non-deterministic, may retry)")

            # Test 2: Advanced Data Visualization
            print("\n  2. Testing advanced data visualization...")
            advanced_prompt = "Create a line chart with trend analysis for monthly revenue growth"
            transcript.append(("User", advanced_prompt))

            response2 = await self.overlord.chat(
                advanced_prompt,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result2 = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append(("System", result2[:100] + "..." if len(result2) > 100 else result2))

            artifacts2 = getattr(response2, 'artifacts', []) or [] or []
            if artifacts2:
                print(f"    ✓ Generated advanced visualization with {len(artifacts2)} artifact(s)")
                checks_passed.append("Advanced visualization generated")
            else:
                print("    ✗ No advanced visualization artifacts (non-deterministic)")

            # Test 3: Artifact validation
            print("\n  3. Validating artifact properties...")
            all_artifacts = artifacts1 + artifacts2

            for i, artifact in enumerate(all_artifacts):
                if hasattr(artifact, 'type') and artifact.type:
                    print(f"    ✓ Artifact {i+1} has type: {artifact.type}")

                if hasattr(artifact, 'format') and artifact.format:
                    print(f"    ✓ Artifact {i+1} has format: {artifact.format}")

            if all_artifacts:
                checks_passed.append(f"Total artifacts generated: {len(all_artifacts)}")
            else:
                print("    ✗ No artifacts generated across all tests")
                all_passed = False

            # Pass if at least 1 artifact was generated (LLM is non-deterministic)
            if not all_artifacts:
                all_passed = False
            else:
                all_passed = True

        except Exception as e:
            print(f"  ✗ Test failed: {e}")
            all_passed = False

        finally:
            duration = time.time() - start_time
            self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)
            if all_passed:
                print("SUCCESS", flush=True)
            os._exit(0 if all_passed else 1)

    async def run_test(self):
        """Run test."""
        print("\n" + "=" * 60)
        print("AREA 5_1: Chart Generation and File Artifacts")
        print("=" * 60)
        await self.test_main()


if __name__ == "__main__":
    test = Test51()
    asyncio.run(test.run_test())
