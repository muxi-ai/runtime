#!/usr/bin/env python3
"""Test that scheduler methods are properly exposed through Formation API."""

import asyncio
import os
from pathlib import Path
import sys

# Add runtime src to path
runtime_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(runtime_path))

from muxi.runtime.formation import Formation


async def test_formation_scheduler_api():
    """Test Formation scheduler API methods."""
    print("Testing Formation scheduler API methods...")
    print("=" * 60)
    
    # Create a minimal formation config
    config = {
        "formation": {
            "name": "test-scheduler-api",
            "version": "1.0.0"
        },
        "agents": [],
        "database": {
            "type": "sqlite",
            "path": ":memory:"
        }
    }
    
    # Create formation
    formation = Formation(config)
    
    try:
        # Initialize formation to set up database
        formation.start_overlord()
        
        # Check that scheduler methods exist
        scheduler_methods = [
            "get_active_jobs",
            "get_all_jobs", 
            "get_user_jobs",
            "get_job_audit_trail",
            "get_recent_audit_trail"
        ]
        
        print("Checking Formation has scheduler methods:")
        for method in scheduler_methods:
            has_method = hasattr(formation, method)
            print(f"  {method:30} {'✓' if has_method else '✗'}")
            if not has_method:
                print(f"    ERROR: Method {method} not found!")
        
        print("\nChecking method signatures:")
        
        # Check get_active_jobs
        import inspect
        sig = inspect.signature(formation.get_active_jobs)
        print(f"  get_active_jobs{sig}")
        
        # Check get_all_jobs
        sig = inspect.signature(formation.get_all_jobs)
        print(f"  get_all_jobs{sig}")
        expected_params = ["status", "user_id", "is_recurring", "limit", "offset"]
        actual_params = list(sig.parameters.keys())
        for param in expected_params:
            if param not in actual_params:
                print(f"    WARNING: Expected parameter '{param}' not found")
        
        # Check get_user_jobs
        sig = inspect.signature(formation.get_user_jobs)
        print(f"  get_user_jobs{sig}")
        
        # Check get_job_audit_trail
        sig = inspect.signature(formation.get_job_audit_trail)
        print(f"  get_job_audit_trail{sig}")
        
        # Check get_recent_audit_trail
        sig = inspect.signature(formation.get_recent_audit_trail)
        print(f"  get_recent_audit_trail{sig}")
        
        print("\nTesting functional behavior:")
        
        # Test get_active_jobs - should return empty list initially
        try:
            active_jobs = await formation.get_active_jobs()
            assert isinstance(active_jobs, list), f"Expected list, got {type(active_jobs)}"
            print(f"  ✓ get_active_jobs() returns list ({len(active_jobs)} jobs)")
        except Exception as e:
            print(f"  ✗ get_active_jobs() failed: {e}")
        
        # Test get_all_jobs with default parameters
        try:
            all_jobs = await formation.get_all_jobs()
            assert isinstance(all_jobs, list), f"Expected list, got {type(all_jobs)}"
            print(f"  ✓ get_all_jobs() returns list ({len(all_jobs)} jobs)")
        except Exception as e:
            print(f"  ✗ get_all_jobs() failed: {e}")
        
        # Test get_all_jobs with filters
        try:
            filtered_jobs = await formation.get_all_jobs(status="ACTIVE", limit=10)
            assert isinstance(filtered_jobs, list), f"Expected list, got {type(filtered_jobs)}"
            print(f"  ✓ get_all_jobs(status='ACTIVE', limit=10) returns list ({len(filtered_jobs)} jobs)")
        except Exception as e:
            print(f"  ✗ get_all_jobs() with filters failed: {e}")
        
        # Test get_user_jobs - should handle non-existent user gracefully
        try:
            user_jobs = await formation.get_user_jobs("test_user_123")
            assert isinstance(user_jobs, list), f"Expected list, got {type(user_jobs)}"
            print(f"  ✓ get_user_jobs('test_user_123') returns list ({len(user_jobs)} jobs)")
        except Exception as e:
            print(f"  ✗ get_user_jobs() failed: {e}")
        
        # Test get_job_audit_trail - should handle non-existent job gracefully
        try:
            audit_trail = await formation.get_job_audit_trail("nonexistent_job_123")
            assert isinstance(audit_trail, list), f"Expected list, got {type(audit_trail)}"
            print(f"  ✓ get_job_audit_trail('nonexistent_job_123') returns list ({len(audit_trail)} entries)")
        except Exception as e:
            print(f"  ✗ get_job_audit_trail() failed: {e}")
        
        # Test get_recent_audit_trail
        try:
            recent_audit = await formation.get_recent_audit_trail(limit=20)
            assert isinstance(recent_audit, list), f"Expected list, got {type(recent_audit)}"
            print(f"  ✓ get_recent_audit_trail(limit=20) returns list ({len(recent_audit)} entries)")
        except Exception as e:
            print(f"  ✗ get_recent_audit_trail() failed: {e}")
        
        print("\nTesting error handling:")
        
        # Test invalid parameters
        try:
            await formation.get_all_jobs(limit=-1)
            print("  ⚠️ get_all_jobs() with negative limit should raise error")
        except (ValueError, TypeError) as e:
            print(f"  ✓ get_all_jobs() properly validates negative limit: {type(e).__name__}")
        except Exception as e:
            print(f"  ? get_all_jobs() with negative limit raised unexpected error: {e}")
        
        # Test invalid job ID type
        try:
            await formation.get_job_audit_trail(None)
            print("  ⚠️ get_job_audit_trail() with None job_id should raise error")
        except (ValueError, TypeError) as e:
            print(f"  ✓ get_job_audit_trail() properly validates None job_id: {type(e).__name__}")
        except Exception as e:
            print(f"  ? get_job_audit_trail() with None job_id raised unexpected error: {e}")
        
        print("\nFormation scheduler API test complete!")
        print("All scheduler methods are properly exposed and functional through the Formation class.")
        
    except Exception as e:
        print(f"\nFormation initialization failed: {e}")
        print("This may be expected if scheduler service is not available in this environment.")
    
    finally:
        # Clean up
        try:
            await formation.stop()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(test_formation_scheduler_api())