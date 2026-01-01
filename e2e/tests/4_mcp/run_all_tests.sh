#!/bin/bash
# Run all 4_mcp tests and capture results

cd /Users/ran/Projects/muxi/code/runtime

echo "=================================="
echo "Running all 4_mcp tests"
echo "=================================="
echo ""

PASSED=0
FAILED=0
TIMEOUT=0

TESTS=(
    "e2e/tests/4_mcp/test_4a1_variant_1_existing_dir.py"
    "e2e/tests/4_mcp/test_4a2_system_info_mcp.py"
    "e2e/tests/4_mcp/test_4b1_complex_multi_mcp_workflow.py"
    "e2e/tests/4_mcp/test_4b2_file_system_coordination.py"
    "e2e/tests/4_mcp/test_4b3_mcp_failure_handling.py"
    "e2e/tests/4_mcp/test_4c1_create_linear_issue.py"
    "e2e/tests/4_mcp/test_4c2_update_linear_issue.py"
    "e2e/tests/4_mcp/test_4c3_list_linear_issues.py"
    "e2e/tests/4_mcp/test_4d1_user_credential_exists.py"
    "e2e/tests/4_mcp/test_4d2_user_credential_missing_full.py"
    "e2e/tests/4_mcp/test_4d2_user_credential_missing.py"
    "e2e/tests/4_mcp/test_4d2_user_help_request.py"
    "e2e/tests/4_mcp/test_4d3_clarification_with_cache_switch.py"
    "e2e/tests/4_mcp/test_4d3_clarification_with_cache.py"
    "e2e/tests/4_mcp/test_4d3_clarification.py"
    "e2e/tests/4_mcp/test_4d3_explicit.py"
    "e2e/tests/4_mcp/test_4d3_multiple_credentials.py"
    "e2e/tests/4_mcp/test_4d4_multiuser_isolation_simple.py"
    "e2e/tests/4_mcp/test_4e1_verify_user_isolation.py"
    "e2e/tests/4_mcp/test_4e2_multiple_users_permissions.py"
    "e2e/tests/4_mcp/test_mcp_env_auth_simple.py"
    "e2e/tests/4_mcp/test_mcp_env_auth_user_simple.py"
    "e2e/tests/4_mcp/test_mcp_env_auth_user.py"
    "e2e/tests/4_mcp/test_mcp_env_auth.py"
)

for test in "${TESTS[@]}"; do
    test_name=$(basename "$test" .py)
    echo "----------------------------------------"
    echo "Running: $test_name"
    echo "----------------------------------------"
    
    # Run with timeout of 360 seconds (6 minutes) for complex MCP operations
    timeout 360 python "$test" > /tmp/test_output_$.txt 2>&1
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✅ PASSED: $test_name"
        PASSED=$((PASSED + 1))
    elif [ $exit_code -eq 124 ]; then
        echo "⏱️  TIMEOUT: $test_name (360s)"
        TIMEOUT=$((TIMEOUT + 1))
    else
        echo "❌ FAILED: $test_name (exit code: $exit_code)"
        echo "   Error output:"
        tail -20 /tmp/test_output_$$.txt | grep -v "^{" | sed 's/^/     /'
        FAILED=$((FAILED + 1))
    fi
    
    rm -f /tmp/test_output_$$.txt
    echo ""
done

echo "=================================="
echo "Test Results Summary"
echo "=================================="
echo "✅ Passed:  $PASSED"
echo "❌ Failed:  $FAILED"
echo "⏱️  Timeout: $TIMEOUT"
echo "Total:     $((PASSED + FAILED + TIMEOUT))"
echo "=================================="

exit $FAILED
