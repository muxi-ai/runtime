#!/usr/bin/env python3
"""Variant 2: Create file in non-existing directory"""

import asyncio
from pathlib import Path
import sys
import shutil

sys.path.append(".")
from src.muxi.runtime import Formation  # noqa: E402


async def test():
    """Variant 2: File in non-existing directory"""
    try:
        print("\n=== Variant 2: File in NON-Existing Directory ===")
        
        # Ensure directory does NOT exist
        test_dir = Path("/Users/ran/Desktop/test_variant_2_missing")
        if test_dir.exists():
            shutil.rmtree(test_dir)
        print(f"✓ Ensured directory does NOT exist: {test_dir}")
        
        formation = Formation()
        await formation.load("test-formations/formation-mcp")
        overlord = await formation.start_overlord()
        
        print("Requesting file creation in NON-existing directory...")
        response_generator = await overlord.chat(
            "Create a file called 'auto_created.txt' with content 'Agent created missing directory!' in /Users/ran/Desktop/test_variant_2_missing",
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
        file_path = test_dir / "auto_created.txt"
        if file_path.exists():
            print(f"\n✅ SUCCESS: {file_path}")
            print(f"Content: '{file_path.read_text()}'")
            print("🎉 Tool chaining worked - agent created the missing directory!")
        else:
            print(f"\n❌ FAILED: File not created")
            if test_dir.exists():
                print(f"Directory exists but file missing")
            else:
                print(f"Directory was not created: {test_dir}")
        
        print("\nTerminating...")
        
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test())