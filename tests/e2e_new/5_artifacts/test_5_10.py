#!/usr/bin/env python3
"""Test test_5_10: Intelligent File Generation"""

import asyncio
import time
import os

from .base_artifacts_test import BaseArtifactsTest


class Testtest510(BaseArtifactsTest):
    """Test class for test_5_10."""

    async def test_main(self):
        """Test intelligent file generation functionality."""
        test_name = "test_5_10"
        self.print_test_header(test_name, "Intelligent File Generation")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: Context-Aware File Creation
            print("\n  1. Testing Context-aware file creation...")
            prompt1 = "Analyze this sales data and create appropriate visualizations and reports"
            transcript.append(("User", prompt1))

            response1 = await self.overlord.chat(
                prompt1,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result1 = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append(("System", result1[:100] + "..." if len(result1) > 100 else result1))

            artifacts1 = getattr(response1, 'artifacts', [])
            if artifacts1:
                print(f"    ✓ Generated {len(artifacts1)} artifact(s) for Context-aware file creation")
                checks_passed.append("Context-aware files generated")
            else:
                print("    ✗ No artifacts generated for Context-aware file creation")
                all_passed = False

            # Test 2: Implicit Format Detection
            print("\n  2. Testing Implicit format detection...")
            prompt2 = "I need to present quarterly results to the board next week"
            transcript.append(("User", prompt2))

            response2 = await self.overlord.chat(
                prompt2,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result2 = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append(("System", result2[:100] + "..." if len(result2) > 100 else result2))

            artifacts2 = getattr(response2, 'artifacts', [])
            if artifacts2:
                print(f"    ✓ Generated {len(artifacts2)} artifact(s) for Implicit format detection")
                checks_passed.append("Implicit presentation files created")
            else:
                print("    ✗ No artifacts generated for Implicit format detection")
                all_passed = False

            # Test 3: Smart File Organization
            print("\n  3. Testing Smart file organization...")
            prompt3 = "Organize these project files into a proper structure with documentation"
            transcript.append(("User", prompt3))

            response3 = await self.overlord.chat(
                prompt3,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result3 = response3.content if hasattr(response3, "content") else str(response3)
            transcript.append(("System", result3[:100] + "..." if len(result3) > 100 else result3))

            artifacts3 = getattr(response3, 'artifacts', [])
            if artifacts3:
                print(f"    ✓ Generated {len(artifacts3)} artifact(s) for Smart file organization")
                checks_passed.append("Smart organization completed")
            else:
                print("    ✗ No artifacts generated for Smart file organization")
                all_passed = False

            # Final validation
            print("\n  4. Validating all artifacts...")
            all_artifacts = artifacts1 + artifacts2 + artifacts3

            if all_artifacts:
                print(f"    ✓ Total artifacts generated: {len(all_artifacts)}")
                checks_passed.append(f"Total intelligent file generation artifacts: {len(all_artifacts)}")

                for i, artifact in enumerate(all_artifacts):
                    if hasattr(artifact, 'filename') and artifact.filename:
                        print(f"    ✓ Artifact {i+1}: {artifact.filename}")
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
        print("🧪 AREA TEST_5_10")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Testtest510()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
