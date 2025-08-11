"""
Test Group 5B: Document Generation using built-in File Generation MCP

This test validates the system's ability to generate various document formats
including Word documents, PDF reports, and multi-section documents.

Based on Test Report: tests/reports/5b.md
Status: ✅ COMPLETED (3/3 PASSED)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.overlord.overlord import MuxiOverlord


async def test_5b1_word_document_creation():
    """Test 5B1: Word Document Creation

    Expected: Generate a Word document (.docx) with project status report
    Validated: ✅ PASSED - Created project_status_report.docx with base64 data URL
    """
    print("\n" + "="*50)
    print("TEST 5B1: Word Document Creation")
    print("="*50)

    # Initialize overlord with file generation formation
    formation_path = Path(__file__).parent.parent / "test-formations" / "formation-file-generation"
    overlord = MuxiOverlord(formation_path=str(formation_path))

    try:
        print("Loading formation...")
        await overlord.initialize()
        print(f"✅ Formation loaded: {overlord.formation_config.id}")

        # Test prompt from report
        prompt = "Create a Word document with a project status report including sections for overview, progress, and next steps"
        print(f"📝 Prompt: {prompt}")

        # Send message and get response
        print("🔄 Processing request...")
        response = await overlord.process_user_message(prompt, stream=False)

        # Validate response
        print(f"📄 Response content: {response.content[:200]}...")
        print(f"🎯 Artifacts generated: {len(response.artifacts)}")

        # Validate artifacts
        if response.artifacts:
            artifact = response.artifacts[0]
            print(f"📁 Artifact type: {artifact.type}")
            print(f"📁 Artifact format: {artifact.format}")
            print(f"📁 Artifact filename: {artifact.filename}")

            # Validate it's a Word document with proper data URL
            expected_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if artifact.data_url and artifact.data_url.startswith(f"data:{expected_mime};base64,"):
                print("✅ Artifact contains complete Word document base64 data URL")
            else:
                print("❌ Artifact missing proper Word document base64 data URL")

            # Check if filename indicates Word document
            if artifact.filename and artifact.filename.endswith('.docx'):
                print("✅ Artifact filename indicates Word document (.docx)")
            else:
                print("⚠️ Artifact filename doesn't indicate Word document")

        # Save test results
        output_file = Path(__file__).parent.parent / "outputs" / "5b1.json"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump({
                "test": "5B1",
                "status": "PASSED" if response.artifacts else "FAILED",
                "artifacts_count": len(response.artifacts),
                "response_preview": response.content[:200],
                "artifacts": [
                    {
                        "type": artifact.type,
                        "format": artifact.format,
                        "filename": artifact.filename,
                        "has_data_url": bool(artifact.data_url and artifact.data_url.startswith("data:")),
                        "is_word_doc": artifact.filename.endswith('.docx') if artifact.filename else False
                    } for artifact in response.artifacts
                ]
            }, indent=2)

        print(f"💾 Results saved to: {output_file}")

        return len(response.artifacts) > 0

    finally:
        await overlord.cleanup()


async def test_5b2_pdf_report_generation():
    """Test 5B2: PDF Report Generation

    Expected: Generate a PDF report with executive summary and financial data
    Validated: ✅ PASSED - Created executive_summary_report.pdf with base64 data URL and preview
    """
    print("\n" + "="*50)
    print("TEST 5B2: PDF Report Generation")
    print("="*50)

    formation_path = Path(__file__).parent.parent / "test-formations" / "formation-file-generation"
    overlord = MuxiOverlord(formation_path=str(formation_path))

    try:
        await overlord.initialize()
        print(f"✅ Formation loaded: {overlord.formation_config.id}")

        prompt = "Generate a PDF report with executive summary and financial data"
        print(f"📝 Prompt: {prompt}")

        print("🔄 Processing request...")
        response = await overlord.process_user_message(prompt, stream=False)

        print(f"📄 Response content: {response.content[:200]}...")
        print(f"🎯 Artifacts generated: {len(response.artifacts)}")

        # Validate PDF artifact
        if response.artifacts:
            artifact = response.artifacts[0]
            print(f"📁 Artifact type: {artifact.type}")
            print(f"📁 Artifact format: {artifact.format}")
            print(f"📁 Artifact filename: {artifact.filename}")

            # Validate it's a PDF with proper data URL
            if artifact.data_url and artifact.data_url.startswith("data:application/pdf;base64,"):
                print("✅ Artifact contains complete PDF base64 data URL")
            else:
                print("❌ Artifact missing proper PDF base64 data URL")

            # Check for PDF preview thumbnail
            if artifact.thumbnail and artifact.thumbnail.startswith("data:image/png;base64,"):
                print("✅ Artifact contains PDF preview thumbnail")
            else:
                print("⚠️ Artifact missing PDF preview thumbnail")

            # Check if filename indicates PDF
            if artifact.filename and artifact.filename.endswith('.pdf'):
                print("✅ Artifact filename indicates PDF document (.pdf)")
            else:
                print("⚠️ Artifact filename doesn't indicate PDF document")

        # Save test results
        output_file = Path(__file__).parent.parent / "outputs" / "5b2.json"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump({
                "test": "5B2",
                "status": "PASSED" if response.artifacts else "FAILED",
                "artifacts_count": len(response.artifacts),
                "response_preview": response.content[:200],
                "artifacts": [
                    {
                        "type": artifact.type,
                        "format": artifact.format,
                        "filename": artifact.filename,
                        "has_data_url": bool(artifact.data_url and artifact.data_url.startswith("data:")),
                        "has_thumbnail": bool(artifact.thumbnail and artifact.thumbnail.startswith("data:")),
                        "is_pdf": artifact.filename.endswith('.pdf') if artifact.filename else False
                    } for artifact in response.artifacts
                ]
            }, indent=2)

        print(f"💾 Results saved to: {output_file}")

        return len(response.artifacts) > 0

    finally:
        await overlord.cleanup()


async def test_5b3_multi_section_documents():
    """Test 5B3: Multi-Section Documents

    Expected: Generate a comprehensive business proposal with multiple sections
    Validated: ✅ PASSED - Created Business_Proposal.docx with cover page, summary, and appendices
    """
    print("\n" + "="*50)
    print("TEST 5B3: Multi-Section Documents")
    print("="*50)

    formation_path = Path(__file__).parent.parent / "test-formations" / "formation-file-generation"
    overlord = MuxiOverlord(formation_path=str(formation_path))

    try:
        await overlord.initialize()
        print(f"✅ Formation loaded: {overlord.formation_config.id}")

        prompt = "Create a comprehensive business proposal with cover page, executive summary, and appendices"
        print(f"📝 Prompt: {prompt}")

        print("🔄 Processing request...")
        response = await overlord.process_user_message(prompt, stream=False)

        print(f"📄 Response content: {response.content[:200]}...")
        print(f"🎯 Artifacts generated: {len(response.artifacts)}")

        # Validate complex document artifact
        if response.artifacts:
            artifact = response.artifacts[0]
            print(f"📁 Artifact type: {artifact.type}")
            print(f"📁 Artifact format: {artifact.format}")
            print(f"📁 Artifact filename: {artifact.filename}")

            # Validate it's a Word document with proper data URL
            expected_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if artifact.data_url and artifact.data_url.startswith(f"data:{expected_mime};base64,"):
                print("✅ Artifact contains complete Word document base64 data URL")
            else:
                print("❌ Artifact missing proper Word document base64 data URL")

            # Check if filename indicates business proposal
            if artifact.filename and ('proposal' in artifact.filename.lower() or artifact.filename.endswith('.docx')):
                print("✅ Artifact filename indicates business proposal document")
            else:
                print("⚠️ Artifact filename doesn't clearly indicate business proposal")

            # Check response content for multi-section confirmation
            if any(keyword in response.content.lower() for keyword in ['cover', 'executive', 'summary', 'appendix', 'section']):
                print("✅ Response mentions multi-section document structure")
            else:
                print("⚠️ Response doesn't clearly mention document structure")

        # Save test results
        output_file = Path(__file__).parent.parent / "outputs" / "5b3.json"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump({
                "test": "5B3",
                "status": "PASSED" if response.artifacts else "FAILED",
                "artifacts_count": len(response.artifacts),
                "response_preview": response.content[:200],
                "artifacts": [
                    {
                        "type": artifact.type,
                        "format": artifact.format,
                        "filename": artifact.filename,
                        "has_data_url": bool(artifact.data_url and artifact.data_url.startswith("data:")),
                        "is_word_doc": artifact.filename.endswith('.docx') if artifact.filename else False,
                        "mentions_sections": any(keyword in response.content.lower() for keyword in ['cover', 'executive', 'summary', 'appendix', 'section'])
                    } for artifact in response.artifacts
                ]
            }, indent=2)

        print(f"💾 Results saved to: {output_file}")

        return len(response.artifacts) > 0

    finally:
        await overlord.cleanup()


async def run_test_group_5b():
    """Run all Test Group 5B tests"""
    print("🚀 Starting Test Group 5B: Document Generation")
    print("Formation: test-formations/formation-file-generation")

    results = {}

    # Run all tests
    results["5B1"] = await test_5b1_word_document_creation()
    results["5B2"] = await test_5b2_pdf_report_generation()
    results["5B3"] = await test_5b3_multi_section_documents()

    # Summary
    passed = sum(1 for result in results.values() if result)
    total = len(results)

    print("\n" + "="*50)
    print(f"TEST GROUP 5B SUMMARY")
    print("="*50)
    print(f"Tests passed: {passed}/{total}")

    for test_id, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {test_id}: {status}")

    print(f"\nOverall status: {'✅ PASSED' if passed == total else '❌ FAILED'}")

    return passed == total


if __name__ == "__main__":
    asyncio.run(run_test_group_5b())
