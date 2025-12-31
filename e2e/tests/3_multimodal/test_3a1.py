"""
Test 3A1: Multimodal Document Processing Tests
Simplified version using synchronous responses for faster testing
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_document_processing():
    """Test document processing with file analysis"""
    print("\n=== Test 3A1.1: Document Processing ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read test file from tests/assets/files
    test_file_path = Path(__file__).parent.parent.parent / "assets/files" / "sample.pdf"
    with open(test_file_path, "rb") as f:
        file_content = f.read()

    # Prepare files
    files = [
        {
            "filename": "sample.pdf",
            "content": file_content,
            "content_type": "application/pdf",
            "size": len(file_content),
        }
    ]

    # Test cases
    test_cases = [
        {
            "name": "Key features extraction",
            "message": "What are the key features mentioned in this document?",
            "expected_keywords": ["feature", "key", "document", "mention", "describe", "content"],
        },
        {
            "name": "Theme analysis",
            "message": "What are the main themes in this document? Provide a brief summary.",
            "expected_keywords": ["theme", "summary", "main", "topic", "content", "document"],
        },
        {
            "name": "Comprehensive analysis",
            "message": "Provide a comprehensive analysis of this document including themes, insights, and recommendations.",  # noqa: E501
            "expected_keywords": [
                "analysis",
                "insight",
                "recommendation",
                "theme",
                "document",
                "comprehensive",
            ],
        },
    ]

    for test in test_cases:
        print(f"\n📝 Test: {test['name']}")
        print(f"   Message: {test['message'][:60]}...")

        # Send request with sync forced
        response = await overlord.chat(
            user_id="test_user",
            message=test["message"],
            files=files,
            use_async=False,  # Force sync for immediate response
            stream=False,  # Disable streaming for direct response
        )

        # Extract response content
        if hasattr(response, "content"):
            result = response.content
        elif hasattr(response, "__aiter__"):  # Handle streaming response
            # Collect all chunks from async generator
            chunks = []
            async for chunk in response:
                if hasattr(chunk, "content"):
                    chunks.append(chunk.content)
                else:
                    chunks.append(str(chunk))
            result = "".join(chunks)
        else:
            result = str(response)

        print(f"   Response length: {len(result)} chars")
        print(f"   Response preview: {result[:150]}...")

        # Verify response contains expected keywords
        result_lower = result.lower()
        found_keywords = [kw for kw in test["expected_keywords"] if kw in result_lower]

        assert (
            len(found_keywords) >= 1
        ), f"Expected at least 1 keyword from {test['expected_keywords']}, found: {found_keywords} in response: {result[:200]}"  # noqa: E501

        print(f"   ✅ Found keywords: {found_keywords}")

    # Cleanup
    await formation.stop_overlord()
    print("\n✅ All document processing tests passed!")


async def test_multimodal_without_files():
    """Test multimodal agent without files"""
    print("\n=== Test 3A1.2: Multimodal Agent (No Files) ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Test various prompts
    test_cases = [
        {
            "message": "Hello, how are you?",
            "expected": ["hello", "hi", "greet", "help", "assist", "how"],
        },
        {
            "message": "Explain the concept of machine learning in simple terms.",
            "expected": ["machine", "learning", "data", "pattern"],
        },
        {
            "message": "What are the benefits of using AI in healthcare?",
            "expected": ["health", "benefit", "ai", "patient"],
        },
    ]

    for test in test_cases:
        print(f"\n📝 Testing: {test['message'][:50]}...")

        response = await overlord.chat(
            user_id="test_user",
            message=test["message"],
            use_async=False,  # Force sync
            stream=False,  # Disable streaming for direct response
        )

        result = response.content if hasattr(response, "content") else str(response)
        print(f"   Response length: {len(result)} chars")

        # Check for expected content
        result_lower = result.lower()
        found = [word for word in test["expected"] if word in result_lower]

        assert (
            len(found) > 0
        ), f"Expected some of {test['expected']}, found none in response: {result[:200]}"
        print(f"   ✅ Found expected words: {found}")

    # Cleanup
    await formation.stop_overlord()
    print("\n✅ All no-file tests passed!")


async def test_multiple_files():
    """Test processing multiple files"""
    print("\n=== Test 3A1.3: Multiple File Processing ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Create multiple test files
    files = [
        {
            "filename": "doc1.txt",
            "content": "This is the first document about AI and machine learning.",
            "content_type": "text/plain",
            "size": 57,
        },
        {
            "filename": "doc2.txt",
            "content": "This is the second document about healthcare and medicine.",
            "content_type": "text/plain",
            "size": 58,
        },
    ]

    print(f"📁 Testing with {len(files)} files")

    # Test combined analysis
    response = await overlord.chat(
        user_id="test_user",
        message="Compare and summarize the topics covered in these documents.",
        files=files,
        use_async=False,
        stream=False,  # Disable streaming for direct response
    )

    result = response.content if hasattr(response, "content") else str(response)
    print(f"\n📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify response mentions both documents
    result_lower = result.lower()
    assert (
        "first" in result_lower or "doc1" in result_lower or "document 1" in result_lower
    ), "Should mention first document"
    assert (
        "second" in result_lower or "doc2" in result_lower or "document 2" in result_lower
    ), "Should mention second document"
    assert any(
        word in result_lower for word in ["ai", "machine learning", "healthcare", "medicine"]
    ), "Should mention document topics"

    print("✅ Multiple file processing successful!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3A1: Multimodal Document Processing (Sync Mode)")
    print("=" * 60)

    # Run tests sequentially
    asyncio.run(test_document_processing())
    print("\n" + "=" * 60 + "\n")

    asyncio.run(test_multimodal_without_files())
    print("\n" + "=" * 60 + "\n")

    asyncio.run(test_multiple_files())

    print("\n🎉 All Test 3A1 tests completed successfully!")
