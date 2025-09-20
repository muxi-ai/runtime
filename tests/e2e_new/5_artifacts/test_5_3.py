#!/usr/bin/env python3
"""Test 5_3: File generation and artifacts"""

import asyncio
import time
import os

from .base_artifacts_test import BaseArtifactsTest


class Test53(BaseArtifactsTest):
    """Test class for 5_3."""

    async def test_main(self):
        """Test spreadsheet generation functionality."""
        test_name = "5_3"
        self.print_test_header(test_name, "Spreadsheet Generation using File Generation MCP")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: Basic Excel File Creation
            print("\n  1. Testing Excel file creation...")
            excel_prompt = "Create an Excel file with sales data: Product A: 100 units, Product B: 150 units, Product C: 75 units"
            transcript.append(("User", excel_prompt))

            response1 = await self.overlord.chat(
                excel_prompt,
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

            # Check for Excel artifacts
            artifacts1 = getattr(response1, 'artifacts', [])
            if artifacts1:
                print(f"    ✓ Generated {len(artifacts1)} Excel file artifact(s)")
                checks_passed.append(f"Excel file generation: {len(artifacts1)} artifacts")

                # Validate Excel file properties
                artifact = artifacts1[0]
                if hasattr(artifact, 'filename') and artifact.filename and ('.xlsx' in artifact.filename or '.xls' in artifact.filename):
                    print(f"    ✓ Excel filename: {artifact.filename}")
                    checks_passed.append("Excel file has proper extension")

                if hasattr(artifact, 'data_url') and artifact.data_url and "data:" in artifact.data_url:
                    print("    ✓ Excel file contains data URL")
                    checks_passed.append("Excel file has valid data URL")
            else:
                print("    ✗ No Excel file artifacts generated")
                all_passed = False

            # Test 2: Complex Data Analysis Spreadsheet
            print("\n  2. Testing complex data analysis spreadsheet...")
            analysis_prompt = "Generate a spreadsheet with pivot tables and charts for quarterly sales analysis"
            transcript.append(("User", analysis_prompt))

            response2 = await self.overlord.chat(
                analysis_prompt,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result2 = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append(("System", result2[:100] + "..." if len(result2) > 100 else result2))

            artifacts2 = getattr(response2, 'artifacts', [])
            if artifacts2:
                print(f"    ✓ Generated {len(artifacts2)} analysis spreadsheet artifact(s)")
                checks_passed.append("Complex analysis spreadsheet generated")

                # Check for analysis features in response
                if any(keyword in result2.lower() for keyword in ["pivot", "chart", "analysis", "quarterly"]):
                    print("    ✓ Response mentions analysis features")
                    checks_passed.append("Analysis features mentioned")
            else:
                print("    ✗ No analysis spreadsheet artifacts")
                all_passed = False

            # Test 3: Financial Model Creation
            print("\n  3. Testing financial model spreadsheet...")
            financial_prompt = "Create a financial model spreadsheet with revenue projections and cost analysis"
            transcript.append(("User", financial_prompt))

            response3 = await self.overlord.chat(
                financial_prompt,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            result3 = response3.content if hasattr(response3, "content") else str(response3)
            transcript.append(("System", result3[:100] + "..." if len(result3) > 100 else result3))

            artifacts3 = getattr(response3, 'artifacts', [])
            if artifacts3:
                print(f"    ✓ Generated financial model with {len(artifacts3)} artifact(s)")
                checks_passed.append(f"Financial model: {len(artifacts3)} artifacts")

                # Check for financial model features in response
                if any(keyword in result3.lower() for keyword in ["revenue", "projection", "cost", "financial", "model"]):
                    print("    ✓ Response mentions financial model features")
                    checks_passed.append("Financial model features mentioned")
            else:
                print("    ✗ No financial model artifacts")
                all_passed = False

            # Test 4: Spreadsheet validation summary
            print("\n  4. Validating all spreadsheet artifacts...")
            all_artifacts = artifacts1 + artifacts2 + artifacts3

            spreadsheet_count = 0
            for i, artifact in enumerate(all_artifacts):
                if hasattr(artifact, 'filename') and artifact.filename:
                    if any(ext in artifact.filename.lower() for ext in ['.xlsx', '.xls', '.csv']):
                        spreadsheet_count += 1
                        print(f"    ✓ Artifact {i+1} is spreadsheet: {artifact.filename}")

                if hasattr(artifact, 'type') and artifact.type:
                    print(f"    ✓ Artifact {i+1} has type: {artifact.type}")

            if spreadsheet_count > 0:
                checks_passed.append(f"Total spreadsheet artifacts: {spreadsheet_count}")
            else:
                print("    ✗ No valid spreadsheet artifacts found")
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
        print("🧪 AREA 5_3")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Test53()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
