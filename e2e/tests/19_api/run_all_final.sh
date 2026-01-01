#!/bin/bash
echo "========================================"
echo "API Test Suite - Final Run (All 23)"
echo "========================================"

PASSED=0; FAILED=0; declare -a FAILED_TESTS

for test in test_19*.py; do
  name=$(basename "$test" .py)
  echo "[$((PASSED + FAILED + 1))/23] $name..."
  
  timeout 60 python3 "$test" > "/tmp/${name}_final.log" 2>&1
  if [ $? -eq 0 ] && grep -q "SUCCESS" "/tmp/${name}_final.log"; then
    echo "     ✅ PASSED"
    ((PASSED++))
  else
    echo "     ❌ FAILED"
    FAILED_TESTS+=("$name")
    ((FAILED++))
  fi
  sleep 1
done

echo ""
echo "========================================"
echo "RESULTS: $PASSED passed, $FAILED failed"
echo "Success Rate: $(( PASSED * 100 / 23 ))%"
echo "========================================"
if [ $FAILED -gt 0 ]; then
  echo "Failed: ${FAILED_TESTS[@]}"
fi
