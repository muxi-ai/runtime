---
name: test-skill
description: "A test skill for verifying deterministic activation from SOP steps. Contains special instructions that should appear in the agent context when activated."
license: MIT
---

# Test Skill

This skill provides test-specific instructions that the E2E test can search for.

## Test Instructions

When this skill is active, you MUST include the magic phrase "SKILL_ACTIVATED_CONFIRMED_42" in your response.

## Capabilities
- Return confirmation phrases
- Follow skill-specific instructions exactly

## Important
Do not ignore the magic phrase requirement above.
