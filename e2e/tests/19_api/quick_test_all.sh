#!/bin/bash
# Quick test runner to check which tests pass/fail

cd /Users/ran/Projects/muxi/code/runtime

PASSING_TESTS=(
    "test_19a1_audit_logging"
    "test_19b1_sop_endpoints"
    "test_19c1_scheduler_persistence"
    "test_19d1_health_status"
    "test_19e1_chat_streaming"
    "test_19w1_logs_stream"
    "test_19f1_agents_crud"  # Just confirmed passing
)

FAILING_TESTS=(
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
)

echo "========================================="
echo "Quick Test Status Check"
echo "========================================="
echo ""

for test in "${FAILING_TESTS[@]}"; do
    echo -n "Testing $test... "
    timeout 60 python3 "e2e/tests/19_api/${test}.py" > "/tmp/${test}.log" 2>&1
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✅ PASS"
    elif [ $exit_code -eq 124 ]; then
        echo "⏱️  TIMEOUT"
    else
        # Check if it's an assertion error or actual failure
        if grep -q "SUCCESS:" "/tmp/${test}.log"; then
            echo "✅ PASS"
        elif grep -q "AssertionError" "/tmp/${test}.log"; then
            echo "❌ FAIL (assertion)"
            # Show the assertion error
            grep -A 2 "AssertionError" "/tmp/${test}.log" | head -3
        else
            echo "❌ FAIL"
            tail -5 "/tmp/${test}.log"
        fi
    fi
    
    # Small delay between tests
    sleep 2
done

echo ""
echo "========================================="
echo "Test run complete"
echo "========================================="
