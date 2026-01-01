"""
Test 3D1: Document + Image Cross-Analysis
Sync version using files from tests/assets/files
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_document_image_alignment():
    """Test aligning document content with visual data"""
    print("\n=== Test 3D1: Document + Image Cross-Analysis ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read document and chart from tests/assets/files
    doc_path = Path(__file__).parent.parent.parent / "assets/files" / "report.pdf"
    chart_path = Path(__file__).parent.parent.parent / "assets/files" / "chart.png"

    with open(doc_path, "rb") as f:
        doc_content = f.read()
    with open(chart_path, "rb") as f:
        chart_content = f.read()

    files = [
        {
            "filename": "report.pdf",
            "content": doc_content,
            "content_type": "application/pdf",
            "size": len(doc_content)
        },
        {
            "filename": "chart.png",
            "content": chart_content,
            "content_type": "image/png",
            "size": len(chart_content)
        }
    ]

    print(f"✓ Loaded {len(files)} files for cross-analysis")

    # Test cross-analysis
    print("\n📊 Testing document and image alignment...")
    response = await overlord.chat(
        user_id="test_user",
        message="Analyze how the data in the chart relates to the information in the report document",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify cross-analysis
    result_lower = result.lower()
    expected_keywords = ["chart", "report", "data", "document", "relate", "analysis"]
    found_keywords = [kw for kw in expected_keywords if kw in result_lower]

    assert len(found_keywords) >= 3, \
        f"Expected at least 3 keywords from {expected_keywords}, found: {found_keywords}"
    assert len(result) > 200, "Cross-analysis should be detailed"

    print(f"✅ Found keywords: {found_keywords}")
    print("✅ Document + image cross-analysis test passed!")

    # Cleanup
    await formation.stop_overlord()


async def test_slide_document_comparison():
    """Test comparing presentation slides with documents"""
    print("\n=== Test 3D1.2: Slide + Document Comparison ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read slide and document from tests/assets/files
    slide_path = Path(__file__).parent.parent.parent / "assets/files" / "slide.png"
    doc_path = Path(__file__).parent.parent.parent / "assets/files" / "document.docx"

    with open(slide_path, "rb") as f:
        slide_content = f.read()
    with open(doc_path, "rb") as f:
        doc_content = f.read()

    files = [
        {
            "filename": "slide.png",
            "content": slide_content,
            "content_type": "image/png",
            "size": len(slide_content)
        },
        {
            "filename": "document.docx",
            "content": doc_content,
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": len(doc_content)
        }
    ]

    # Test comparison
    print("\n📊 Testing slide and document comparison...")
    response = await overlord.chat(
        user_id="test_user",
        message="Compare the visual information in the slide with the content in the document",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify comparison
    result_lower = result.lower()
    expected_keywords = ["slide", "document", "visual", "compare", "content", "information"]
    found_keywords = [kw for kw in expected_keywords if kw in result_lower]

    assert len(found_keywords) >= 3, \
        f"Expected at least 3 keywords from {expected_keywords}, found: {found_keywords}"

    print(f"✅ Found keywords: {found_keywords}")
    print("✅ Slide + document comparison test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3D1: Document + Image Cross-Analysis (Sync Mode)")
    print("=" * 60)

    # Run tests sequentially
    asyncio.run(test_document_image_alignment())
    print("\n" + "="*60 + "\n")

    asyncio.run(test_slide_document_comparison())

    print("\n🎉 All Test 3D1 tests completed successfully!")
