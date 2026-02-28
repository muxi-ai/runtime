#!/usr/bin/env python3
"""Test 5_2: File generation and artifacts"""

import asyncio
import time
import os

from base_artifacts_test import BaseArtifactsTest


class Test52(BaseArtifactsTest):
    """Test class for 5_2."""

    async def test_main(self):
        """Test document generation functionality."""
        test_name = "5_2"
        self.print_test_header(test_name, "Document Generation using File Generation MCP")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: Word Document Creation
            print("\n  1. Testing Word document creation...")
            word_prompt = "Create a Word document with a project status report including sections for overview, progress, and next steps"
            transcript.append(("User", word_prompt))

            response1 = await self.overlord.chat(
                word_prompt,
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

            # Check for Word document artifacts
            artifacts1 = getattr(response1, 'artifacts', []) or []
            if artifacts1:
                print(f"    ✓ Generated {len(artifacts1)} Word document artifact(s)")
                checks_passed.append(f"Word document generation: {len(artifacts1)} artifacts")

                # Validate Word document properties
                artifact = artifacts1[0]
                if hasattr(artifact, 'filename') and artifact.filename and artifact.filename.endswith('.docx'):
                    print(f"    ✓ Word document filename: {artifact.filename}")
                    checks_passed.append("Word document has .docx extension")

                expected_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if hasattr(artifact, 'data_url') and artifact.data_url and expected_mime in artifact.data_url:
                    print("    ✓ Word document contains proper MIME type")
                    checks_passed.append("Word document has valid MIME type")
            else:
                print("    ✗ No Word document artifacts generated")
                all_passed = False

            # Test 2: PDF Report Generation
            print("\n  2. Testing PDF report generation...")
            pdf_prompt = "Generate a PDF report with executive summary and financial data"
            transcript.append(("User", pdf_prompt))

            response2 = await self.overlord.chat(
                pdf_prompt,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result2 = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append(("System", result2[:100] + "..." if len(result2) > 100 else result2))

            artifacts2 = getattr(response2, 'artifacts', []) or []
            if artifacts2:
                print(f"    ✓ Generated {len(artifacts2)} PDF report artifact(s)")
                checks_passed.append("PDF report generated")

                # Validate PDF properties
                artifact = artifacts2[0]
                if hasattr(artifact, 'filename') and artifact.filename and artifact.filename.endswith('.pdf'):
                    print(f"    ✓ PDF filename: {artifact.filename}")
                    checks_passed.append("PDF has .pdf extension")

                if hasattr(artifact, 'data_url') and artifact.data_url and "application/pdf" in artifact.data_url:
                    print("    ✓ PDF contains proper MIME type")
                    checks_passed.append("PDF has valid MIME type")

                if hasattr(artifact, 'thumbnail') and artifact.thumbnail and artifact.thumbnail.startswith("data:image/"):
                    print("    ✓ PDF has thumbnail preview")
                    checks_passed.append("PDF has thumbnail")
            else:
                print("    ✗ No PDF report artifacts")
                all_passed = False

            # Test 3: Multi-Section Business Proposal
            print("\n  3. Testing multi-section document generation...")
            proposal_prompt = "Create a comprehensive business proposal with cover page, executive summary, and appendices"
            transcript.append(("User", proposal_prompt))

            response3 = await self.overlord.chat(
                proposal_prompt,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result3 = response3.content if hasattr(response3, "content") else str(response3)
            transcript.append(("System", result3[:100] + "..." if len(result3) > 100 else result3))

            artifacts3 = getattr(response3, 'artifacts', []) or []
            if artifacts3:
                print(f"    ✓ Generated business proposal with {len(artifacts3)} artifact(s)")
                checks_passed.append(f"Business proposal: {len(artifacts3)} artifacts")

                # Check for multi-section structure in response
                if any(keyword in result3.lower() for keyword in ["cover", "executive", "summary", "appendix", "section"]):
                    print("    ✓ Response mentions multi-section structure")
                    checks_passed.append("Multi-section structure mentioned")
            else:
                print("    ✗ No business proposal artifacts")
                all_passed = False

            # Test 4: Document validation summary
            print("\n  4. Validating all document artifacts...")
            all_artifacts = artifacts1 + artifacts2 + artifacts3

            for i, artifact in enumerate(all_artifacts):
                if hasattr(artifact, 'type') and artifact.type:
                    print(f"    ✓ Artifact {i+1} has type: {artifact.type}")

                if hasattr(artifact, 'format') and artifact.format:
                    print(f"    ✓ Artifact {i+1} has format: {artifact.format}")

            if all_artifacts:
                checks_passed.append(f"Total document artifacts generated: {len(all_artifacts)}")
            else:
                print("    ✗ No document artifacts to validate")
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
        print("🧪 AREA 5_2")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Test52()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    import os
    try:
        main()
        print("SUCCESS", flush=True)
        os._exit(0)
    except SystemExit as e:
        if e.code == 0:
            print("SUCCESS", flush=True)
        os._exit(e.code or 0)
    except Exception:
        os._exit(1)
