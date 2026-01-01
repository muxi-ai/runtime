#!/bin/bash
# Run tests one by one with cleanup and timeout

echo "=========================================="
echo "API Test Suite - Safe Sequential Run"
echo "=========================================="

PASSED=0
FAILED=0
RESULTS_FILE="/tmp/test_results.txt"
> "$RESULTS_FILE"  # Clear results file

run_test_safe() {
    local test=$1
    local num=$2
    local name=$(basename "$test" .py)
    
    echo ""
    echo "[$num/23] $name"
    
    # Kill any leftover processes
    pkill -9 -f "python.*test_19" 2>/dev/null
    pkill -9 -f "uvicorn" 2>/dev/null
    lsof -ti:8271 | xargs kill -9 2>/dev/null
    sleep 1
    
    # Run with 120s timeout
    timeout 120 python3 "$test" > "/tmp/${name}.log" 2>&1
    local exit_code=$?
    
    # Check result
    if [ $exit_code -eq 0 ] && grep -q "SUCCESS" "/tmp/${name}.log" 2>/dev/null; then
        echo "   ✅ PASSED"
        echo "$name: PASSED" >> "$RESULTS_FILE"
        PASSED=$((PASSED + 1))
    elif [ $exit_code -eq 124 ]; then
        echo "   ⏱️  TIMEOUT"
        echo "$name: TIMEOUT" >> "$RESULTS_FILE"
        FAILED=$((FAILED + 1))
    else
        echo "   ❌ FAILED (code $exit_code)"
        echo "$name: FAILED" >> "$RESULTS_FILE"
        FAILED=$((FAILED + 1))
    fi
    
    # Force cleanup
    pkill -9 -f "python.*$name" 2>/dev/null
    sleep 2
}

# Run all 23 tests
run_test_safe "test_19a1_audit_logging.py" 1
run_test_safe "test_19b1_sop_endpoints.py" 2
run_test_safe "test_19c1_scheduler_persistence.py" 3
run_test_safe "test_19d1_health_status.py" 4
run_test_safe "test_19e1_chat_streaming.py" 5
run_test_safe "test_19f1_agents_crud.py" 6
run_test_safe "test_19g1_memory_sessions.py" 7
run_test_safe "test_19h1_users.py" 8
run_test_safe "test_19i1_memory_crud.py" 9
run_test_safe "test_19j1_buffer_memory_ops.py" 10
run_test_safe "test_19k1_jobs.py" 11
run_test_safe "test_19l1_secrets.py" 12
run_test_safe "test_19m1_admin_config.py" 13
run_test_safe "test_19n1_mcp.py" 14
run_test_safe "test_19o1_memory_admin.py" 15
run_test_safe "test_19p1_scheduler_admin.py" 16
run_test_safe "test_19q1_llm_settings.py" 17
run_test_safe "test_19r1_a2a.py" 18
run_test_safe "test_19s1_async_jobs.py" 19
run_test_safe "test_19t1_logging.py" 20
run_test_safe "test_19u1_triggers.py" 21
run_test_safe "test_19v1_events_streaming.py" 22
run_test_safe "test_19w1_logs_stream.py" 23

echo ""
echo "=========================================="
echo "FINAL RESULTS"
echo "=========================================="
echo "Passed: $PASSED / 23"
echo "Failed: $FAILED / 23"
echo "Success Rate: $(( PASSED * 100 / 23 ))%"
echo ""
echo "Detailed results in $RESULTS_FILE"
cat "$RESULTS_FILE"
