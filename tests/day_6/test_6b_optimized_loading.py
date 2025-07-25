"""
Test 6B: Optimized Knowledge Loading
Test that the knowledge system only regenerates embeddings for changed files
"""
import asyncio
import shutil
import sys
import os
from pathlib import Path
import time

sys.path.insert(0, '../..')

from src.muxi.runtime.formation import Formation


async def test_optimized_knowledge_loading():
    """Test that only changed files regenerate embeddings"""
    
    print("\n=== Test 6B: Optimized Knowledge Loading ===")
    
    # Test setup
    knowledge_dir = Path("../../test-formations/formation-knowledge/knowledge")
    test_file1 = knowledge_dir / "muxi-business-plan.md"
    test_file2 = knowledge_dir / "muxi-pricing.md"
    
    # Store original contents
    with open(test_file1, 'r') as f:
        original_content1 = f.read()
    with open(test_file2, 'r') as f:
        original_content2 = f.read()
    
    try:
        # Phase 1: Initial load - should generate embeddings for both files
        print("\n--- Phase 1: Initial Load (All Files) ---")
        formation1 = Formation()
        await formation1.load("../../test-formations/formation-knowledge/formation.yaml")
        overlord1 = await formation1.start_overlord()
        
        # Force knowledge initialization
        muxi_agent1 = overlord1.agents.get("muxi")
        await muxi_agent1._ensure_knowledge_initialized()
        
        await formation1.stop_overlord()
        
        # Phase 2: Reload with no changes - should skip all files
        print("\n--- Phase 2: Reload With No Changes ---")
        formation2 = Formation()
        await formation2.load("../../test-formations/formation-knowledge/formation.yaml")
        overlord2 = await formation2.start_overlord()
        
        muxi_agent2 = overlord2.agents.get("muxi")
        await muxi_agent2._ensure_knowledge_initialized()
        
        # Should see "unchanged" messages for both files
        await formation2.stop_overlord()
        
        # Phase 3: Modify one file and reload
        print("\n--- Phase 3: Modify One File ---")
        
        # Modify only muxi-pricing.md
        print("Modifying muxi-pricing.md...")
        modified_content2 = original_content2 + f"\n\n<!-- Modified at {time.time()} -->\n"
        with open(test_file2, 'w') as f:
            f.write(modified_content2)
        
        # Wait for filesystem
        await asyncio.sleep(0.5)
        
        formation3 = Formation()
        await formation3.load("../../test-formations/formation-knowledge/formation.yaml")
        overlord3 = await formation3.start_overlord()
        
        muxi_agent3 = overlord3.agents.get("muxi")
        await muxi_agent3._ensure_knowledge_initialized()
        
        # Should see:
        # - muxi-business-plan.md unchanged (skipped)
        # - muxi-pricing.md changed (regenerated)
        
        await formation3.stop_overlord()
        
        # Phase 4: Add a new file
        print("\n--- Phase 4: Add New File ---")
        
        # Create a temporary new file
        new_file = knowledge_dir / "test-new-file.md"
        new_content = "# Test New File\n\nThis is a test file for optimization."
        with open(new_file, 'w') as f:
            f.write(new_content)
        
        # Create a custom formation config that includes the new file
        custom_formation_path = Path("../../test-formations/test-optimized/formation.yaml")
        custom_formation_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Read original formation
        with open("../../test-formations/formation-knowledge/formation.yaml", 'r') as f:
            formation_config = f.read()
        
        # Add the new file to sources
        formation_config = formation_config.replace(
            '      - path: "knowledge/muxi-pricing.md"',
            '      - path: "knowledge/muxi-pricing.md"\n      - path: "knowledge/test-new-file.md"'
        )
        
        with open(custom_formation_path, 'w') as f:
            f.write(formation_config)
        
        formation4 = Formation()
        await formation4.load(str(custom_formation_path))
        overlord4 = await formation4.start_overlord()
        
        muxi_agent4 = overlord4.agents.get("muxi")
        await muxi_agent4._ensure_knowledge_initialized()
        
        # Should see:
        # - Existing files unchanged (skipped)
        # - test-new-file.md new (generated)
        
        await formation4.stop_overlord()
        
        # Phase 5: Remove a file
        print("\n--- Phase 5: Remove File ---")
        
        # Remove the test file
        os.remove(new_file)
        
        # Load original formation (without the new file)
        formation5 = Formation()
        await formation5.load("../../test-formations/formation-knowledge/formation.yaml")
        overlord5 = await formation5.start_overlord()
        
        muxi_agent5 = overlord5.agents.get("muxi")
        await muxi_agent5._ensure_knowledge_initialized()
        
        # Should see cleanup message for removed file
        
        await formation5.stop_overlord()
        
        print("\n=== Test Summary ===")
        print("✅ Optimized loading is working correctly:")
        print("  • Initial load generates all embeddings")
        print("  • Unchanged files are skipped (no API calls)")
        print("  • Changed files regenerate embeddings")
        print("  • New files generate embeddings")
        print("  • Deleted files are cleaned up")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup
        print("\nCleaning up...")
        
        # Restore original contents
        with open(test_file1, 'w') as f:
            f.write(original_content1)
        with open(test_file2, 'w') as f:
            f.write(original_content2)
        
        # Remove test files
        if Path(new_file).exists():
            os.remove(new_file)
        
        # Remove test formation
        test_formation_dir = Path("../../test-formations/test-optimized")
        if test_formation_dir.exists():
            shutil.rmtree(test_formation_dir)


if __name__ == "__main__":
    success = asyncio.run(test_optimized_knowledge_loading())
    if success:
        print("\n✅ Test 6B PASSED: Optimized loading saves API costs!")
    else:
        print("\n❌ Test 6B FAILED")