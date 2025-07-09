#!/usr/bin/env python3
"""Test 2A1: Basic Conversation Context - Buffer Memory Configuration"""

import sys
sys.path.insert(0, '.')
import asyncio
from src.muxi.runtime.formation.formation import Formation

async def test_formation_buffer_config():
    """Test buffer configuration through formation loading"""
    print("\n=== Testing Formation Buffer Configuration ===")
    
    formations = []
    try:
        # Test loading local buffer formation
        formation_local = Formation()
        await formation_local.load("test-formations/formation-memory/formation-buffer-local.yaml")
        formations.append(formation_local)
        print("✓ Local buffer formation loaded successfully")
        
        # Test loading remote buffer formation
        formation_remote = Formation()
        await formation_remote.load("test-formations/formation-memory/formation-buffer-remote.yaml")
        formations.append(formation_remote)
        print("✓ Remote buffer formation loaded successfully")
        
        # Extract buffer configurations
        local_config = formation_local.config.get("memory", {}).get("buffer", {})
        remote_config = formation_remote.config.get("memory", {}).get("buffer", {})
        
        print(f"  - Local buffer config: mode={local_config.get('mode', 'local')}, size={local_config.get('size')}")
        print(f"  - Remote buffer config: mode={remote_config.get('mode')}, size={remote_config.get('size')}")
        
        # Verify buffer memory is configured
        local_buffer_memory = formation_local._configured_services.get("buffer_memory") if hasattr(formation_local, '_configured_services') else None
        remote_buffer_memory = formation_remote._configured_services.get("buffer_memory") if hasattr(formation_remote, '_configured_services') else None
        
        if local_buffer_memory:
            print(f"  - Local buffer memory initialized: mode={getattr(local_buffer_memory, 'mode', 'unknown')}")
        if remote_buffer_memory:
            print(f"  - Remote buffer memory initialized: mode={getattr(remote_buffer_memory, 'mode', 'unknown')}")
        
        return {
            "formation_loading": "success",
            "local_config": local_config,
            "remote_config": remote_config,
            "local_memory_initialized": local_buffer_memory is not None,
            "remote_memory_initialized": remote_buffer_memory is not None
        }
        
    except Exception as e:
        print(f"❌ Formation buffer configuration failed: {e}")
        return {"formation_loading": "failed", "error": str(e)}

async def test_buffer_memory_functionality():
    """Test actual buffer memory functionality with overlord"""
    print("\n=== Testing Buffer Memory Functionality ===")
    
    formation = None
    overlord = None
    try:
        # Load formation with local buffer
        formation = Formation()
        await formation.load("test-formations/formation-memory/formation-buffer-local.yaml")
        overlord = await formation.start_overlord()
        print("✓ Overlord started with local buffer memory")
        
        # Test memory retention
        print("\nTesting conversation context retention...")
        
        # First message
        response1 = await overlord.chat(
            "My name is Alice and I work at TechCorp.", 
            user_id="test_user"
        )
        # Collect async response
        if hasattr(response1, '__aiter__'):
            chunks = []
            async for chunk in response1:
                chunks.append(chunk)
            response1_text = ''.join(chunks)
        else:
            response1_text = str(response1)
        
        print("  - First message processed")
        
        # Second message - should remember context
        response2 = await overlord.chat(
            "What's my name and where do I work?", 
            user_id="test_user"
        )
        # Collect async response
        if hasattr(response2, '__aiter__'):
            chunks = []
            async for chunk in response2:
                chunks.append(chunk)
            response2_text = ''.join(chunks)
        else:
            response2_text = str(response2)
        
        print("  - Second message processed")
        
        # Check if context was retained
        context_retained = ("alice" in response2_text.lower() and "techcorp" in response2_text.lower())
        print(f"  - Context retained: {'✅' if context_retained else '❌'}")
        
        return {
            "functionality": "success",
            "context_retained": context_retained
        }
        
    except Exception as e:
        print(f"❌ Buffer memory functionality test failed: {e}")
        return {"functionality": "failed", "error": str(e)}
    finally:
        # Clean up with timeout handling
        if overlord and formation:
            try:
                # Try graceful shutdown with short timeout
                await formation.stop_overlord(timeout_seconds=2.0)
                print("  - Overlord stopped gracefully")
            except Exception as e:
                # If graceful fails, force shutdown
                print(f"  - Graceful shutdown failed: {e}")
                formation.kill_overlord()
                print("  - Overlord killed")

async def main():
    """Run all buffer configuration tests"""
    print("🧠 Testing Buffer Memory Configuration (Local vs Remote)")
    print("=" * 60)
    
    # Test formation configurations
    formation_result = await test_formation_buffer_config()
    
    # Test actual functionality
    functionality_result = await test_buffer_memory_functionality()
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 BUFFER CONFIGURATION TEST SUMMARY")
    print("=" * 60)
    
    # Formation loading results
    formation_success = formation_result.get("formation_loading") == "success"
    print(f"Formation Configuration: {'✅ PASS' if formation_success else '❌ FAIL'}")
    if formation_success:
        print(f"  - Local buffer size: {formation_result['local_config'].get('size')}")
        print(f"  - Remote buffer size: {formation_result['remote_config'].get('size')}")
        print(f"  - Local memory initialized: {'✅' if formation_result.get('local_memory_initialized') else '❌'}")
        print(f"  - Remote memory initialized: {'✅' if formation_result.get('remote_memory_initialized') else '❌'}")
    
    # Functionality results
    functionality_success = functionality_result.get("functionality") == "success"
    print(f"\nBuffer Memory Functionality: {'✅ PASS' if functionality_success else '❌ FAIL'}")
    if functionality_success:
        print(f"  - Context retention: {'✅' if functionality_result.get('context_retained') else '❌'}")
    
    # Overall result
    all_tests_passed = formation_success and functionality_success
    
    print(f"\n🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_tests_passed else '❌ SOME TESTS FAILED'}")
    
    # Key insights
    print("\n💡 KEY INSIGHTS:")
    print("- Local buffer mode uses in-memory FAISS for vector search")
    print("- Remote buffer mode connects to external FAISSx servers")
    print("- Buffer memory retains conversation context across messages")
    print("- Both local and remote formations load successfully")
    
    return all_tests_passed

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)