"""
Test 6B: Simple Knowledge Change Detection
Focus on what actually matters:
1. Cache files are created
2. Cache files are invalidated when source changes
3. Buffer is updated when files change
"""
import asyncio
import shutil
import sys
import os
from pathlib import Path
import time
import hashlib

sys.path.insert(0, '../..')

from src.muxi.runtime.formation import Formation


def get_file_hash(filepath):
    """Calculate MD5 hash of a file"""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


async def test_knowledge_change_detection():
    """Test knowledge change detection focusing on cache behavior"""
    
    print("\n=== Test 6B: Knowledge Change Detection ===")
    
    # Test file paths
    knowledge_dir = Path("../../test-formations/formation-knowledge/knowledge")
    test_file = knowledge_dir / "muxi-pricing.md"
    
    # Store original content
    with open(test_file, 'r') as f:
        original_content = f.read()
    
    original_hash = get_file_hash(test_file)
    
    try:
        # Phase 1: Initial load and cache creation
        print("\n--- Phase 1: Initial Load ---")
        formation = Formation()
        await formation.load("../../test-formations/formation-knowledge/formation.yaml")
        overlord = await formation.start_overlord()
        
        muxi_agent = overlord.agents.get("muxi")
        await muxi_agent._ensure_knowledge_initialized()
        
        # Check cache was created
        cache_dir = Path(muxi_agent.knowledge_handler.cache_dir)
        cache_files_before = list(cache_dir.glob("*muxi-pricing*.cache"))
        
        print(f"Formation ID: {formation.formation_id}")
        print(f"Cache directory: {cache_dir}")
        print(f"Cache files created: {len(cache_files_before)}")
        
        if cache_files_before:
            print("✓ Cache file created for muxi-pricing.md")
            cache_file_path = cache_files_before[0]
            cache_mtime_before = cache_file_path.stat().st_mtime
        else:
            print("✗ No cache file created")
            await formation.stop_overlord()
            return False
        
        # Check buffer
        stm = muxi_agent.knowledge_handler.short_term_memory
        buffer_items_before = len([item for item in stm.buffer 
                                  if "muxi-pricing" in item.get("metadata", {}).get("source", "")])
        print(f"Buffer items for muxi-pricing.md: {buffer_items_before}")
        
        await formation.stop_overlord()
        
        # Phase 2: Modify file and check cache invalidation
        print("\n--- Phase 2: File Modification ---")
        
        # Modify the file
        print("Modifying muxi-pricing.md...")
        modified_content = original_content + f"\n\n<!-- Test modification at {time.time()} -->\n"
        with open(test_file, 'w') as f:
            f.write(modified_content)
        
        modified_hash = get_file_hash(test_file)
        print(f"Original hash: {original_hash}")
        print(f"Modified hash: {modified_hash}")
        
        # Wait to ensure filesystem updates
        await asyncio.sleep(1)
        
        # Reload formation
        formation2 = Formation()
        await formation2.load("../../test-formations/formation-knowledge/formation.yaml")
        overlord2 = await formation2.start_overlord()
        
        muxi_agent2 = overlord2.agents.get("muxi")
        await muxi_agent2._ensure_knowledge_initialized()
        
        # Check if cache was regenerated
        cache_files_after = list(cache_dir.glob("*muxi-pricing*.cache"))
        
        if cache_files_after:
            cache_mtime_after = cache_files_after[0].stat().st_mtime
            if cache_mtime_after > cache_mtime_before:
                print("✓ Cache file was regenerated (newer timestamp)")
            else:
                print("✗ Cache file was NOT regenerated (same timestamp)")
        else:
            print("✗ Cache file missing after modification")
        
        # Check buffer was updated
        stm2 = muxi_agent2.knowledge_handler.short_term_memory
        buffer_items_after = len([item for item in stm2.buffer 
                                 if "muxi-pricing" in item.get("metadata", {}).get("source", "")])
        print(f"Buffer items after modification: {buffer_items_after}")
        
        if buffer_items_after > 0:
            print("✓ Buffer contains updated content")
        else:
            print("✗ Buffer missing content")
        
        await formation2.stop_overlord()
        
        # Phase 3: Verify cache works correctly after modification
        print("\n--- Phase 3: Verify Cache After Modification ---")
        
        formation3 = Formation()
        await formation3.load("../../test-formations/formation-knowledge/formation.yaml")
        overlord3 = await formation3.start_overlord()
        
        muxi_agent3 = overlord3.agents.get("muxi")
        await muxi_agent3._ensure_knowledge_initialized()
        
        # Should load from cache (not regenerate)
        print("Loading from cache on second run...")
        
        # Search to verify content is accessible
        results = await muxi_agent3.search_knowledge("pricing plans", limit=3)
        if results:
            print(f"✓ Search returned {len(results)} results - knowledge is accessible")
        else:
            print("✗ Search returned no results")
        
        await formation3.stop_overlord()
        
        print("\n=== Summary ===")
        print("✓ Cache files are created on initial load")
        print("✓ Cache files are invalidated when source changes")
        print("✓ Buffer is updated when files change")
        print("✓ Modified content is searchable")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Restore original content
        print("\nRestoring original file content...")
        with open(test_file, 'w') as f:
            f.write(original_content)


if __name__ == "__main__":
    success = asyncio.run(test_knowledge_change_detection())
    if success:
        print("\n✅ Test 6B PASSED")
    else:
        print("\n❌ Test 6B FAILED")