# Test Mapping - Area 12: Scheduling

## Overview
Tests for scheduled task execution and job management functionality through the chat interface.

## Test Files

### Group 12A: One-time Scheduled Tasks

| Test ID | File | Description | Status |
|---------|------|-------------|--------|
| 12A1a | `test_12a1_basic_scheduling.py` | Basic scheduling detection for recurring and one-off schedules | ✅ Implemented |
| 12A1b | `test_12a1_schedule_future_task.py` | Schedule a task for future execution | ✅ Implemented |
| 12A2 | `test_12a2_natural_language_scheduling.py` | Natural language time parsing (e.g., "in 5 minutes") | ✅ Implemented |
| 12A3 | `test_12a3_schedule_with_context.py` | Schedule recurring tasks with context | ✅ Implemented |

### Group 12B: Recurring Jobs

| Test ID | File | Description | Status |
|---------|------|-------------|--------|
| 12B1 | `test_12b1_cron_based_scheduling.py` | Cron-based scheduling for recurring jobs | ✅ Implemented |

### Group 12D: Error Handling

| Test ID | File | Description | Status |
|---------|------|-------------|--------|
| 12D1 | `test_12d1_error_scenarios.py` | Invalid scheduling requests and error handling | ✅ Implemented |

### Removed Tests (API-exclusive)
- `test_12b2_update_recurring_job.py` - Required direct scheduler API access
- `test_12b3_cancel_job.py` - Required direct scheduler API access
- `test_12c1_job_execution_tracking.py` - Required direct scheduler API access
- `test_12c2_failed_job_handling.py` - Required direct scheduler API access

## Test Formation
- **Location**: `./formation-scheduling/formation.yaml`
- **Purpose**: Provides a scheduler-enabled formation for testing job creation
- **Key Config**: `scheduler.enabled: true` with 1-minute check interval

## Test Runner

- `run_all_tests.py` - Executes all chat-based scheduling tests sequentially

## Test Coverage

### ✅ Covered Scenarios
- Basic scheduling detection (recurring and one-off)
- Natural language time parsing ("in 5 minutes", "tomorrow at 3pm")
- Recurring schedules with cron patterns ("every Monday at 8am")
- Error handling for invalid requests
- Future task scheduling
- Context-aware scheduling

### ⚠️ Limitations (Chat Interface Only)
- Cannot directly update or cancel jobs
- Cannot track execution history
- Cannot verify actual job execution (would require waiting)
- Some natural language patterns may not be detected as scheduling requests

## Known Issues

1. **Scheduling Detection**: Not all phrasings are detected as scheduling requests
   - "Every Monday at 2pm team sync" - may not be recognized
   - Complex scheduling descriptions may require more specific phrasing

2. **Fixed Issues**:
   - ✅ JSON parsing issue where LLM returns markdown-wrapped JSON
   - ✅ Non-existent observability event types in scheduler modules
   - ✅ One-off job handling in scheduler service

## Running Tests

### Run All Tests
```bash
python tests/e2e/12_scheduling/run_all_tests.py
```

### Run Individual Tests
```bash
# Basic scheduling test
bash .claude/scripts/test-and-log.sh tests/e2e/12_scheduling/test_12a1_basic_scheduling.py

# Natural language scheduling
bash .claude/scripts/test-and-log.sh tests/e2e/12_scheduling/test_12a2_natural_language_scheduling.py

# Error scenarios
bash .claude/scripts/test-and-log.sh tests/e2e/12_scheduling/test_12d1_error_scenarios.py
```

## Implementation Architecture

### Integration Flow
1. User sends scheduling request via chat
2. `RequestAnalyzer` analyzes request and sets `is_scheduling_request` flag
3. Overlord routes to scheduler service if flag is true
4. `ScheduleParser` parses natural language into cron expression or datetime
5. `JobManager` creates job in database
6. Response sent back to user with job ID

### Key Components Modified
- `src/muxi/formation/workflow/analyzer.py` - Enhanced prompt for scheduling detection
- `src/muxi/formation/overlord/overlord.py` - Added scheduler routing after line 6395
- `src/muxi/services/scheduler/service.py` - Fixed one-off vs recurring job handling
- `src/muxi/services/scheduler/parser.py` - Fixed JSON parsing and observability events

## Database Tables

### scheduled_jobs
- Stores active scheduled jobs
- Fields: `id`, `user_id`, `title`, `original_prompt`, `execution_prompt`, `cron_expression`, `scheduled_for`, `is_recurring`, `status`

### scheduled_job_audit
- Audit trail for job lifecycle events
- Fields: `job_id`, `user_id`, `action`, `timestamp`, `changes`, `reason`

## Test Results Summary

Last Run: 2025-01-18

| Test | Result | Notes |
|------|--------|-------|
| 12A1a Basic Scheduling | ✅ 2/3 | One-off works, some recurring patterns not detected |
| 12A1b Future Task | ⚠️ | Schedules but cannot verify execution |
| 12A2 Natural Language | ⚠️ | Basic patterns work, complex ones may fail |
| 12A3 Context Scheduling | ❌ | Not all context patterns detected |
| 12B1 Cron Scheduling | ✅ | Weekly patterns work |
| 12D1 Error Scenarios | TBD | Not fully tested |

## Success Criteria

Tests should verify:
1. Natural language scheduling requests are detected
2. Jobs are created with correct parameters
3. Response confirms scheduling with job ID
4. Invalid requests are handled gracefully
5. Both recurring and one-off schedules work