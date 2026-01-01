#!/bin/bash
# Run 3 tests sequentially with aggressive cleanup

echo "=========================================="
echo "Running 3 Sequential API Tests"
echo "=========================================="

run_test() {
    local test_file=$1
    local test_name=$(basename "$test_file" .py)
    
    echo ""
    echo "[$test_name] Starting..."
    
    # Run in subprocess with timeout
    ( timeout 60 python3 "$test_file" > "/tmp/${test_name}_run.log" 2>&1 ) &
    PID=$!
    
    wait $PID
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        if grep -q "SUCCESS" "/tmp/${test_name}_run.log" 2>/dev/null; then
            echo "[$test_name] ✅ PASSED"
            return 0
        else
            echo "[$test_name] ❌ FAILED (no success marker)"
            return 1
        fi
    elif [ $EXIT_CODE -eq 124 ]; then
        echo "[$test_name] ❌ TIMEOUT"
        return 1
    else
        echo "[$test_name] ❌ ERROR (code $EXIT_CODE)"
        return 1
    fi
}

cleanup() {
    echo "  Cleaning up..."
    pkill -9 -f "test_19" 2>/dev/null
    lsof -ti:8271 | xargs kill -9 2>/dev/null
    sleep 3
}

# Test 1
run_test "test_19d1_health_status.py"
cleanup

# Test 2  
run_test "test_19a1_audit_logging.py"
cleanup

# Test 3
run_test "test_19b1_sop_endpoints.py"
cleanup

echo ""
echo "=========================================="
echo "All 3 tests attempted"
echo "Check /tmp/test_*_run.log for details"
echo "=========================================="
