#!/usr/bin/env python3
"""Test 3A1: Multimodal Document Processing Tests

This test validates:
1. Document processing with file analysis
2. Key features extraction from documents
3. Theme analysis and comprehensive document analysis
4. Multimodal agent without files
5. Multiple file processing
"""

import asyncio
import time
import os
from pathlib import Path

from .base_multimodal_test import BaseMultimodalTest


class TestMultimodal3A1(BaseMultimodalTest):
    """Test Document Processing functionality."""

    async def test_3a1(self):
        """Test multimodal document processing."""
        test_name = "3a1"
        self.print_test_header(test_name, "Multimodal Document Processing")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Setup formation
            await self.setup_multimodal_formation()
            print("  ✓ Multimodal formation loaded")

            # Test 1: Document processing with file analysis
            print("\n  1. Testing document processing with file analysis...")

            # Try to use the sample PDF from assets
            test_file_path = Path(__file__).parent.parent.parent / "assets/files" / "sample.pdf"

            if test_file_path.exists():
                with open(test_file_path, "rb") as f:
                    file_content = f.read()
            else:
                # Create a simple test document if sample doesn't exist
                file_content = b"This is a test PDF document content for multimodal processing tests."

            # Prepare file
            files = [{
                "filename": "sample.pdf",
                "content": file_content,
                "content_type": "application/pdf",
                "size": len(file_content),
            }]

            # Test cases for document analysis
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
                    "message": "Provide a comprehensive analysis of this document including themes, insights, and recommendations.",
                    "expected_keywords": ["analysis", "insight", "recommendation", "theme", "document", "comprehensive"],
                },
            ]

            for test_case in test_cases:
                print(f"\n    Testing: {test_case['name']}")

                response = await self.overlord.chat(
                    user_id="test_user",
                    message=test_case["message"],
                    files=files,
                    use_async=False,
                    stream=False,
                )

                transcript.append(("User", test_case["message"]))

                # Extract response content
                if hasattr(response, "content"):
                    result = response.content
                elif hasattr(response, "__aiter__"):
                    chunks = []
                    async for chunk in response:
                        if hasattr(chunk, "content"):
                            chunks.append(chunk.content)
                        else:
                            chunks.append(str(chunk))
                    result = "".join(chunks)
                else:
                    result = str(response)

                transcript.append(("System", result[:100] + "..." if len(result) > 100 else result))

                print(f"      Response length: {len(result)} chars")

                # Verify response contains expected keywords
                result_lower = result.lower()
                found_keywords = [kw for kw in test_case["expected_keywords"] if kw in result_lower]

                if len(found_keywords) >= 1:
                    print(f"      ✓ Found keywords: {found_keywords}")
                    checks_passed.append(f"{test_case['name']}: Found {len(found_keywords)} keywords")
                else:
                    print(f"      ✗ No keywords found from {test_case['expected_keywords']}")
                    all_passed = False

            # Test 2: Multimodal agent without files
            print("\n  2. Testing multimodal agent without files...")

            no_file_tests = [
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

            for test in no_file_tests:
                print(f"\n    Testing: {test['message'][:50]}...")

                response = await self.overlord.chat(
                    user_id="test_user",
                    message=test["message"],
                    use_async=False,
                    stream=False,
                )

                transcript.append(("User", test["message"]))

                result = response.content if hasattr(response, "content") else str(response)
                transcript.append(("System", result[:100] + "..." if len(result) > 100 else result))

                print(f"      Response length: {len(result)} chars")

                # Check for expected content
                result_lower = result.lower()
                found = [word for word in test["expected"] if word in result_lower]

                if len(found) > 0:
                    print(f"      ✓ Found expected words: {found}")
                    checks_passed.append(f"No-file test found {len(found)} expected terms")
                else:
                    print(f"      ✗ No expected words found from {test['expected']}")
                    all_passed = False

            # Test 3: Multiple file processing
            print("\n  3. Testing multiple file processing...")

            # Create multiple test files
            multi_files = [
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

            print(f"    Testing with {len(multi_files)} files")

            multi_response = await self.overlord.chat(
                user_id="test_user",
                message="Compare and summarize the topics covered in these documents.",
                files=multi_files,
                use_async=False,
                stream=False,
            )

            transcript.append(("User", "Compare and summarize the topics covered in these documents."))

            multi_result = multi_response.content if hasattr(multi_response, "content") else str(multi_response)
            transcript.append(("System", multi_result[:100] + "..." if len(multi_result) > 100 else multi_result))

            print(f"    Response length: {len(multi_result)} chars")

            # Verify response mentions both documents
            result_lower = multi_result.lower()
            first_doc = ("first" in result_lower or "doc1" in result_lower or "document 1" in result_lower)
            second_doc = ("second" in result_lower or "doc2" in result_lower or "document 2" in result_lower)
            topics = any(word in result_lower for word in ["ai", "machine learning", "healthcare", "medicine"])

            if first_doc and second_doc and topics:
                print("    ✓ Multiple file processing successful!")
                checks_passed.append("Multiple file processing successful")
            else:
                print(f"    ✗ Multiple file processing failed (first: {first_doc}, second: {second_doc}, topics: {topics})")
                all_passed = False

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("📄 AREA 3A1: DOCUMENT PROCESSING")
        print("=" * 60)

        # Run test cases
        result = await self.test_3a1()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = TestMultimodal3A1()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
