#!/usr/bin/env python3
"""Variant 1: Create file in existing directory"""

import asyncio
from pathlib import Path
import sys

sys.path.append(".")
from src.muxi import Formation  # noqa: E402


async def test():
    """Variant 1: File in existing directory"""
    try:
        print("\n=== Variant 1: File in Existing Directory ===")

        # Ensure directory EXISTS
        test_dir = Path("/Users/ran/Desktop/test_variant_1_existing")
        test_dir.mkdir(exist_ok=True)
        print(f"✓ Created directory: {test_dir}")

        formation = Formation()
        await formation.load("test-formations/formation-mcp")
        overlord = await formation.start_overlord()

        print("Requesting file creation in existing directory...")
        response_generator = await overlord.chat(
            "Create a file called 'success_existing.txt' with content 'Created in existing directory!' in /Users/ran/Desktop/test_variant_1_existing",  # noqa: E501
            user_id="user1",
            use_async=False
        )

        # Collect response
        full_response = ""
        async for chunk in response_generator:
            if hasattr(chunk, 'content') and chunk.content:
                full_response += chunk.content
            elif isinstance(chunk, str):
                full_response += chunk

        print(f"Response: {full_response}")

        # Check result
        file_path = test_dir / "success_existing.txt"
        if file_path.exists():
            print(f"\n✅ SUCCESS: {file_path}")
            print(f"Content: '{file_path.read_text()}'")
        else:
            print("\n❌ FAILED: File not created")

        # Don't wait for graceful shutdown - just terminate
        print("\nTerminating...")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test())
