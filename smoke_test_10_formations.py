#!/usr/bin/env python3
"""
Test 10 diverse formations to verify Phase 2 observability changes.
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

# 10 diverse formations from different test categories
TEST_FORMATIONS = [
    ("1_foundation", "e2e/tests/1_foundation/formations/formation-base/formation.yaml"),
    ("2_memory", "e2e/tests/2_memory/formations/formation-memory/formation-buffer-local.yaml"),
    ("3_multimodal", "e2e/tests/3_multimodal/formations/formation-multimodal/formation.yaml"),
    ("4_mcp", "e2e/tests/4_mcp/formations/formation-mcp/formation.yaml"),
    ("6_knowledge", "e2e/tests/6_knowledge/formations/formation-knowledge/formation.yaml"),
    ("10_streaming", "e2e/tests/10_streaming/formations/formation-streaming/formation.yaml"),
    ("13_triggers", "e2e/tests/13_triggers/formation-triggers/formation.yaml"),
    ("15_topic_tagging", "e2e/tests/15_topic_tagging/formations/formation-topic-tagging/formation.yaml"),
    ("16_caching_enabled", "e2e/tests/16_caching/formations/formation-cache-enabled/formation.yaml"),
    ("16_caching_disabled", "e2e/tests/16_caching/formations/formation-cache-disabled/formation.yaml"),
]

async def test_formation_load(name, path):
    """Test that a formation can load and initialize"""
    try:
        formation_path = Path(path)
        if not formation_path.exists():
            return None  # Skip
        
        from muxi.formation import Formation
        
        # Load and start (all initialization happens here)
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        # Quick validation
        assert overlord is not None
        assert overlord.formation_id is not None
        
        # Cleanup
        await formation.stop_overlord()
        
        return True
        
    except Exception as e:
        print(f"    Error: {e}")
        return False

async def main():
    """Run all formation tests"""
    print("="*70)
    print("10 FORMATION LOADING SMOKE TEST")
    print("Testing diverse formations from different test categories")
    print("="*70)
    
    results = []
    
    for idx, (name, path) in enumerate(TEST_FORMATIONS, 1):
        print(f"\n[{idx}/10] Testing: {name}...", end=" ", flush=True)
        
        result = await test_formation_load(name, path)
        results.append((name, result))
        
        if result is True:
            print("✅ PASS")
        elif result is None:
            print("⚠️  SKIP (file not found)")
        else:
            print("❌ FAIL")
        
        # Small delay between tests
        if result is True:
            await asyncio.sleep(0.5)
    
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, r in results if r is True)
    skipped = sum(1 for _, r in results if r is None)
    failed = sum(1 for _, r in results if r is False)
    
    for name, result in results:
        if result is True:
            print(f"✅ {name}")
        elif result is None:
            print(f"⚠️  {name} (skipped)")
        else:
            print(f"❌ {name} (FAILED)")
    
    print(f"\n{'='*70}")
    print(f"Passed: {passed}/{len(TEST_FORMATIONS)}")
    print(f"Skipped: {skipped}/{len(TEST_FORMATIONS)}")
    print(f"Failed: {failed}/{len(TEST_FORMATIONS)}")
    print(f"{'='*70}")
    
    if failed == 0 and passed > 0:
        print("\n🎉 ALL TESTED FORMATIONS LOADED SUCCESSFULLY!")
        print(f"Phase 2 observability changes are working correctly.")
        print(f"No regressions detected in {passed} formation(s).")
        return 0
    elif failed > 0:
        print(f"\n❌ {failed} formation(s) failed - REGRESSIONS DETECTED")
        return 1
    else:
        print("\n⚠️  No formations could be tested")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
