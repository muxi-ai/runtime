"""
Test 3A3: Multi-Document Comparison Tests
Simplified version using synchronous responses for faster testing
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest
from muxi.formation.formation import Formation


async def test_document_comparison():
    """Test comparing multiple documents"""
    print("\n=== Test 3A3.1: Document Comparison ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read test documents from tests/assets/files
    doc1_path = Path(__file__).parent.parent.parent / "assets/files" / "report.pdf"
    doc2_path = Path(__file__).parent.parent.parent / "assets/files" / "document.docx"

    with open(doc1_path, "rb") as f:
        doc1_content = f.read()
    with open(doc2_path, "rb") as f:
        doc2_content = f.read()

    files = [
        {
            "filename": "report.pdf",
            "content": doc1_content,
            "content_type": "application/pdf",
            "size": len(doc1_content)
        },
        {
            "filename": "document.docx",
            "content": doc2_content,
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": len(doc2_content)
        }
    ]

    # Test comparison
    test_cases = [
        {
            "name": "Compare growth metrics",
            "message": "Compare the revenue and growth between these two reports",
            "expected": ["revenue", "growth", "compare", "increase"],
        },
        {
            "name": "Analyze achievements",
            "message": "What are the key differences in achievements between these reports?",
            "expected": ["achievement", "difference", "report"],
        },
        {
            "name": "Identify trends",
            "message": "Identify trends and patterns across these documents",
            "expected": ["trend", "pattern", "document"],
        }
    ]

    for test in test_cases:
        print(f"\n📊 Test: {test['name']}")
        print(f"   Message: {test['message']}")

        # Send request with sync forced
        response = await overlord.chat(
            user_id="test_user",
            message=test['message'],
            files=files,
            use_async=False,  # Force sync
            stream=False,  # Disable streaming
        )

        result = response.content if hasattr(response, 'content') else str(response)

        print(f"   Response length: {len(result)} chars")
        print(f"   Response preview: {result[:150]}...")

        # Verify response
        result_lower = result.lower()
        found_keywords = [kw for kw in test['expected'] if kw in result_lower]

        assert len(found_keywords) >= 2, \
            f"Expected at least 2 keywords from {test['expected']}, found: {found_keywords}"

        print(f"   ✅ Found keywords: {found_keywords}")

    # Cleanup
    await formation.stop_overlord()
    print("\n✅ All comparison tests passed!")


async def test_mixed_media_analysis():
    """Test analyzing mixed media types"""
    print("\n=== Test 3A3.2: Mixed Media Analysis ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read mixed media files from tests/assets/files
    csv_path = Path(__file__).parent.parent.parent / "assets/files" / "spreadsheet.csv"
    xlsx_path = Path(__file__).parent.parent.parent / "assets/files" / "spreadsheet.xlsx"
    pdf_path = Path(__file__).parent.parent.parent / "assets/files" / "small.pdf"

    with open(csv_path, "rb") as f:
        csv_content = f.read()
    with open(xlsx_path, "rb") as f:
        xlsx_content = f.read()
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()

    files = [
        {
            "filename": "spreadsheet.csv",
            "content": csv_content,
            "content_type": "text/csv",
            "size": len(csv_content)
        },
        {
            "filename": "spreadsheet.xlsx",
            "content": xlsx_content,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": len(xlsx_content)
        },
        {
            "filename": "small.pdf",
            "content": pdf_content,
            "content_type": "application/pdf",
            "size": len(pdf_content)
        }
    ]

    print(f"📁 Testing with {len(files)} mixed files")

    # Test comprehensive analysis
    response = await overlord.chat(
        user_id="test_user",
        message="Provide a comprehensive analysis of all the information in these files",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"\n📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify comprehensive response
    result_lower = result.lower()
    # Updated to match actual file content (MUXI platform docs and spreadsheet data)
    expected_terms = ["muxi", "platform", "data", "analysis", "spreadsheet", "document"]
    found_terms = [term for term in expected_terms if term in result_lower]

    assert len(found_terms) >= 3, \
        f"Expected at least 3 terms from {expected_terms}, found: {found_terms}"

    print(f"✅ Found expected terms: {found_terms}")

    # Cleanup
    await formation.stop_overlord()
    print("\n✅ Mixed media analysis test passed!")


async def test_large_document_set():
    """Test processing a larger set of documents"""
    print("\n=== Test 3A3.3: Large Document Set ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read multiple PDFs from tests/assets/files for large document set
    pdf_files = ["sample.pdf", "small.pdf", "report.pdf", "large.pdf"]
    doc_path = Path(__file__).parent.parent.parent / "assets/files" / "document.docx"

    files = []
    # Add PDFs
    for pdf_file in pdf_files:
        pdf_path = Path(__file__).parent.parent.parent / "assets/files" / pdf_file
        with open(pdf_path, "rb") as f:
            content = f.read()
        files.append({
            "filename": pdf_file,
            "content": content,
            "content_type": "application/pdf",
            "size": len(content)
        })

    # Add DOCX
    with open(doc_path, "rb") as f:
        docx_content = f.read()
    files.append({
        "filename": "document.docx",
        "content": docx_content,
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size": len(docx_content)
    })

    print(f"📁 Testing with {len(files)} documents")

    # Test synthesis across all documents
    response = await overlord.chat(
        user_id="test_user",
        message="Synthesize the key information from all these documents into a brief summary",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"\n📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify synthesis
    result_lower = result.lower()
    assert any(word in result_lower for word in ["document", "topic", "summary", "information"]), \
        "Should provide synthesis of documents"
    assert len(result) > 100, "Synthesis should be substantial"

    print("✅ Large document set processing successful!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3A3: Multi-Document Comparison (Sync Mode)")
    print("=" * 60)

    # Run tests sequentially
    asyncio.run(test_document_comparison())
    print("\n" + "="*60 + "\n")

    asyncio.run(test_mixed_media_analysis())
    print("\n" + "="*60 + "\n")

    asyncio.run(test_large_document_set())

    print("\n🎉 All Test 3A3 tests completed successfully!")
