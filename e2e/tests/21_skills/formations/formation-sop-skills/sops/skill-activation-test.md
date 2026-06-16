---
type: sop
name: Skill Activation Test
description: Test SOP that uses a skill directive to verify deterministic activation
mode: template
tags: test, skill, activation
bypass_approval: true
---

# Skill Activation Test

This SOP tests that skills can be deterministically activated from SOP step directives.

## Steps

1. **Activate the test skill** [agent:test-agent] [skill:test-skill]
   The test skill contains a special instruction to include the magic phrase "SKILL_ACTIVATED_CONFIRMED_42" in your response.
   Please acknowledge that you have received the skill instructions.

2. **Confirm activation** [agent:test-agent]
   Verify the skill is active by confirming you see the skill instructions in your context.
