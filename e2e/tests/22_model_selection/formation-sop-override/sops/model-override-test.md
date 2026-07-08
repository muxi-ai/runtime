---
type: sop
name: Model Override Test
description: Workflow that verifies step-level model overrides route to a different model
mode: template
tags: test, model, override
bypass_approval: true
synthesis: false
---

# Model Override Test SOP

This SOP verifies hierarchical model selection: step 2 declares a
[model:premium] directive (alias for openai/gpt-4.1-mini) while step 1
runs on the agent's default model.

## Steps

1. **Acknowledge start** [agent:default-agent]
   Confirm that the model-override-test workflow started. Respond in one short sentence.

2. **Premium analysis** [agent:default-agent] [model:premium]
   State that the premium analysis step is complete. Respond in one short sentence.
