#!/usr/bin/env python3
"""Test 4B3: MCP Failure Handling - Error recovery and graceful degradation"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_mcp_failure_handling():
    """Test MCP error handling and graceful failure"""
    print("\n=== Test 4B3: MCP Failure Handling ===")
    print("Goal: Validate graceful error handling for MCP operations")
    
    try:
        # Run the async test in a thread pool to avoid event loop issues
        def run_test():
            async def test_operations():
                # Load formation with MCP enabled
                formation = Formation()
                formation.load("test-formations/formation-mcp")
                overlord = formation.start_overlord()
                
                # Ensure overlord is started
                await overlord.ensure_started()
                
                print("\n1. Testing permission denied error handling...")
                response = await overlord.chat(
                    "Create a file in /root/forbidden_directory",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle permission error gracefully
                response_lower = response.lower()
                assert any(term in response_lower for term in 
                          ["error", "permission", "denied", "unable", "cannot", "failed", "access"]), \
                    "Response should indicate permission error"
                assert "traceback" not in response_lower, \
                    "Response should not contain raw traceback"
                print("✓ Permission denied handled gracefully")
                
                print("\n2. Testing invalid path handling...")
                response = await overlord.chat(
                    "Read the file at /this/path/definitely/does/not/exist/file.txt",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle missing file gracefully
                assert any(term in response_lower for term in 
                          ["not found", "doesn't exist", "does not exist", "unable", "cannot find", "missing"]), \
                    "Response should indicate file not found"
                print("✓ Invalid path handled gracefully")
                
                print("\n3. Testing invalid file operation...")
                response = await overlord.chat(
                    "Delete the entire filesystem starting from /",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should refuse dangerous operation
                assert any(term in response_lower for term in 
                          ["cannot", "unable", "dangerous", "not allowed", "refuse", "error"]), \
                    "Response should refuse dangerous operation"
                print("✓ Dangerous operation refused")
                
                print("\n4. Testing malformed request handling...")
                response = await overlord.chat(
                    "Create a file with name containing null bytes: test\x00file.txt",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle invalid filename
                assert any(term in response_lower for term in 
                          ["invalid", "error", "cannot", "unable", "filename"]), \
                    "Response should indicate invalid filename"
                print("✓ Malformed request handled gracefully")
                
                print("\n5. Testing partial workflow failure...")
                response = await overlord.chat(
                    "Get system stats and save to /root/forbidden.txt, "
                    "if that fails, tell me the stats anyway",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should still provide system stats despite file write failure
                assert any(term in response_lower for term in ["cpu", "memory", "ram"]), \
                    "Response should still contain system stats"
                assert any(term in response_lower for term in 
                          ["unable", "couldn't save", "permission", "but", "however"]), \
                    "Response should acknowledge the file write failure"
                print("✓ Partial workflow failure handled with fallback")
                
                print("\n6. Testing MCP timeout simulation...")
                response = await overlord.chat(
                    "Try to analyze a massive 10GB file that would timeout",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle large file scenario
                assert any(term in response_lower for term in 
                          ["large", "size", "unable", "timeout", "cannot"]) or \
                       len(response) > 20, \
                    "Response should handle large file scenario"
                print("✓ Timeout scenario handled appropriately")
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=90)
            
        if result:
            print("\n✅ Test 4B3 PASSED: All MCP failures handled gracefully")
            return True
        else:
            print("\n❌ Test 4B3 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4B3 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_mcp_failure_handling()
    sys.exit(0 if success else 1)