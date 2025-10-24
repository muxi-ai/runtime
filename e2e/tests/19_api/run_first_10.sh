#!/bin/bash
# Run first 10 tests
set +e

echo "=========================================="
echo "Running First 10 API Tests"
echo "=========================================="

PASSED=0
FAILED=0

run_test() {
    local test=$1
    echo ""
    echo "Running $(basename $test)..."
    
    python3 "$test" > /tmp/$(basename $test).log 2>&1
    local exit_code=$?
    
    if [ $exit_code -eq 0 ] && grep -q "SUCCESS" /tmp/$(basename $test).log; then
        echo "  ✅ PASSED"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo "  ❌ FAILED (exit: $exit_code)"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

# Run tests
run_test "test_19a1_audit_logging.py"
run_test "test_19b1_sop_endpoints.py"
run_test "test_19c1_scheduler_persistence.py"
run_test "test_19d1_health_status.py"
run_test "test_19e1_chat_streaming.py"
run_test "test_19f1_agents_crud.py"
run_test "test_19g1_memory_sessions.py"
run_test "test_19h1_users.py"
run_test "test_19i1_memory_crud.py"
run_test "test_19j1_buffer_memory_ops.py"

echo ""
echo "=========================================="
echo "Results: $PASSED passed, $FAILED failed"
echo "=========================================="
