#!/usr/bin/env python
"""Simple PDF Generation Regression Test for Artifacts System

This test verifies that the artifact generation system is still working
after the area 8 (clarification) implementation changes.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation


async def run_test():
    """Run the PDF artifact regression test."""
    formation = None
    try:
        print("\n" + "="*60)
        print("ARTIFACTS REGRESSION TEST: Simple PDF Generation")
        print("="*60)

        # Load formation
        formation_path = Path(__file__).parent / "formations" / "formation-file-generation"
        formation = Formation()
        await formation.load(str(formation_path / "formation.yaml"))

        print("\n✅ Formation loaded successfully")
        print("   Starting overlord...")
        overlord = await formation.start_overlord()
        print("   Overlord started successfully")

        # Simple test: Create a PDF with a joke
        prompt = "Create a PDF file with a joke as the content"
        print(f"\n📝 Test Prompt: {prompt}")
        print("   Expected: System should generate a PDF file")
        print("   Expected: Response should contain artifacts")

        # Send request with timeout
        print("\n🔄 Processing request...")
        try:
            response = await asyncio.wait_for(
                overlord.chat(prompt, user_id="test_user", session_id="pdf_test", stream=False),
                timeout=120.0  # 30 seconds for file generation
            )
        except asyncio.TimeoutError:
            print("❌ Request timed out after 30 seconds")
            return False

        print("\n📊 Response received:")
        print("-" * 40)

        # Check response structure
        if response:
            print(f"   Response: {response}")
            # Check for artifacts in the response
            if hasattr(response, 'artifacts'):
                print(f"✅ Response has artifacts attribute")

                if response.artifacts and len(response.artifacts) > 0:
                    print(f"✅ Found {len(response.artifacts)} artifact(s) in response!")

                    # Display artifact details
                    pdf_found = False
                    for i, artifact in enumerate(response.artifacts, 1):
                        print(f"\n📁 Artifact {i}:")
                        print(f"   - Filename: {getattr(artifact, 'filename', 'N/A')}")
                        print(f"   - Type: {getattr(artifact, 'type', 'N/A')}")
                        print(f"   - Format: {getattr(artifact, 'format', 'N/A')}")

                        # Check if it's a PDF
                        if (hasattr(artifact, 'format') and artifact.format == 'pdf') or \
                           (hasattr(artifact, 'filename') and 'pdf' in str(artifact.filename).lower()):
                            pdf_found = True
                            print("   ✅ This is a PDF artifact!")

                        # Check for data URL
                        if hasattr(artifact, 'data_url') and artifact.data_url:
                            if artifact.data_url.startswith("data:"):
                                print(f"   ✅ Valid base64 data URL present")
                            else:
                                print(f"   ⚠️ Data URL present but unexpected format")

                    if pdf_found:
                        print("\n" + "="*60)
                        print("### Test Result:")
                        print("  🎉 SUCCESS: Artifacts system is working!")
                        print("  ✓ PDF artifact generated and included in response")
                        print("="*60)

                        # Show chat transcript
                        content = response.content if hasattr(response, 'content') else str(response)
                        print("\n### Chat transcript:")
                        print(f"User: {prompt}")
                        print(f"System: {content[:200]}...")
                        return True
                    else:
                        print("\n⚠️ Artifacts found but no PDF detected")
                        print("   Formats found:", [getattr(a, 'format', 'unknown') for a in response.artifacts])
                else:
                    print("\n❌ No artifacts in response.artifacts!")
                    print(f"   Value: {response.artifacts}")
            else:
                # Check if response is just a string
                content = str(response)
                print(f"⚠️ Response has no artifacts attribute (type: {type(response)})")
                print(f"   Content: {content[:200]}...")

                if "pdf" in content.lower() or "file" in content.lower():
                    print("\n⚠️ Response mentions file/PDF but no artifacts in structure")
                    print("   This indicates a regression in the artifacts system!")
        else:
            print("❌ No response received!")

        print("\n" + "="*60)
        print("### Test Result:")
        print("  ❌ FAILED: Artifacts system regression detected!")
        print("  ✗ No PDF artifact found in response.artifacts")
        print("="*60)
        return False

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean shutdown
        if formation:
            try:
                print("\nShutting down...")
                await formation.kill_overlord()
                formation.shutdown()
            except:
                pass


async def main():
    """Main entry point with overall timeout."""
    try:
        success = await asyncio.wait_for(run_test(), timeout=60.0)
        return success
    except asyncio.TimeoutError:
        print("\n❌ Overall test timeout (60 seconds)")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
