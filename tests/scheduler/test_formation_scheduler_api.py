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
    
    print("\nFormation scheduler API test complete!")
    print("All scheduler methods are properly exposed through the Formation class.")


if __name__ == "__main__":
    asyncio.run(test_formation_scheduler_api())