#!/bin/bash
# Validate all API tests and show progress

set -e

cd "$(dirname "$0")"

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║               🧪 API Test Suite Validation                          ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Array of all tests
TESTS=(
    "test_19a1_audit_logging.py"
    "test_19b1_sop_endpoints.py"
    "test_19c1_scheduler_persistence.py"
    "test_19d1_health_status.py"
    "test_19e1_chat_streaming.py"
    "test_19f1_agents_crud.py"
    "test_19g1_memory_sessions.py"
    "test_19h1_users.py"
    "test_19i1_memory_crud.py"
    "test_19j1_buffer_memory_ops.py"
    "test_19k1_jobs.py"
    "test_19l1_secrets.py"
    "test_19m1_admin_config.py"
    "test_19n1_mcp.py"
    "test_19o1_memory_admin.py"
    "test_19p1_scheduler_admin.py"
    "test_19q1_llm_settings.py"
    "test_19r1_a2a.py"
    "test_19s1_async_jobs.py"
    "test_19t1_logging.py"
    "test_19u1_triggers.py"
    "test_19v1_events_streaming.py"
    "test_19w1_logs_stream.py"
)

PASSED=0
FAILED=0
FAILED_TESTS=()

for test in "${TESTS[@]}"; do
    echo -n "Testing $test... "
    
    # Run test with timeout
    if timeout 60 python3 "$test" > /tmp/test_output.log 2>&1; then
        echo "✅ PASSED"
        ((PASSED++))
    else
        echo "❌ FAILED"
        ((FAILED++))
        FAILED_TESTS+=("$test")
    fi
    
    # Small delay to avoid port conflicts
    sleep 0.5
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 RESULTS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Passed:  $PASSED"
echo "  ❌ Failed:  $FAILED"
echo "  📦 Total:   23"
echo ""
PASS_RATE=$(echo "scale=1; $PASSED * 100 / 23" | bc)
echo "  🎯 Pass Rate: $PASS_RATE%"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "Failed tests:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
fi

echo ""

# Progress milestones
if (( $(echo "$PASS_RATE >= 78" | bc -l) )); then
    echo "🎉 Phase 1 Complete! (List-wrapping bugs fixed)"
fi

if (( $(echo "$PASS_RATE >= 91" | bc -l) )); then
    echo "🎉 Phase 2 Complete! (Critical bugs fixed)"
fi

if (( $(echo "$PASS_RATE >= 96" | bc -l) )); then
    echo "🎉 Phase 3 Complete! (Infrastructure setup)"
fi

if (( $(echo "$PASS_RATE >= 100" | bc -l) )); then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║                  🎊 100% PASS RATE ACHIEVED! 🎊                     ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
fi

# Exit with error if not all tests passed (for CI/CD)
if [ $FAILED -gt 0 ]; then
    exit 1
fi
