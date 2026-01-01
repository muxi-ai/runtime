#!/bin/bash
# Batch runner for all multimodal tests with result tracking

cd "$(dirname "$0")/../../.."

RESULTS_FILE="e2e/tests/3_multimodal/test_results.txt"
echo "Multimodal Test Results - $(date)" > "$RESULTS_FILE"
echo "========================================" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

PASSED=0
FAILED=0
TOTAL=0

for test in e2e/tests/3_multimodal/test_3*.py; do
    test_name=$(basename "$test")
    TOTAL=$((TOTAL + 1))
    
    echo -n "[$TOTAL/38] Running $test_name... "
    
    start_time=$(date +%s)
    
    if timeout 180 python "$test" > /tmp/test_output.log 2>&1; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        echo "✅ PASSED (${duration}s)"
        echo "✅ $test_name - PASSED (${duration}s)" >> "$RESULTS_FILE"
        PASSED=$((PASSED + 1))
    else
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        echo "❌ FAILED (${duration}s)"
        echo "❌ $test_name - FAILED (${duration}s)" >> "$RESULTS_FILE"
        tail -20 /tmp/test_output.log >> "$RESULTS_FILE"
        echo "" >> "$RESULTS_FILE"
        FAILED=$((FAILED + 1))
    fi
done

echo "" >> "$RESULTS_FILE"
echo "========================================" >> "$RESULTS_FILE"
echo "SUMMARY" >> "$RESULTS_FILE"
echo "========================================" >> "$RESULTS_FILE"
echo "Total: $TOTAL" >> "$RESULTS_FILE"
echo "Passed: $PASSED" >> "$RESULTS_FILE"
echo "Failed: $FAILED" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

echo ""
echo "========================================"
echo "FINAL SUMMARY"
echo "========================================"
echo "Total: $TOTAL"
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo ""
echo "Results saved to: $RESULTS_FILE"
