#!/usr/bin/env python3
"""Test init formatting with multiple formations."""

import asyncio
import sys
from src.muxi.formation.formation import Formation

# Test formations with different features
FORMATIONS = [
    ("Simple Foundation", "e2e/tests/1_foundation/formations/formation-base/formation.yaml"),
    ("Multi-Agent with MCP", "e2e/tests/7_orchestration/formations/formation-multi-agent-segregated/formation.yaml"),
    ("Scheduling", "e2e/tests/12_scheduling/formation-scheduling/formation.yaml"),
]

async def test_formation(name: str, path: str):
    """Test a single formation initialization."""
    print(f"\n{'='*70}")
    print(f"Testing: {name}")
    print(f"Path: {path}")
    print(f"{'='*70}\n")
    
    try:
        # Load and start formation
        formation = Formation()
        await formation.load(path)
        overlord = await formation.start_overlord()
        
        # Cleanup
        await formation.stop_overlord()
        
        print(f"\n✅ {name} - Success\n")
        return True
        
    except Exception as e:
        print(f"\n❌ {name} - Failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all formation tests."""
    print("\n" + "="*70)
    print("MUXI Init Formatting Test Suite")
    print("="*70)
    
    results = []
    for name, path in FORMATIONS:
        success = await test_formation(name, path)
        results.append((name, success))
        
        # Short delay between formations
        await asyncio.sleep(1)
    
    # Summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\nResults: {passed}/{total} formations initialized successfully")
    print("="*70 + "\n")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
