#!/bin/bash
# Run API tests in smaller batches for faster feedback

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================"
echo "API Test Suite - Batch Runner"
echo "========================================"
echo ""

# Function to run a test
run_test() {
    local test_file=$1
    local test_name=$(basename "$test_file" .py)
    
    echo "Testing $test_name..."
    
    # Run test with timeout
    if timeout 90 python3 "$test_file" > "/tmp/${test_name}.log" 2>&1; then
        # Check if test passed
        if grep -q "SUCCESS" "/tmp/${test_name}.log" 2>/dev/null; then
            echo "   ✅ PASSED"
            return 0
        else
            echo "   ❌ FAILED (check log)"
            return 1
        fi
    else
        echo "   ❌ TIMEOUT/ERROR"
        return 1
    fi
}

# Batch 1: Basic endpoints (5 tests)
echo "=== Batch 1: Basic Endpoints (5 tests) ==="
BATCH1_PASS=0
BATCH1_FAIL=0

for test in test_19a1_audit_logging test_19b1_sop_endpoints test_19c1_scheduler_persistence test_19d1_health_status test_19e1_chat_streaming; do
    if run_test "${test}.py"; then
        BATCH1_PASS=$((BATCH1_PASS + 1))
    else
        BATCH1_FAIL=$((BATCH1_FAIL + 1))
    fi
    # Clean up
    pkill -9 -f "$test" 2>/dev/null || true
    lsof -ti:8271 | xargs kill -9 2>/dev/null || true
    sleep 2
done

echo ""
echo "Batch 1 Results: $BATCH1_PASS passed, $BATCH1_FAIL failed"
echo ""

# Batch 2: CRUD endpoints (5 tests)
echo "=== Batch 2: CRUD Endpoints (5 tests) ==="
BATCH2_PASS=0
BATCH2_FAIL=0

for test in test_19f1_agents_crud test_19g1_memory_sessions test_19h1_users test_19i1_memory_crud test_19j1_buffer_memory_ops; do
    if run_test "${test}.py"; then
        BATCH2_PASS=$((BATCH2_PASS + 1))
    else
        BATCH2_FAIL=$((BATCH2_FAIL + 1))
    fi
    pkill -9 -f "$test" 2>/dev/null || true
    lsof -ti:8271 | xargs kill -9 2>/dev/null || true
    sleep 2
done

echo ""
echo "Batch 2 Results: $BATCH2_PASS passed, $BATCH2_FAIL failed"
echo ""

# Summary
TOTAL_PASS=$((BATCH1_PASS + BATCH2_PASS))
TOTAL_FAIL=$((BATCH1_FAIL + BATCH2_FAIL))
TOTAL=$((TOTAL_PASS + TOTAL_FAIL))

echo "========================================"
echo "SUMMARY (First 10 Tests)"
echo "========================================"
echo "Passed: $TOTAL_PASS / $TOTAL"
echo "Failed: $TOTAL_FAIL / $TOTAL"
echo "Success Rate: $(( TOTAL_PASS * 100 / TOTAL ))%"
echo ""

if [ $TOTAL_FAIL -gt 0 ]; then
    echo "⚠️  Some tests failed - check logs in /tmp/test_*.log"
    exit 1
else
    echo "✅ All tests in first 2 batches passed!"
    exit 0
fi
