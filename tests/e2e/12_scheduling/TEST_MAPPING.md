# MUXI Scheduler E2E Test Mapping

## Overview
This directory contains end-to-end tests for the MUXI Scheduler service, validating both one-time and recurring job functionality.

## Test Formation
- **Location**: `./formation-scheduling/formation.yaml`
- **Purpose**: Provides a scheduler-enabled formation for testing job creation and execution
- **Key Config**: `scheduler.enabled: true` with 1-minute check interval

## Test Files

### test_scheduler_jobs.py
**Purpose**: Tests core scheduler functionality including job creation, execution, and management

**Test Cases**:

1. **test_recurring_job_creation_and_execution**
   - Tests: Creating a recurring job via natural language
   - Coverage:
     - Natural language parsing ("every 5 minutes")
     - Cron expression generation
     - Job persistence in `scheduled_jobs` table
     - Job execution via overlord.chat()
     - Audit trail in `scheduled_jobs_audit`
   - Expected: Job created, executes on schedule, audit recorded

2. **test_onetime_job_creation_and_execution**
   - Tests: Creating and executing a one-time scheduled job
   - Coverage:
     - Natural language parsing ("in 30 seconds")
     - Datetime calculation for `scheduled_for`
     - One-time job execution
     - Automatic completion after execution
     - Status update to COMPLETED
   - Expected: Job executes once at scheduled time, marked complete

3. **test_job_pause_and_resume**
   - Tests: Pausing and resuming active jobs
   - Coverage:
     - Job pause functionality (`is_paused` flag)
     - Resume functionality
     - Skipping paused jobs during execution cycles
   - Expected: Paused jobs don't execute, resumed jobs continue

4. **test_job_deletion**
   - Tests: Deleting scheduled jobs
   - Coverage:
     - Job deletion from `scheduled_jobs` table
     - Preservation of audit records
     - Immediate effect on execution cycle
   - Expected: Deleted jobs stop executing, audit preserved

5. **test_auto_pause_on_failures**
   - Tests: Automatic pausing after consecutive failures
   - Coverage:
     - Failure counting mechanism
     - Auto-pause threshold (default: 3)
     - Error tracking in audit table
   - Expected: Job auto-pauses after 3 consecutive failures

6. **test_timezone_handling**
   - Tests: Timezone-aware scheduling
   - Coverage:
     - UTC storage in database
     - Timezone conversion for user input
     - Correct execution timing across timezones
   - Expected: Jobs execute at correct local times

## Database Tables Tested

### scheduled_jobs
- Primary active job storage
- Fields tested: `id`, `formation_id`, `user_id`, `name`, `is_recurring`, `cron_expression`, `scheduled_for`, `execution_prompt`, `is_paused`, `failure_count`

### scheduled_jobs_audit
- Historical execution records
- Fields tested: `job_id`, `executed_at`, `status`, `response`, `error_message`

## Key Validation Points

1. **Natural Language Processing**
   - Validates LLM-based parsing of scheduling expressions
   - Tests both relative ("in 5 minutes") and absolute ("at 3pm") times

2. **Map/Reduce Pattern**
   - Verifies the map/reduce implementation for finding due jobs
   - Tests efficiency with multiple concurrent jobs

3. **Session Isolation**
   - Confirms each job runs with unique session_id (`job_{job_id}`)
   - Validates memory context separation between jobs

4. **Formation Isolation**
   - Tests multi-tenant support via formation_id
   - Ensures jobs from different formations don't interfere

5. **Background Worker**
   - Validates the @multitasking.task worker execution
   - Tests check_interval_minutes configuration

## Running Tests

```bash
# Run all scheduler tests
bash .claude/scripts/test-and-log.sh tests/e2e/12_scheduling/test_scheduler_jobs.py

# Run specific test
bash .claude/scripts/test-and-log.sh tests/e2e/12_scheduling/test_scheduler_jobs.py::test_recurring_job_creation_and_execution
```

## Expected Logs

The test runner creates detailed logs in `tests/logs/` including:
- Job creation requests and responses
- Cron expression generation
- Execution cycle details
- Database operations
- Overlord chat interactions
- Error scenarios and recovery

## Success Criteria

All tests should:
1. Successfully create jobs via natural language
2. Execute jobs at the correct times
3. Properly handle job lifecycle (pause/resume/delete)
4. Generate complete audit trails
5. Handle failures gracefully
6. Maintain formation isolation