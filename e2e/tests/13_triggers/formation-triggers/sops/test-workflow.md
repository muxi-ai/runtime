---
type: sop
name: Test Workflow
description: Simple test workflow for validating explicit SOP invocation
mode: template
tags: test, validation
bypass_approval: true
---

# Test Workflow SOP

This is a test workflow that validates explicit SOP invocation.

## Steps

1. **Acknowledge the request** [agent:test-agent]
   - Confirm that the workflow was triggered
   - Mention this is the "test-workflow SOP"

2. **Process the input** [agent:test-agent]
   - Summarize any data provided
   - Confirm the workflow completed

## Output

Provide a brief confirmation message that includes:
- Confirmation this is the test-workflow SOP
- Summary of input data
- Status: Completed
