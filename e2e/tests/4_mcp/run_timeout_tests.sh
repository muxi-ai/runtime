#!/bin/bash
# Run just the timeout tests with extended timeout

cd /Users/ran/Projects/muxi/code/runtime

echo "=================================="
echo "Running Timeout Tests (6 min each)"
echo "=================================="
echo ""

PASSED=0
FAILED=0
TIMEOUT=0

TESTS=(
    "e2e/tests/4_mcp/test_4b2_file_system_coordination.py"
    "e2e/tests/4_mcp/test_4b3_mcp_failure_handling.py"
    "e2e/tests/4_mcp/test_4c2_update_linear_issue.py"
    "e2e/tests/4_mcp/test_4c3_list_linear_issues.py"
    "e2e/tests/4_mcp/test_4e1_verify_user_isolation.py"
    "e2e/tests/4_mcp/test_4e2_multiple_users_permissions.py"
)

for test in "${TESTS[@]}"; do
    test_name=$(basename "$test" .py)
    echo "----------------------------------------"
    echo "Running: $test_name"
    echo "Start time: $(date '+%H:%M:%S')"
    echo "----------------------------------------"
    
    start_time=$(date +%s)
    
    # Run with timeout of 360 seconds (6 minutes)
    timeout 360 python "$test" > /tmp/test_output_$.txt 2>&1
    exit_code=$?
    
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    if [ $exit_code -eq 0 ]; then
        echo "✅ PASSED: $test_name (${duration}s)"
        PASSED=$((PASSED + 1))
    elif [ $exit_code -eq 124 ]; then
        echo "⏱️  TIMEOUT: $test_name (360s)"
        TIMEOUT=$((TIMEOUT + 1))
    else
        echo "❌ FAILED: $test_name (exit code: $exit_code, ${duration}s)"
        echo "   Last 30 lines of output:"
        tail -30 /tmp/test_output_$$.txt | grep -v "^{" | sed 's/^/     /'
        FAILED=$((FAILED + 1))
    fi
    
    rm -f /tmp/test_output_$$.txt
    echo ""
done

echo "=================================="
echo "Timeout Tests Summary"
echo "=================================="
echo "✅ Passed:  $PASSED"
echo "❌ Failed:  $FAILED"
echo "⏱️  Timeout: $TIMEOUT"
echo "Total:     $((PASSED + FAILED + TIMEOUT))"
echo "=================================="

exit $((FAILED + TIMEOUT))
