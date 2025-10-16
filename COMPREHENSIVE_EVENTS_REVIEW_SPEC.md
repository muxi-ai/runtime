# Comprehensive Events Audit Review Specification

## Review Objective
Manually review ALL 1,261 observability events in the CSV to identify:
1. **Misclassifications**: Wrong event type for the context
2. **Wrong Levels**: DEBUG/INFO/WARNING/ERROR incorrectly assigned
3. **Descriptions**: Unclear, incomplete, or misleading descriptions
4. **False Positives**: Events marked "OK" that actually have issues
5. **Context Accuracy**: Description matches the actual code behavior

## Review Criteria

### 1. Level Classification Accuracy
For each event, verify the level is appropriate:

- **DEBUG**: Development/diagnostic info, too granular for production monitoring
- **INFO**: Important operational events, normal flow milestones (loading, completion, init)
- **WARNING**: Degraded but functional state, missing optional configs, fallbacks triggered
- **ERROR**: Actual failures, exceptions, user-visible issues

**Red Flags**:
- ❌ ERROR events that actually succeed (e.g., "API key configured" as ERROR)
- ❌ INFO events for trivial details (e.g., "loading started")
- ❌ WARNING events that indicate success states
- ❌ DEBUG in production-critical paths

### 2. Event Type Appropriateness
- Does the event_type match the event's purpose?
- Is it the most specific type available? (e.g., APIEvents vs ConversationEvents)
- Should it be a different system event category?

**Examples of mistype**:
- Loading events as DEBUG when they should be INFO
- Success events classified as ERROR
- Operational events in wrong event family

### 3. Description Quality
Descriptions must be:
- ✅ **Complete**: Full sentence explaining what happened
- ✅ **Accurate**: Matches the code's actual behavior
- ✅ **Informative**: Not generic (avoid "operation started", "operation complete")
- ✅ **Actionable**: Reader understands the event's significance
- ✅ **Specific**: Includes relevant context (agent_id, file_id, error type, etc.)

**Bad descriptions** (too generic):
- "Operation completed"
- "Processing started"
- "Error occurred"
- "Loading data"

**Good descriptions** (specific):
- "Cache entry evicted after 24-hour TTL expired"
- "Agent {agent_id} handed off task to {target_agent_id}"
- "Formation YAML validation failed: {error_reason}"

### 4. Context Verification
Cross-reference events with their code locations:
- Read the actual code at the file:line specified
- Verify the description matches what the code does
- Check if there are edge cases not captured

### 5. Category Consistency
- Are similar events grouped under same event_type?
- Are levels consistent across the same event family?
- Are descriptions using consistent terminology?

## Common Issues to Flag

### Level Issues
1. **INFO events that are too granular** (debug-level details)
   - Trigger: event is recording step-by-step operations
   - Solution: Change to DEBUG if needed in dev, remove if not critical
   
2. **ERROR events that aren't errors** (success/normal flow)
   - Trigger: description indicates success but level is ERROR
   - Solution: Change to SystemEvents equivalent
   
3. **WARNING events that indicate success**
   - Trigger: message says "successfully configured" but level is WARNING
   - Solution: Change to INFO or SystemEvents

### Description Issues
1. **Missing specificity** (generic descriptions)
   - Pattern: "Operation {x}", "Processing {y}", "Error {z}"
   - Solution: Add specific context from the code
   
2. **Incomplete information**
   - Pattern: description doesn't explain what happened
   - Solution: Add the actual state/context
   
3. **Inconsistent f-string handling**
   - Pattern: `f-string: {actual_message}` when description exists
   - Solution: Either merge or clarify which is primary

### Misclassification Issues
1. **Operational events as DEBUG**
   - Symptom: Loading, initialization, startup events at DEBUG
   - Check: Should these be INFO or even SystemEvents?
   
2. **Success states as ERROR**
   - Symptom: Event describes completion but classified as ERROR
   - Check: Should be SystemEvents or INFO
   
3. **Missing context in descriptions**
   - Symptom: Description doesn't match the surrounding code
   - Check: Does the f-string format match the description?

## Review Process for Each Chunk

For each event in the chunk:

1. **Quick Check**: Read event_type, level, description
2. **Context Check**: Read the actual source code at file:line
3. **Verification**:
   - Is the level correct for this code context?
   - Is the description accurate?
   - Is this an error or success?
4. **Recommendation**:
   - If no issues: Mark as "OK - Verified"
   - If issue: Specify the problem and solution
   
## Recommendation Categories

- **OK - Verified**: No issues found
- **LEVEL_CHANGE**: Recommend changing level (specify new level)
- **TYPE_CHANGE**: Recommend changing event type (specify new type)
- **DESCRIPTION**: Improve description with specific context
- **MISCLASSIFICATION**: Error/success mismatch (specify correct type/level)
- **REMOVE**: Event is too granular or unnecessary
- **COMBINE**: Merge with similar event

## Output Format

For each issue found:
```
File: <chunk_number>
Event: <event_type>
Line: <line_number>
Current: level=<level>, type=<type>
Issue: <specific_problem>
Recommendation: <CATEGORY> - <detailed_fix>
```

## Priority Levels for Fixes

1. **CRITICAL**: Error/success misclassification
2. **HIGH**: Level incorrect (would affect monitoring/alerting)
3. **MEDIUM**: Description needs improvement
4. **LOW**: Minor consistency issues
