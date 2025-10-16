#!/usr/bin/env python3
"""
Formation loading smoke test - verify formations initialize without errors.
Tests formation loading WITHOUT running chat to keep it fast.
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

TEST_FORMATIONS = [
    ("basic", "e2e/tests/1_foundation/formations/formation-base/formation.yaml"),
    ("memory", "e2e/tests/2_memory/formations/formation-local/formation.yaml"),
    ("observability", "e2e/tests/18_observability/formations/formation-basic/formation.yaml"),
]

async def test_formation_load(name, path):
    """Test that a formation can load and initialize"""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"Path: {path}")
    print(f"{'='*60}")
    
    try:
        # Check file exists
        formation_path = Path(path)
        if not formation_path.exists():
            print(f"⚠️  Formation file not found: {path}")
            return None
        
        from muxi.formation import Formation
        
        # Load formation
        print("Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        print("✅ Formation loaded")
        
        # Start overlord (this triggers all initialization)
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        print(f"✅ Overlord started (ID: {overlord.formation_id})")
        
        # Check agents loaded
        agent_count = len(overlord.agents) if hasattr(overlord, 'agents') else 0
        print(f"✅ Agents loaded: {agent_count}")
        
        # Cleanup
        print("Cleaning up...")
        await formation.stop_overlord()
        print("✅ Cleaned up")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all formation tests"""
    print("="*60)
    print("FORMATION LOADING SMOKE TEST")
    print("="*60)
    
    results = []
    
    for name, path in TEST_FORMATIONS:
        result = await test_formation_load(name, path)
        results.append((name, result))
        
        # Give some breathing room between tests
        if result:
            await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    
    passed = sum(1 for _, r in results if r is True)
    skipped = sum(1 for _, r in results if r is None)
    failed = sum(1 for _, r in results if r is False)
    
    for name, result in results:
        if result is True:
            print(f"✅ PASS: {name}")
        elif result is None:
            print(f"⚠️  SKIP: {name} (formation file not found)")
        else:
            print(f"❌ FAIL: {name}")
    
    print(f"\nPassed: {passed}, Skipped: {skipped}, Failed: {failed}")
    
    if failed == 0 and passed > 0:
        print("\n🎉 ALL FORMATIONS LOADED SUCCESSFULLY!")
        return 0
    elif failed > 0:
        print(f"\n❌ {failed} formation(s) failed to load")
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
