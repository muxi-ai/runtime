#!/usr/bin/env python3
"""Test 3F1: Process actual PDF content and extract key information."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation


class ObservabilityCapture:
    """Capture observability events for display."""

    def __init__(self):
        self.events = []
        self._original_observe = None

    def __enter__(self):
        # Import and patch the observe function
        from src.muxi.runtime.services import observability

        self._original_observe = observability.observe

        def capture_observe(**kwargs):
            # Capture the event
            event_type = kwargs.get("event_type", "unknown")
            level = kwargs.get("level", "info")
            description = kwargs.get("description", "")
            data = kwargs.get("data", {})

            # Format the event for display
            event_str = f"[{level}] {event_type}"
            if description:
                event_str += f" - {description}"
            if data:
                event_str += f" | data: {data}"

            self.events.append(event_str)
            print(f"observability event: {event_str}")

            # Call original function
            return self._original_observe(**kwargs)

        observability.observe = capture_observe
        return self

    def __exit__(self, *args):
        # Restore original function
        from src.muxi.runtime.services import observability

        if self._original_observe:
            observability.observe = self._original_observe


def test_3f1_real_pdf_formula():
    """Test real PDF processing with formula extraction."""

    print("I am testing real PDF content extraction with formula analysis")
    print("This test validates that MUXI can process actual PDF files and extract")
    print("meaningful information, specifically about mathematical formulas.")
    print()

    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    formation.load(str(formation_path))
    overlord = formation.start_overlord()

    # Prepare the PDF file
    pdf_path = Path("test-docs/sample.pdf")
    if not pdf_path.exists():
        print(f"ERROR: PDF file not found at {pdf_path}")
        return

    # Create the prompt
    prompt = "explain the formula in this pdf"

    print(f"Prompt sent to overlord.chat:")
    print(f'"{prompt}"')
    print(f"Files: [{pdf_path.name} ({os.path.getsize(pdf_path)} bytes)]")
    print()

    # Capture observability events
    with ObservabilityCapture() as capture:
        try:
            # Read the PDF file
            with open(pdf_path, "rb") as f:
                pdf_content = f.read()

            # Send request with PDF attachment
            response = asyncio.run(
                overlord.chat(
                    user_id="test_user",
                    message=prompt,
                    files=[
                        {
                            "filename": pdf_path.name,
                            "content": pdf_content,
                            "content_type": "application/pdf",
                            "size": len(pdf_content),
                        }
                    ],
                    use_async=False,  # Use sync processing for immediate response
                )
            )

            # Handle async response - should get back a dict with request_id
            if isinstance(response, dict) and "request_id" in response:
                print()
                print("overlord.chat async response:")
                print(f"Request ID: {response.get('request_id')}")
                print(f"Status: {response.get('status')}")
                print(f"Message: {response.get('message')}")
                print(f"Processing Info: {response.get('processing_info', {})}")
                print()
                print("✅ Async request submitted successfully")
                print("⏳ Webhook will be sent upon completion to:", response.get('processing_info', {}).get('webhook_url', 'Not specified'))
            else:
                # Handle sync response (shouldn't happen with use_async=True)
                if hasattr(response, "__aiter__"):
                    async def collect():
                        chunks = []
                        async for chunk in response:
                            chunks.append(chunk)
                        return "".join(chunks)
                    response = asyncio.run(collect())

                print()
                print("overlord.chat response:")
                print(response)
                print()

                # Summary
                print("summary:")
                if response:
                    if isinstance(response, dict) and "error" in response:
                        print(f"❌ Test failed with error: {response['error']}")
                    else:
                        resp_text = str(response)
                        if "formula" in resp_text.lower() or "equation" in resp_text.lower():
                            print("✅ Successfully extracted and explained formula from PDF")
                            print(f"   Response length: {len(resp_text)} characters")

                            # Check for specific formula elements
                            formula_indicators = [
                                "=",
                                "x",
                                "y",
                                "+",
                                "-",
                                "*",
                                "/",
                                "^",
                                "sqrt",
                                "²",
                                "³",
                            ]
                            found_indicators = [ind for ind in formula_indicators if ind in resp_text]
                            if found_indicators:
                                print(f"   Found mathematical symbols: {', '.join(found_indicators)}")
                        else:
                            print("⚠️  Response received but no formula explanation detected")
                else:
                    print("❌ No response received")

        except Exception as e:
            print(f"❌ Exception occurred: {type(e).__name__}: {str(e)}")
            import traceback

            traceback.print_exc()
        finally:
            formation.stop_overlord()


if __name__ == "__main__":
    test_3f1_real_pdf_formula()
