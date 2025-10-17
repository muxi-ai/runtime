#!/bin/bash
# Run one test from each of 18 groups with 5-minute timeout each

tests=(
  "e2e/tests/1_foundation/test_1a_1_basic_yaml_formation.py"
  "e2e/tests/2_memory/test_2a1_basic_conversation_context.py"
  "e2e/tests/3_multimodal/test_3a1.py"
  "e2e/tests/4_mcp/test_4a2_system_info_mcp.py"
  "e2e/tests/5_artifacts/test_5_1.py"
  "e2e/tests/6_knowledge/test_6a1_chat_knowledge_loading.py"
  "e2e/tests/7_orchestration/test_7a1_task_decomposition.py"
  "e2e/tests/8_clarification/test_8_1.py"
  "e2e/tests/9_async/test_9a2_forced_sync_mode.py"
  "e2e/tests/10_streaming/test_10_a_1.py"
  "e2e/tests/11_formatting/test_11_a_1.py"
  "e2e/tests/12_scheduling/test_12a1_basic_scheduling.py"
  "e2e/tests/13_triggers/test_13a1_list_triggers.py"
  "e2e/tests/14_user_synopsis/test_14a1_synopsis_enabled.py"
  "e2e/tests/15_topic_tagging/test_15a1_topic_extraction.py"
  "e2e/tests/16_caching/test_16a1_cache_enabled.py"
  "e2e/tests/17_multiple_identities/test_17a1_sqlite.py"
  "e2e/tests/18_observability/test_init_formatting_success.py"
)

passed=0
failed=0
timeout=0
total=${#tests[@]}

echo "=========================================="
echo "Running 1 test from each of 18 groups"
echo "Timeout: 300s (5 min) per test"
echo "=========================================="
echo ""

for test in "${tests[@]}"; do
  group=$(echo "$test" | cut -d'/' -f3)
  testname=$(basename "$test" .py)
  
  echo "[$((passed+failed+timeout+1))/$total] $group/$testname"
  
  logfile="/tmp/e2e_${group}_${testname}.log"
  
  if timeout 300 python3 "$test" > "$logfile" 2>&1; then
    if grep -q "SUCCESS\|ALL TESTS PASSED\|🎉" "$logfile"; then
      echo "  ✅ PASSED"
      ((passed++))
    else
      echo "  ❓ UNCLEAR (no success marker)"
      tail -10 "$logfile" | sed 's/^/    /'
      ((failed++))
    fi
  else
    exit_code=$?
    if [ $exit_code -eq 124 ]; then
      echo "  ⏱️  TIMEOUT (>5min)"
      ((timeout++))
    else
      echo "  ❌ FAILED (exit code: $exit_code)"
      tail -20 "$logfile" | sed 's/^/    /'
      ((failed++))
    fi
  fi
  echo ""
done

echo "=========================================="
echo "FINAL RESULTS"
echo "=========================================="
echo "Passed:  $passed/$total"
echo "Failed:  $failed/$total"
echo "Timeout: $timeout/$total"
echo "=========================================="

if [ $failed -eq 0 ]; then
  echo "✅ No failures detected!"
  exit 0
else
  echo "❌ $failed test(s) failed"
  exit 1
fi
