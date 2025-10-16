#!/usr/bin/env python3
"""
Quick smoke test for Phase 2 observability changes.
Tests that all our changes work without running full e2e tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test 1: All modules import successfully"""
    print("Test 1: Module imports...")
    
    try:
        from muxi.datatypes.observability import (
            SystemEvents, ConversationEvents, ErrorEvents,
            ServerEvents, APIEvents, EventLevel
        )
        from muxi.services.observability import observe
        from muxi.formation import Formation
        from muxi.formation.overlord import Overlord
        from muxi.formation.agents.agent import Agent
        from muxi.services.memory.working import WorkingMemory
        from muxi.services.memory.long_term import LongTermMemory
        
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_event_counts():
    """Test 2: Verify event counts match expectations"""
    print("\nTest 2: Event counts...")
    
    try:
        from muxi.datatypes.observability import SystemEvents, ConversationEvents, ErrorEvents
        
        system_count = len([e for e in SystemEvents])
        conversation_count = len([e for e in ConversationEvents])
        error_count = len([e for e in ErrorEvents])
        
        print(f"  SystemEvents: {system_count}")
        print(f"  ConversationEvents: {conversation_count}")
        print(f"  ErrorEvents: {error_count}")
        print(f"  Total: {system_count + conversation_count + error_count}")
        
        # Should have our expected counts
        assert system_count >= 119, f"Expected 119+ SystemEvents, got {system_count}"
        assert conversation_count >= 145, f"Expected 145+ ConversationEvents, got {conversation_count}"
        assert error_count >= 61, f"Expected 61+ ErrorEvents, got {error_count}"
        
        print("✅ Event counts correct")
        return True
    except Exception as e:
        print(f"❌ Event count test failed: {e}")
        return False

def test_new_events_exist():
    """Test 3: Verify our newly added events exist"""
    print("\nTest 3: New events from Phase 2...")
    
    try:
        from muxi.datatypes.observability import SystemEvents, ConversationEvents, ErrorEvents
        
        # Sample of events we added in Phase 2
        test_events = [
            ('SystemEvents', 'A2A_AGENT_REGISTRATIONS_COMPLETED'),
            ('SystemEvents', 'SCHEDULER_CACHE_CLEANUP'),
            ('SystemEvents', 'MCP_TRANSPORT_ATTEMPT'),
            ('SystemEvents', 'SYSTEM_ACTION'),
            ('SystemEvents', 'DATABASE_TYPE_FALLBACK'),
            ('ConversationEvents', 'PROMPT_FORMATION_ENHANCED'),
            ('ConversationEvents', 'CLARIFICATION_REQUEST_GENERATED'),
            ('ConversationEvents', 'CLARIFICATION_SKIPPED'),
            ('ConversationEvents', 'EXCLUSION_RULES_GENERATED'),
            ('ErrorEvents', 'AGENT_CREATION_FAILED'),
            ('ErrorEvents', 'GENERIC_ERROR'),
            ('ErrorEvents', 'PROCESSING_ERROR'),
        ]
        
        failed = []
        for enum_name, event_name in test_events:
            enum_class = {'SystemEvents': SystemEvents, 
                         'ConversationEvents': ConversationEvents,
                         'ErrorEvents': ErrorEvents}[enum_name]
            
            if hasattr(enum_class, event_name):
                print(f"  ✓ {enum_name}.{event_name}")
            else:
                print(f"  ✗ {enum_name}.{event_name} NOT FOUND")
                failed.append(f"{enum_name}.{event_name}")
        
        if failed:
            print(f"❌ Missing events: {failed}")
            return False
        
        print("✅ All new events present")
        return True
    except Exception as e:
        print(f"❌ New events test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enum_fixes():
    """Test 4: Verify enum category fixes"""
    print("\nTest 4: Enum category fixes...")
    
    try:
        from muxi.datatypes.observability import SystemEvents, ConversationEvents, ErrorEvents
        
        # Events we moved to correct categories
        checks = [
            (ConversationEvents, 'WORKFLOW_ANALYSIS_FAILED', 'ConversationEvents'),
            (ConversationEvents, 'WORKFLOW_DECOMPOSITION_FAILED', 'ConversationEvents'),
            (SystemEvents, 'CRON_TIMEZONE_CONVERTED', 'SystemEvents'),
            (SystemEvents, 'SYSTEM_ACTION', 'SystemEvents'),
            (ErrorEvents, 'OVERLORD_PROCESSING_ERROR', 'ErrorEvents'),
        ]
        
        for enum_class, event_name, expected_category in checks:
            if hasattr(enum_class, event_name):
                print(f"  ✓ {event_name} in {expected_category}")
            else:
                print(f"  ✗ {event_name} NOT in {expected_category}")
                return False
        
        print("✅ All enum fixes verified")
        return True
    except Exception as e:
        print(f"❌ Enum fixes test failed: {e}")
        return False

def test_observe_function():
    """Test 5: Test observe() function works"""
    print("\nTest 5: Observe function...")
    
    try:
        from muxi.services.observability import observe
        from muxi.datatypes.observability import SystemEvents, EventLevel
        
        # Try to call observe (it should work even if not in a request context)
        observe(
            event_type=SystemEvents.SYSTEM_ACTION,
            level=EventLevel.INFO,
            description="Smoke test verification",
            data={"test": "phase2_validation"}
        )
        
        print("✅ Observe function works")
        return True
    except Exception as e:
        print(f"❌ Observe function failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_fail_fast_modules():
    """Test 6: Modules with fail-fast conversions still import"""
    print("\nTest 6: Fail-fast conversion modules...")
    
    try:
        # These modules had events converted to fail-fast RuntimeError
        from muxi.formation.agents.agent import Agent
        from muxi.formation.overlord.overlord import Overlord
        from muxi.formation.overlord.a2a_coordinator import A2ACoordinator
        
        print("  ✓ Agent module")
        print("  ✓ Overlord module")
        print("  ✓ A2ACoordinator module")
        print("✅ All fail-fast modules import successfully")
        return True
    except Exception as e:
        print(f"❌ Fail-fast modules test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all smoke tests"""
    print("="*70)
    print("PHASE 2 OBSERVABILITY SMOKE TEST")
    print("="*70)
    
    tests = [
        test_imports,
        test_event_counts,
        test_new_events_exist,
        test_enum_fixes,
        test_observe_function,
        test_fail_fast_modules,
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            print(f"\n❌ Test {test_func.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_func.__name__, False))
    
    print("\n" + "="*70)
    print("SMOKE TEST RESULTS")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL SMOKE TESTS PASSED!")
        print("Phase 2 observability changes are working correctly.")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
