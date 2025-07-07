#!/usr/bin/env python3
"""Variant 3: Create file with explicit directory creation instruction"""

import asyncio
from pathlib import Path
import sys
import shutil

sys.path.append(".")
from src.muxi.runtime import Formation  # noqa: E402


async def test():
    """Variant 3: File with explicit directory instruction"""
    try:
        print("\n=== Variant 3: Explicit Directory Creation Instruction ===")

        # Ensure directory does NOT exist
        # Ensure directory does NOT exist
        import tempfile
        test_dir = Path(tempfile.gettempdir()) / "test_variant_3_explicit"
        if test_dir.exists():
            shutil.rmtree(test_dir)
        print(f"✓ Ensured directory does NOT exist: {test_dir}")

        formation = Formation()
        await formation.load("test-formations/formation-mcp")
        overlord = await formation.start_overlord()

        print("Requesting file creation with EXPLICIT directory creation instruction...")
        response_generator = await overlord.chat(
            f"Create a file called 'explicit_instruction.txt' with content 'Following explicit instructions!' in {test_dir}. If the directory does not exist, please create it first.",  # noqa: E501
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
        file_path = test_dir / "explicit_instruction.txt"
        if file_path.exists():
            print(f"\n✅ SUCCESS: {file_path}")
            print(f"Content: '{file_path.read_text()}'")
            print("📋 Agent followed explicit instructions correctly!")
        else:
            print("\n❌ FAILED: File not created")
            if test_dir.exists():
                print("Directory exists but file missing")
            else:
                print(f"Directory was not created: {test_dir}")

        print("\nTerminating...")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test())
