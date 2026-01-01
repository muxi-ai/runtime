#!/bin/bash
# Run all API tests sequentially with proper cleanup

cd /Users/ran/Projects/muxi/code/runtime

# Kill any stale processes on port 8271
echo "Cleaning up stale processes..."
lsof -ti :8271 | xargs kill -9 2>/dev/null || true
sleep 1

TESTS=(
    "test_19a1_audit_logging"
    "test_19b1_sop_endpoints"
    "test_19c1_scheduler_persistence"
    "test_19d1_health_status"
    "test_19e1_chat_streaming"
    "test_19f1_agents_crud"
    "test_19g1_memory_sessions"
    "test_19h1_users"
    "test_19i1_memory_crud"
    "test_19j1_buffer_memory_ops"
    "test_19k1_jobs"
    "test_19l1_secrets"
    "test_19m1_admin_config"
    "test_19n1_mcp"
    "test_19o1_memory_admin"
    "test_19p1_scheduler_admin"
    "test_19q1_llm_settings"
    "test_19r1_a2a"
    "test_19s1_async_jobs"
    "test_19t1_logging"
    "test_19u1_triggers"
    "test_19v1_events_streaming"
    "test_19w1_logs_stream"
)

PASSED=0
FAILED=0
TOTAL=${#TESTS[@]}

echo "========================================================================"
echo "RUNNING ALL API TESTS ($TOTAL tests)"
echo "========================================================================"
echo ""

for test in "${TESTS[@]}"; do
    echo "[$((PASSED + FAILED + 1))/$TOTAL] Running $test..."
    
    # Run test with timeout
    timeout 60 python3 "e2e/tests/19_api/${test}.py" > "/tmp/${test}.log" 2>&1
    exit_code=$?
    
    # Kill any lingering processes
    lsof -ti :8271 | xargs kill -9 2>/dev/null || true
    
    if [ $exit_code -eq 0 ] && grep -q "SUCCESS:" "/tmp/${test}.log"; then
        echo "✅ PASS"
        ((PASSED++))
    else
        echo "❌ FAIL"
        ((FAILED++))
        # Show error details
        if grep -q "AssertionError" "/tmp/${test}.log"; then
            echo "   Assertion error found. Last 10 lines:"
            tail -10 "/tmp/${test}.log" | sed 's/^/   /'
        elif grep -q "address already in use" "/tmp/${test}.log"; then
            echo "   Port conflict (should have been cleaned up)"
        elif [ $exit_code -eq 124 ]; then
            echo "   Test timed out after 60 seconds"
        else
            echo "   Exit code: $exit_code"
        fi
    fi
    
    # Small delay between tests
    sleep 2
    echo ""
done

echo "========================================================================"
echo "TEST SUMMARY"
echo "========================================================================"
echo "Passed: $PASSED/$TOTAL"
echo "Failed: $FAILED/$TOTAL"
echo ""

if [ $FAILED -gt 0 ]; then
    echo "Failed tests:"
    for test in "${TESTS[@]}"; do
        if [ -f "/tmp/${test}.log" ]; then
            if ! grep -q "SUCCESS:" "/tmp/${test}.log" 2>/dev/null; then
                echo "  - $test"
            fi
        fi
    done
    exit 1
else
    echo "🎉 All tests passed!"
    exit 0
fi
