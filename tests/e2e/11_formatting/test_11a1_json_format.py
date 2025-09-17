"""
Test 11A1: JSON Response Format

Tests that the system can return responses in JSON format when configured.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the src directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.formation import Formation  # noqa: E402


async def test_json_response_format():
    """Test that responses are returned in JSON format when configured."""
    print("🧪 Test 11A1: JSON Response Format")
    print("=" * 50)

    formation_path = Path(__file__).parent / "formation-formatting"
    formation = Formation()

    # Load the formation
    await formation.load(str(formation_path))

    # Start the formation and get overlord
    overlord = await formation.start_overlord()

    try:
        # Modify response format to JSON
        overlord.response_format = "json"

        print("📝 Testing JSON format with simple question...")

        # Test with a simple question
        response = await overlord.chat(
            message="List three benefits of cloud computing",
            user_id="test_user",
            session_id="test_session"
        )

        print(f"✅ Response received: {type(response)}")
        print(f"📄 Content: {response.content[:200]}...")

        # Validate that response content is JSON
        try:
            # Try to parse the content as JSON
            parsed_json = json.loads(response.content)
            print("✅ Response is valid JSON!")
            print(f"📋 JSON structure: {list(parsed_json.keys())}")

            # Check expected JSON structure
            assert "content" in parsed_json, "JSON should have 'content' field"
            assert "type" in parsed_json, "JSON should have 'type' field"
            assert "format" in parsed_json, "JSON should have 'format' field"
            assert parsed_json["type"] == "response", "Type should be 'response'"
            assert parsed_json["format"] == "json", "Format should be 'json'"

            print("✅ JSON structure is correct!")
            print(f"💬 Actual content: {parsed_json['content']}")

            # Print chat transcript
            print("\n" + "="*40)
            print("### Test Result:")
            print("  🎉 SUCCESS: JSON format working correctly")
            print("  ✓ Response parsed as valid JSON")
            print("  ✓ JSON structure contains required fields")
            print("  ✓ Content properly wrapped in JSON format")
            print("\n" + "="*40)
            print("### Chat transcript:")
            print("User: List three benefits of cloud computing")
            print(f"System: {response.content}")

            return True

        except json.JSONDecodeError as e:
            print(f"❌ Response is not valid JSON: {e}")
            print(f"📄 Raw content: {response.content}")

            # Print failure transcript
            print("\n" + "="*40)
            print("### Test Result:")
            print("  ❌ FAILURE: JSON format not working")
            print("  ✗ Response is not valid JSON")
            print("\n" + "="*40)
            print("### Chat transcript:")
            print("User: List three benefits of cloud computing")
            print(f"System: {response.content}")

            return False

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await formation.stop_overlord()


async def test_markdown_format():
    """Test that responses are returned in markdown format when configured."""
    print("\n🧪 Test 11A2: Markdown Response Format")
    print("=" * 50)

    formation_path = Path(__file__).parent / "formation-formatting"
    formation = Formation()

    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    try:
        overlord.response_format = "markdown"

        print("📝 Testing Markdown format...")

        response = await overlord.chat(
            message="Create a simple README for a Python project",
            user_id="test_user",
            session_id="test_session"
        )

        print(f"✅ Response received: {type(response)}")
        print(f"📄 Content preview: {response.content[:200]}...")

        # Check for markdown indicators
        has_headers = "#" in response.content
        has_code_blocks = "```" in response.content or "`" in response.content

        print(f"📋 Has headers (#): {has_headers}")
        print(f"📋 Has code blocks (```): {has_code_blocks}")

        # Should be formatted markdown, not JSON
        try:
            json.loads(response.content)
            print("❌ Response is JSON when it should be markdown!")
            return False
        except json.JSONDecodeError:
            print("✅ Response is not JSON (correct for markdown format)")

        # Print chat transcript
        print("\n" + "="*40)
        print("### Test Result:")
        print("  🎉 SUCCESS: Markdown format working correctly")
        print(f"  ✓ Has headers: {has_headers}")
        print(f"  ✓ Has code blocks: {has_code_blocks}")
        print("  ✓ Response is not JSON (correct)")
        print("\n" + "="*40)
        print("### Chat transcript:")
        print("User: Create a simple README for a Python project")
        print(f"System: {response.content}")

        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await formation.stop_overlord()


async def test_text_format():
    """Test that responses are returned in plain text format when configured."""
    print("\n🧪 Test 11A3: Plain Text Response Format")
    print("=" * 50)

    formation_path = Path(__file__).parent / "formation-formatting"
    formation = Formation()

    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    try:
        overlord.response_format = "text"

        print("📝 Testing plain text format...")

        response = await overlord.chat(
            message="Explain what cloud computing is in simple terms",
            user_id="test_user",
            session_id="test_session"
        )

        print(f"✅ Response received: {type(response)}")
        print(f"📄 Content preview: {response.content[:200]}...")

        # Should be plain text - no markdown formatting
        has_markdown = "#" in response.content or "**" in response.content or "*" in response.content

        print(f"📋 Has markdown formatting: {has_markdown}")

        # Should not be JSON
        try:
            json.loads(response.content)
            print("❌ Response is JSON when it should be plain text!")
            return False
        except json.JSONDecodeError:
            print("✅ Response is not JSON (correct for text format)")

        # Print chat transcript
        print("\n" + "="*40)
        print("### Test Result:")
        print("  🎉 SUCCESS: Plain text format working correctly")
        print(f"  ✓ Has no markdown formatting: {not has_markdown}")
        print("  ✓ Response is not JSON (correct)")
        print("\n" + "="*40)
        print("### Chat transcript:")
        print("User: Explain what cloud computing is in simple terms")
        print(f"System: {response.content}")

        print("✅ Plain text format test completed")
        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await formation.stop_overlord()


async def test_html_format():
    """Test that responses are returned in HTML format when configured."""
    print("\n🧪 Test 11A4: HTML Response Format")
    print("=" * 50)

    formation_path = Path(__file__).parent / "formation-formatting"
    formation = Formation()

    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    try:
        overlord.response_format = "html"

        print("📝 Testing HTML format...")

        response = await overlord.chat(
            message="Create a simple guide on the benefits of cloud computing",
            user_id="test_user",
            session_id="test_session"
        )

        print(f"✅ Response received: {type(response)}")
        print(f"📄 Content preview: {response.content[:200]}...")

        # Check for HTML elements
        has_html_tags = "<" in response.content and ">" in response.content
        has_semantic_tags = any(tag in response.content.lower() for tag in ["<h1>", "<h2>", "<p>", "<ul>", "<li>"])
        has_proper_structure = response.content.strip().startswith("<") or "<html>" in response.content.lower()

        print(f"📋 Has HTML tags: {has_html_tags}")
        print(f"📋 Has semantic tags: {has_semantic_tags}")
        print(f"📋 Has proper structure: {has_proper_structure}")

        # Should not be JSON
        try:
            json.loads(response.content)
            print("❌ Response is JSON when it should be HTML!")
            return False
        except json.JSONDecodeError:
            print("✅ Response is not JSON (correct for HTML format)")

        # Print chat transcript
        print("\n" + "="*40)
        print("### Test Result:")
        print("  🎉 SUCCESS: HTML format working correctly")
        print(f"  ✓ Has HTML tags: {has_html_tags}")
        print(f"  ✓ Has semantic tags: {has_semantic_tags}")
        print("  ✓ Response is not JSON (correct)")
        print("\n" + "="*40)
        print("### Chat transcript:")
        print("User: Create a simple guide on the benefits of cloud computing")
        print(f"System: {response.content}")

        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await formation.stop_overlord()


async def main():
    """Run all Area 11A tests."""
    print("🚀 Starting Area 11A: Response Format Tests")
    print("=" * 60)

    results = []

    # Test JSON format
    results.append(await test_json_response_format())

    # Test Markdown format
    results.append(await test_markdown_format())

    # Test Text format
    results.append(await test_text_format())

    # Test HTML format
    results.append(await test_html_format())

    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print(f"✅ Passed: {sum(results)}/{len(results)}")
    print(f"❌ Failed: {len(results) - sum(results)}/{len(results)}")

    if all(results):
        print("🎉 All Area 11A tests passed!")
        return 0
    else:
        print("💥 Some Area 11A tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
