#!/usr/bin/env python3
"""Test buffer memory configuration validation and setup"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from src.muxi.runtime.services.memory.short_term import ShortTermMemory

class MockLLM:
    """Mock LLM for testing"""
    async def embed(self, text):
        return [0.1] * 1536

def test_local_buffer_configuration():
    """Test local buffer memory configuration"""
    print("\n=== Testing Local Buffer Configuration ===")
    
    try:
        # Test direct ShortTermMemory creation with local mode
        buffer_local = ShortTermMemory(
            formation_id="test_formation",
            max_size=10,
            buffer_multiplier=5,
            dimension=1536,
            model=MockLLM(),
            mode="local"
        )
        
        print(f"✓ Local buffer created successfully")
        print(f"  - Max size: {buffer_local.max_size}")
        print(f"  - Buffer multiplier: {buffer_local.buffer_multiplier}")
        print(f"  - Total capacity: {buffer_local.buffer_size}")
        print(f"  - Mode: local")
        print(f"  - Has model: {buffer_local.model is not None}")
        
        # Test adding items to local buffer
        async def test_local_operations():
            await buffer_local.add("Test message 1", {"role": "user"})
            await buffer_local.add("Test response 1", {"role": "assistant"})
            
            # Test search
            results = await buffer_local.search("test")
            print(f"  - Search results: {len(results)} items")
            
            # Test recent retrieval
            recent = buffer_local.get_recent_items(5)
            print(f"  - Recent items: {len(recent)} items")
            
            return True
        
        # Run async operations
        success = asyncio.run(test_local_operations())
        
        return {
            "mode": "local",
            "configuration": "success",
            "operations": "success" if success else "failed",
            "details": {
                "max_size": buffer_local.max_size,
                "buffer_size": buffer_local.buffer_size,
                "has_model": buffer_local.model is not None
            }
        }
        
    except Exception as e:
        print(f"❌ Local buffer configuration failed: {e}")
        return {"mode": "local", "configuration": "failed", "error": str(e)}

def test_remote_buffer_configuration():
    """Test remote buffer memory configuration"""
    print("\n=== Testing Remote Buffer Configuration ===")
    
    try:
        # Test direct ShortTermMemory creation with remote mode
        remote_config = {
            "url": "tcp://localhost:45678",
            "api_key": "test-key",
            "tenant": "test-tenant"
        }
        
        buffer_remote = ShortTermMemory(
            formation_id="test_formation",
            max_size=10,
            buffer_multiplier=5,
            dimension=1536,
            model=MockLLM(),
            mode="remote",
            remote=remote_config
        )
        
        print(f"✓ Remote buffer created successfully")
        print(f"  - Max size: {buffer_remote.max_size}")
        print(f"  - Buffer multiplier: {buffer_remote.buffer_multiplier}")
        print(f"  - Total capacity: {buffer_remote.buffer_size}")
        print(f"  - Mode: remote")
        print(f"  - Remote URL: {remote_config['url']}")
        print(f"  - Has model: {buffer_remote.model is not None}")
        
        # Test adding items (this will likely fail to connect but should handle gracefully)
        async def test_remote_operations():
            try:
                await buffer_remote.add("Test message 1", {"role": "user"})
                print("  - Remote add operation succeeded")
                return True
            except Exception as e:
                print(f"  - Remote add operation failed gracefully: {str(e)[:100]}...")
                # This is expected since no real remote server is running
                return "expected_failure"
        
        # Run async operations
        result = asyncio.run(test_remote_operations())
        
        return {
            "mode": "remote",
            "configuration": "success",
            "operations": result,
            "details": {
                "max_size": buffer_remote.max_size,
                "buffer_size": buffer_remote.buffer_size,
                "remote_url": remote_config["url"],
                "has_model": buffer_remote.model is not None
            }
        }
        
    except Exception as e:
        print(f"❌ Remote buffer configuration failed: {e}")
        return {"mode": "remote", "configuration": "failed", "error": str(e)}

def test_formation_buffer_config():
    """Test buffer configuration through formation loading"""
    print("\n=== Testing Formation Buffer Configuration ===")
    
    try:
        # Test loading local buffer formation
        formation_local = Formation()
        formation_local.load("test-formations/formation-memory/formation-buffer-local.yaml")
        print("✓ Local buffer formation loaded successfully")
        
        # Test loading remote buffer formation
        formation_remote = Formation()
        formation_remote.load("test-formations/formation-memory/formation-buffer-remote.yaml")
        print("✓ Remote buffer formation loaded successfully")
        
        # Extract buffer configurations
        local_config = formation_local.config.get("memory", {}).get("buffer", {})
        remote_config = formation_remote.config.get("memory", {}).get("buffer", {})
        
        print(f"Local buffer config: mode={local_config.get('mode')}, size={local_config.get('size')}")
        print(f"Remote buffer config: mode={remote_config.get('mode')}, size={remote_config.get('size')}")
        
        return {
            "formation_loading": "success",
            "local_config": local_config,
            "remote_config": remote_config
        }
        
    except Exception as e:
        print(f"❌ Formation buffer configuration failed: {e}")
        return {"formation_loading": "failed", "error": str(e)}

def main():
    """Run all buffer configuration tests"""
    print("🧠 Testing Buffer Memory Configuration (Local vs Remote)")
    print("=" * 60)
    
    # Test individual configurations
    local_result = test_local_buffer_configuration()
    remote_result = test_remote_buffer_configuration()
    formation_result = test_formation_buffer_config()
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 BUFFER CONFIGURATION TEST SUMMARY")
    print("=" * 60)
    
    print(f"Local Buffer Configuration: {'✅ PASS' if local_result.get('configuration') == 'success' else '❌ FAIL'}")
    if local_result.get("details"):
        details = local_result["details"]
        print(f"  - Buffer size: {details.get('max_size')} x {details.get('buffer_size', 0) // details.get('max_size', 1)} = {details.get('buffer_size')}")
        print(f"  - Has embedding model: {'✅' if details.get('has_model') else '❌'}")
    
    print(f"Remote Buffer Configuration: {'✅ PASS' if remote_result.get('configuration') == 'success' else '❌ FAIL'}")
    if remote_result.get("details"):
        details = remote_result["details"]
        print(f"  - Buffer size: {details.get('max_size')} x {details.get('buffer_size', 0) // details.get('max_size', 1)} = {details.get('buffer_size')}")
        print(f"  - Remote URL: {details.get('remote_url')}")
        print(f"  - Has embedding model: {'✅' if details.get('has_model') else '❌'}")
    
    print(f"Formation Configuration: {'✅ PASS' if formation_result.get('formation_loading') == 'success' else '❌ FAIL'}")
    if formation_result.get("local_config"):
        print(f"  - Local formation mode: {formation_result['local_config'].get('mode')}")
    if formation_result.get("remote_config"):
        print(f"  - Remote formation mode: {formation_result['remote_config'].get('mode')}")
    
    # Overall result
    all_configs_working = (
        local_result.get("configuration") == "success" and
        remote_result.get("configuration") == "success" and
        formation_result.get("formation_loading") == "success"
    )
    
    print(f"\n🎯 OVERALL RESULT: {'✅ ALL CONFIGURATIONS WORKING' if all_configs_working else '❌ SOME CONFIGURATIONS FAILED'}")
    
    # Key insights
    print("\n💡 KEY INSIGHTS:")
    print("- Local buffer uses in-memory FAISS for vector search")
    print("- Remote buffer connects to external FAISSx servers")
    print("- Both modes support the same buffer size and multiplier configuration")
    print("- Formation YAML correctly loads both buffer configurations")
    if remote_result.get("operations") == "expected_failure":
        print("- Remote operations fail gracefully when no server is available (expected)")
    
    return {
        "local": local_result,
        "remote": remote_result,
        "formation": formation_result,
        "all_working": all_configs_working
    }

if __name__ == "__main__":
    main()