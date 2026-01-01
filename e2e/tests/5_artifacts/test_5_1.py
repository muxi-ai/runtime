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

            # Check for artifacts
            artifacts1 = getattr(response1, 'artifacts', [])
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
                print("    ✗ No artifacts generated")
                all_passed = False

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

            artifacts2 = getattr(response2, 'artifacts', [])
            if artifacts2:
                print(f"    ✓ Generated advanced visualization with {len(artifacts2)} artifact(s)")
                checks_passed.append("Advanced visualization generated")
            else:
                print("    ✗ No advanced visualization artifacts")
                all_passed = False

            # Test 3: Multiple Chart Types
            print("\n  3. Testing multiple chart types generation...")
            multi_prompt = "Create both a pie chart and bar chart showing market share data"
            transcript.append(("User", multi_prompt))

            response3 = await self.overlord.chat(
                multi_prompt,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result3 = response3.content if hasattr(response3, "content") else str(response3)
            transcript.append(("System", result3[:100] + "..." if len(result3) > 100 else result3))

            artifacts3 = getattr(response3, 'artifacts', [])
            if len(artifacts3) >= 2:
                print(f"    ✓ Generated multiple charts: {len(artifacts3)} artifacts")
                checks_passed.append(f"Multiple chart types: {len(artifacts3)} artifacts")

                # Validate different chart types
                for i, artifact in enumerate(artifacts3[:2]):
                    if hasattr(artifact, 'filename'):
                        print(f"      Artifact {i+1}: {artifact.filename}")
            else:
                print(f"    ✗ Expected multiple artifacts, got {len(artifacts3)}")
                all_passed = False

            # Test 4: Artifact validation
            print("\n  4. Validating artifact properties...")
            all_artifacts = artifacts1 + artifacts2 + artifacts3

            for i, artifact in enumerate(all_artifacts):
                if hasattr(artifact, 'type') and artifact.type:
                    print(f"    ✓ Artifact {i+1} has type: {artifact.type}")

                if hasattr(artifact, 'format') and artifact.format:
                    print(f"    ✓ Artifact {i+1} has format: {artifact.format}")

            if all_artifacts:
                checks_passed.append(f"Total artifacts generated: {len(all_artifacts)}")
            else:
                print("    ✗ No artifacts to validate")
                all_passed = False

        except Exception as e:
            print(f"  ✗ Test failed: {e}")
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)
        return all_passed

    async def run_test(self):
        """Run test."""
        print("\n" + "=" * 60)
        print("🧪 AREA 5_1")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Test51()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
