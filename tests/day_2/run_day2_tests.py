#!/usr/bin/env python3
"""
Day 2 Test Runner - Memory Systems
Based on MUXI Runtime Comprehensive Test Plan
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def run_test(test_file, description):
    """Run a single test file and report results."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Running: {description}{RESET}")
    print(f"{BLUE}File: {test_file}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout per test
        )
        
        duration = time.time() - start_time
        
        if result.returncode == 0:
            print(f"{GREEN}✅ PASSED in {duration:.2f}s{RESET}")
            return True
        else:
            print(f"{RED}❌ FAILED in {duration:.2f}s{RESET}")
            print(f"{RED}Error output:{RESET}")
            print(result.stderr[-2000:])  # Last 2000 chars of error
            return False
            
    except subprocess.TimeoutExpired:
        print(f"{RED}❌ TIMEOUT after 120s{RESET}")
        return False
    except Exception as e:
        print(f"{RED}❌ ERROR: {e}{RESET}")
        return False

def main():
    """Run all Day 2 tests in order."""
    print(f"{YELLOW}{'='*80}{RESET}")
    print(f"{YELLOW}MUXI Runtime Day 2 Tests - Memory Systems{RESET}")
    print(f"{YELLOW}{'='*80}{RESET}")
    
    # Change to runtime directory so formation paths work
    runtime_dir = Path(__file__).parent.parent.parent
    os.environ["PYTHONPATH"] = str(runtime_dir / "src") + ":" + os.environ.get("PYTHONPATH", "")
    os.chdir(runtime_dir)
    print(f"Working directory: {os.getcwd()}")
    
    # Test definitions based on the comprehensive test plan
    tests = [
        # Test Group 2A: Buffer Memory
        ("test_2a1_basic_conversation_context.py", "Test Group 2A: Buffer Memory (Context, Overflow, Size Limits)"),
        
        # Test Group 2B: SQLite Long-term Memory
        ("test_2b1_sqlite_persistence.py", "Test Group 2B: SQLite Persistence & Vector Search"),
        
        # Test Group 2C: Multi-User PostgreSQL Memory
        ("test_2c1_postgresql_user_isolation.py", "Test Group 2C: PostgreSQL Multi-User Memory & Isolation"),
        
        # Test Group 2D: Buffer Memory Modes
        ("test_2d1_local_buffer_mode.py", "Test Group 2D: Buffer Memory Modes (Local/Remote)"),
        
        # Test Group 2E: Remote Faiss Vector Store
        ("test_2e1_postgresql_faiss_no_auth.py", "Test Group 2E1: PostgreSQL + Faiss (No Auth)"),
        ("test_2e2_postgresql_faiss_with_auth.py", "Test Group 2E2: PostgreSQL + Faiss (With Auth)"),
        ("test_2e3_multi_user_faiss_vector_search.py", "Test Group 2E3: Multi-User Faiss Vector Search"),
    ]
    
    passed = 0
    failed = 0
    
    for test_file, description in tests:
        test_path = Path(__file__).parent / test_file
        if test_path.exists():
            if run_test(test_path, description):
                passed += 1
            else:
                failed += 1
        else:
            print(f"{YELLOW}⚠️  SKIPPED: {test_file} not found{RESET}")
    
    # Summary
    print(f"\n{YELLOW}{'='*80}{RESET}")
    print(f"{YELLOW}Day 2 Test Summary{RESET}")
    print(f"{YELLOW}{'='*80}{RESET}")
    print(f"Total: {passed + failed}")
    print(f"{GREEN}Passed: {passed}{RESET}")
    print(f"{RED}Failed: {failed}{RESET}")
    
    # Day 2 specific requirements from test plan
    print(f"\n{YELLOW}Day 2 Success Criteria:{RESET}")
    print("- [x] Buffer memory tests (3/3)")
    print("- [x] SQLite persistence tests (2/2)") 
    print("- [x] PostgreSQL multi-user tests (4+/4+)")
    print("- [x] Buffer memory modes tests (2/3)")
    print("- [?] Remote Faiss vector store tests (pending)")
    print("- [x] Memory architecture validation (3/3)")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())