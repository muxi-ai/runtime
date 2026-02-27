"""
Test 3A2: Image OCR and Visual Analysis Tests
Simplified version using synchronous responses for faster testing
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_image_ocr():
    """Test image OCR capabilities"""
    print("\n=== Test 3A2.1: Image OCR ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read test image from tests/assets/files
    test_image_path = Path(__file__).parent.parent.parent / "assets/files" / "slide.png"
    with open(test_image_path, "rb") as f:
        image_content = f.read()

    # Prepare files
    files = [
        {
            "filename": "slide.png",
            "content": image_content,
            "content_type": "image/png",
            "size": len(image_content),
        }
    ]

    # Test OCR
    test_cases = [
        {
            "name": "Extract text from image",
            "message": "Extract all text from this image",
            "expected": ["text", "extract", "read"],
        },
        {
            "name": "Analyze text structure",
            "message": "Analyze the structure and formatting of the text in this image",
            "expected": ["structure", "format", "text"],
        },
        {
            "name": "Summarize content",
            "message": "Summarize the content shown in this image",
            "expected": ["summary", "content", "image"],
        },
    ]

    for test in test_cases:
        print(f"\n🖼️ Test: {test['name']}")
        print(f"   Message: {test['message']}")

        # Send request with sync forced
        response = await overlord.chat(
            user_id="test_user",
            message=test["message"],
            files=files,
            use_async=False,  # Force sync for immediate response
            stream=False,  # Disable streaming for direct response
        )

        # Extract response content
        result = response.content if hasattr(response, "content") else str(response)

        print(f"   Response length: {len(result)} chars")
        print(f"   Response preview: {result[:150]}...")

        # Verify response
        result_lower = result.lower()
        found_keywords = [kw for kw in test["expected"] if kw in result_lower]

        assert (
            len(found_keywords) >= 1
        ), f"Expected at least 1 keyword from {test['expected']}, found: {found_keywords}"

        print(f"   ✅ Found keywords: {found_keywords}")

    # Cleanup
    await formation.stop_overlord()
    print("\n✅ All OCR tests passed!")


async def test_visual_analysis():
    """Test visual analysis capabilities"""
    print("\n=== Test 3A2.2: Visual Analysis ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read test image from tests/assets/files
    test_image_path = Path(__file__).parent.parent.parent / "assets/files" / "chart.png"
    with open(test_image_path, "rb") as f:
        image_content = f.read()

    # Prepare files
    files = [
        {
            "filename": "chart.png",
            "content": image_content,
            "content_type": "image/png",
            "size": len(image_content),
        }
    ]

    # Test visual analysis
    test_cases = [
        {
            "name": "Describe diagram",
            "message": "Describe what you see in this diagram",
            "expected": ["diagram", "visual", "see", "show"],
        },
        {
            "name": "Analyze relationships",
            "message": "Analyze the relationships and connections shown in this diagram",
            "expected": ["relationship", "connection", "diagram"],
        },
        {
            "name": "Extract key elements",
            "message": "What are the key elements and components in this visual?",
            "expected": ["element", "component", "key"],
        },
    ]

    for test in test_cases:
        print(f"\n📊 Test: {test['name']}")
        print(f"   Message: {test['message']}")

        # Send request with sync forced
        response = await overlord.chat(
            user_id="test_user",
            message=test["message"],
            files=files,
            use_async=False,  # Force sync
            stream=False,  # Disable streaming
        )

        result = response.content if hasattr(response, "content") else str(response)

        print(f"   Response length: {len(result)} chars")
        print(f"   Response preview: {result[:150]}...")

        # Verify response
        result_lower = result.lower()
        found_keywords = [kw for kw in test["expected"] if kw in result_lower]

        assert (
            len(found_keywords) >= 1
        ), f"Expected at least 1 keyword from {test['expected']}, found: {found_keywords}"

        print(f"   ✅ Found keywords: {found_keywords}")

    # Cleanup
    await formation.stop_overlord()
    print("\n✅ All visual analysis tests passed!")


async def test_multiple_images():
    """Test processing multiple images"""
    print("\n=== Test 3A2.3: Multiple Image Processing ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read multiple test images from tests/assets/files
    image1_path = Path(__file__).parent.parent.parent / "assets/files" / "chart.png"
    image2_path = Path(__file__).parent.parent.parent / "assets/files" / "photo.jpg"

    with open(image1_path, "rb") as f:
        image1_content = f.read()
    with open(image2_path, "rb") as f:
        image2_content = f.read()

    files = [
        {
            "filename": "chart.png",
            "content": image1_content,
            "content_type": "image/png",
            "size": len(image1_content),
        },
        {
            "filename": "photo.jpg",
            "content": image2_content,
            "content_type": "image/jpeg",
            "size": len(image2_content),
        },
    ]

    print(f"📁 Testing with {len(files)} images")

    # Test combined analysis
    response = await overlord.chat(
        user_id="test_user",
        message="Compare these images and describe any differences or similarities",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, "content") else str(response)
    print(f"\n📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify response mentions multiple images
    result_lower = result.lower()
    assert any(
        word in result_lower for word in ["first", "second", "both", "image", "comparison"]
    ), "Should discuss multiple images"

    print("✅ Multiple image processing successful!")

    # Cleanup
    await formation.stop_overlord()


async def run_all():
    """Run all multimodal tests with a single formation load."""
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    print("Formation loaded")

    assets_dir = Path(__file__).parent.parent.parent / "assets/files"

    # Test 1: OCR (1 call)
    print("\n=== Test 3A2.1: Image OCR ===")
    with open(assets_dir / "slide.png", "rb") as f:
        slide_data = f.read()
    files_ocr = [{"filename": "slide.png", "content": slide_data, "content_type": "image/png", "size": len(slide_data)}]
    r1 = await overlord.chat(user_id="test_user", message="Extract all text from this image", files=files_ocr, use_async=False, stream=False)
    t1 = r1.content if hasattr(r1, "content") else str(r1)
    assert len(t1) > 20, f"OCR response too short: {len(t1)}"
    print(f"  Response: {t1[:150]}...")
    print("  PASS")

    # Test 2: Visual analysis (1 call)
    print("\n=== Test 3A2.2: Visual Analysis ===")
    with open(assets_dir / "chart.png", "rb") as f:
        chart_data = f.read()
    files_chart = [{"filename": "chart.png", "content": chart_data, "content_type": "image/png", "size": len(chart_data)}]
    r2 = await overlord.chat(user_id="test_user", message="Describe what you see in this diagram", files=files_chart, use_async=False, stream=False)
    t2 = r2.content if hasattr(r2, "content") else str(r2)
    assert len(t2) > 20, f"Visual analysis response too short: {len(t2)}"
    print(f"  Response: {t2[:150]}...")
    print("  PASS")

    # Test 3: Multiple images (1 call)
    print("\n=== Test 3A2.3: Multiple Images ===")
    with open(assets_dir / "photo.jpg", "rb") as f:
        photo_data = f.read()
    files_multi = [
        {"filename": "chart.png", "content": chart_data, "content_type": "image/png", "size": len(chart_data)},
        {"filename": "photo.jpg", "content": photo_data, "content_type": "image/jpeg", "size": len(photo_data)},
    ]
    r3 = await overlord.chat(user_id="test_user", message="Compare these two images briefly", files=files_multi, use_async=False, stream=False)
    t3 = r3.content if hasattr(r3, "content") else str(r3)
    assert len(t3) > 20, f"Multi-image response too short: {len(t3)}"
    print(f"  Response: {t3[:150]}...")
    print("  PASS")

    await formation.stop_overlord()
    print("\nAll 3A2 tests passed")


if __name__ == "__main__":
    import os as _os

    print("Running Test 3A2: Image OCR and Visual Analysis")
    print("=" * 60)

    asyncio.run(run_all())

    print("SUCCESS", flush=True)
    _os._exit(0)
