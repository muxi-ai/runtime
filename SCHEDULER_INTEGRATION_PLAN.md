# Safe Scheduler Integration Plan

## Overview
Integrate the scheduler service with the overlord's chat flow by extending the existing RequestAnalyzer to detect scheduling intent using LLM (not pattern matching), then route appropriately.

## Key Principles
- **NO PATTERN MATCHING** - Use LLM for all intent detection (multilingual support)
- **PRESERVE PERSONA** - All responses must go through agent/persona system
- **ZERO BREAKAGE** - All changes must be additive and backward compatible

## Implementation Steps

### 1. Extend RequestAnalysis datatype
**File:** `src/muxi/datatypes/workflow.py`

Add two optional fields to the RequestAnalysis class:
```python
is_scheduling_request: bool = Field(default=False, description="Whether this is a scheduling request")
schedule_details: Optional[Dict[str, Any]] = Field(default=None, description="Parsed schedule information")
```

**Safety:** These are additive changes with defaults, ensuring backward compatibility.

### 2. Update LLM Analysis Prompt
**File:** `src/muxi/formation/workflow/analyzer.py`

Modify `_create_analysis_prompt()` to include scheduling detection in the JSON output:
- Add `"is_scheduling_request"` to the expected JSON response
- Add `"schedule_details"` for any detected schedule pattern
- Update the prompt to detect scheduling intent:
  ```
  "is_scheduling_request": [true if user wants to schedule/remind something at specific time/interval],
  "schedule_details": [if scheduling request, extract the schedule like "daily at 10am", "every Monday", etc.]
  ```
- Keep all existing fields unchanged

### 3. Add Scheduler Routing in Overlord
**File:** `src/muxi/formation/overlord/overlord.py`

After line 6269 where `analyze_request()` is called, add:
```python
# Check if this is a scheduling request BEFORE workflow analysis
if analysis.is_scheduling_request and self.scheduler_service:
    return await self._handle_scheduling_request(
        message=message,
        analysis=analysis,
        user_id=user_id,
        session_id=session_id,
        request_id=request_id
    )
```

**Placement:** This goes AFTER RequestAnalyzer but BEFORE workflow complexity check to ensure:
- Simple scheduling requests don't trigger workflows
- Complex requests with scheduling still get proper routing

### 4. Implement Scheduler Handler Method
**File:** `src/muxi/formation/overlord/overlord.py`

Add new method `_handle_scheduling_request()`:
```python
async def _handle_scheduling_request(
    self,
    message: str,
    analysis: RequestAnalysis,
    user_id: str,
    session_id: Optional[str],
    request_id: Optional[str]
) -> MuxiResponse:
    """Handle scheduling requests through the scheduler service."""

    # Extract actual message from formatted context if needed
    actual_message = self._extract_actual_message(message)

    # Extract schedule from analysis or original message
    schedule = analysis.schedule_details.get("expression") if analysis.schedule_details else actual_message

    # Create a title from the request
    title = f"Scheduled: {actual_message[:50]}"

    # Create the job using scheduler service
    job_id = await self.scheduler_service.create_job(
        user_id=str(user_id),
        title=title,
        original_prompt=actual_message,
        schedule=schedule,  # Natural language schedule
        exclusions=[]
    )

    # Route response through an agent for persona-fication
    # Use the default agent or create a scheduling-specific response
    response_message = f"I've scheduled your request: '{actual_message}'. Job ID: {job_id}"

    # Process through agent for proper persona
    agent = self.agents.get(list(self.agents.keys())[0]) if self.agents else None
    if agent:
        return await agent.process(response_message, context={
            "job_id": job_id,
            "schedule": schedule,
            "is_scheduling_response": True
        })

    # Fallback if no agents available
    return MuxiResponse(
        role="assistant",
        content=response_message,
        metadata={"job_id": job_id, "handled_by": "scheduler_service"}
    )
```

### 5. Update Tests
**File:** `tests/e2e/12_scheduling/test_scheduler_jobs.py`

- Fix API signatures to use correct parameters
- Add integration test for chat-based scheduling
- Test both direct API and chat interface
- Ensure database cleanup after tests

## Key Safety Features

1. **All changes are additive** - No existing functionality is modified
2. **Backward compatible** - Optional fields with defaults
3. **Feature-gated** - Only activates if scheduler_service exists
4. **Uses existing infrastructure** - Responses go through agents for persona
5. **LLM-based detection** - Works in any language, no pattern matching
6. **Clear separation** - Scheduling vs workflow detection is explicit

## What Gets Protected

- ✅ Existing workflow analysis continues unchanged
- ✅ Agent selection logic untouched
- ✅ Clarification flow preserved
- ✅ All existing tests should still pass
- ✅ SOPs and complex workflows still work
- ✅ Multi-step requests like "remind me to do X, Y, and Z" still trigger workflows

## Testing Strategy

1. **Regression Testing**
   - Run all existing workflow tests
   - Verify agent selection still works
   - Check clarification flows

2. **Scheduling Tests**
   - Test: "Schedule a daily reminder at 10am" → Creates job
   - Test: "Remind me every Monday to submit reports" → Creates job
   - Test: "Rappelle-moi chaque jour à 10h" (French) → Creates job
   - Test: "每天上午10点提醒我" (Chinese) → Creates job

3. **Boundary Tests**
   - Test: "Remind me to do X, Y, and Z" → Triggers workflow (multiple tasks)
   - Test: "Schedule a complex project review" → May trigger workflow
   - Test: "What's on my schedule?" → Agent handles (not scheduler)

4. **Integration Tests**
   - Verify job creation in database
   - Check job execution at scheduled time
   - Ensure proper cleanup after tests

## Risk Mitigation

- **Rollback Plan:** All changes are feature-flagged by scheduler_service existence
- **Monitoring:** Add observability events for scheduling detection and routing
- **Gradual Rollout:** Can be tested with specific users/sessions first
- **Fallback:** If scheduler fails, request falls through to normal agent handling

## Future Enhancements

1. Add scheduling management commands (list, cancel, modify jobs)
2. Integrate with clarification system for ambiguous schedules
3. Support complex recurrence patterns and exclusions
4. Add timezone detection from user context