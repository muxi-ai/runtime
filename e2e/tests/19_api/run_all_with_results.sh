#!/bin/bash
# Run all 23 API tests and track results

echo "=========================================="
echo "API Test Suite - Full Run"
echo "Running all 23 tests..."
echo "=========================================="
echo ""

PASSED=0
FAILED=0
FAILED_TESTS=()

run_test() {
    local test=$1
    local num=$2
    local name=$(basename "$test" .py)
    
    echo "[$num/23] Running $name..."
    
    # Run with python3 directly (sys.exit handles cleanup)
    python3 "$test" > "/tmp/${name}_result.log" 2>&1
    local exit_code=$?
    
    # Check if passed
    if [ $exit_code -eq 0 ] && grep -q "SUCCESS" "/tmp/${name}_result.log" 2>/dev/null; then
        echo "       ✅ PASSED"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo "       ❌ FAILED (exit code: $exit_code)"
        FAILED=$((FAILED + 1))
        FAILED_TESTS+=("$name")
        return 1
    fi
}

# Run all tests
run_test "test_19a1_audit_logging.py" 1
run_test "test_19b1_sop_endpoints.py" 2
run_test "test_19c1_scheduler_persistence.py" 3
run_test "test_19d1_health_status.py" 4
run_test "test_19e1_chat_streaming.py" 5
run_test "test_19f1_agents_crud.py" 6
run_test "test_19g1_memory_sessions.py" 7
run_test "test_19h1_users.py" 8
run_test "test_19i1_memory_crud.py" 9
run_test "test_19j1_buffer_memory_ops.py" 10
run_test "test_19k1_jobs.py" 11
run_test "test_19l1_secrets.py" 12
run_test "test_19m1_admin_config.py" 13
run_test "test_19n1_mcp.py" 14
run_test "test_19o1_memory_admin.py" 15
run_test "test_19p1_scheduler_admin.py" 16
run_test "test_19q1_llm_settings.py" 17
run_test "test_19r1_a2a.py" 18
run_test "test_19s1_async_jobs.py" 19
run_test "test_19t1_logging.py" 20
run_test "test_19u1_triggers.py" 21
run_test "test_19v1_events_streaming.py" 22
run_test "test_19w1_logs_stream.py" 23

echo ""
echo "=========================================="
echo "FINAL RESULTS"
echo "=========================================="
echo "Passed: $PASSED / 23"
echo "Failed: $FAILED / 23"
echo "Success Rate: $(( PASSED * 100 / 23 ))%"
echo ""

if [ $FAILED -gt 0 ]; then
    echo "Failed tests:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
    echo ""
    echo "Logs in /tmp/*_result.log"
fi

exit 0  # Always exit 0 so we can see results
